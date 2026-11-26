# vLLM

上游推理框架，也是 Qwen、GroundingPI 两个服务的后端。装环境、版本约束、权重来源、启动配方都写在这一篇。Triton SAM 不走 vLLM，见 [triton-sam.md](triton-sam.md)。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/vllm-project/vllm` |
| 装到 | 项目根下 `0-VLM/0-vllm/vllm`（源码）；服务环境的 venv 单独建 |
| 环境 | 服务端 conda `vllm`（或无 conda 时 uv venv）；训练用 conda `qwen`。都是 Python 3.12 |
| 依赖 skill | `tool-build_env` |

**vLLM 是上游源码，不是独立算法仓**：没有 `0-Agent-demo`、没有 QuickStart，不套 `standard-project_merge`。

Qwen 与 GroundingPI 的差别只在**权重和启动参数**，装环境这一步是同一套。两个服务占同一个 GPU 时，同一时间只能起一个。

服务端环境与训练环境分开是好习惯：训练那套装 flash-attn、跑长任务，服务端只要 vLLM + torch + transformers，互相不干扰。

- [1 拉源码](#1-拉源码)
- [2 整理项目](#2-整理项目)
- [3 装环境](#3-装环境)
- [4 权重与启动配方](#4-权重与启动配方)
- [5 验证](#5-验证)
- [6 已知问题](#6-已知问题)
- [7 后续](#7-后续)
- [8 参考](#8-参考)

---

## 1 拉源码

服务端要编源码，先拉下来：

```bash
mkdir -p <项目根>/0-VLM/0-vllm
cd <项目根>/0-VLM/0-vllm
git clone https://github.com/vllm-project/vllm.git
```

## 2 整理项目

不做。上游源码保持原样，套 `standard-project_merge` 会把结构搞乱。

## 3 装环境

### 3.1 先挑版本，再动手

**PyPI 上的 vLLM 不是每个版本都能用**，取决于机器的 glibc 和驱动上限。下表是「老驱动（CUDA 12 上限）+ glibc 2.31」这类机器上实测的结果：

| 版本 | 能不能用 |
| --- | --- |
| 0.22+ | PyPI 上是 CUDA 13 构建，`import` 就报 `libcudart.so.13` |
| 0.21.0 | 元数据写 CUDA 12，实际 wheel 仍链 `libcudart.so.13` |
| 0.20.x | wheel 标签 `manylinux_2_35`，要 glibc ≥ 2.35，2.31 装不上 |
| **0.19.1** | `manylinux_2_31`，只链 `libcudart.so.12`，可用 |

结论：**驱动只到 CUDA 12、glibc 2.31 的机器，PyPI 上限是 0.19.1**。驱动更新、glibc 更新的机器可以往上试，但要按下面的办法验过再用。

另一条路是自己从源码编 cu128 版（[§3.4](#34-从源码装另一条路)），不受这张表限制，版本号可以比 PyPI 高。代价是编一次 15–20 分钟。

装之前先看 wheel 属于哪条 CUDA 线：

```bash
# 1) 看 wheel 标签的 manylinux 版本（对应 glibc）
curl -s https://pypi.org/pypi/vllm/<ver>/json | python3 -c "import json,sys;[print(f['filename']) for f in json.load(sys.stdin)['urls']]"
# 2) 装完解包后看编译扩展依赖哪个 cudart
readelf -d <site-packages>/vllm/_C.abi3.so | grep -E 'NEEDED|RUNPATH'
```

第二条只应出现 `libcudart.so.12`。出现 `.so.13` 就是装错了。

### 3.2 conda 路线

conda 根用 `CONDA_BASE`（默认 `$HOME/miniconda3`）。驱动 CUDA 12.8+ 用 `cu128`；12.4 / 12.6 改 `cu124`。**有卡时先装 GPU torch，再装其它包**，否则 PyPI 会把 torch 盖成 CPU 版。

服务端和训练端建两个环境，装的东西不一样：

```bash
# 服务端：只要 vLLM + torch + transformers
conda create -n vllm python=3.12
conda activate vllm
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install vllm==0.19.1          # 版本见 §3.1，别直接装最新
pip install 'transformers==5.19.0'  # 防止被降到 4.x

# 训练端：Qwen3-VL 仓内那份依赖
conda create -n qwen python=3.12
conda activate qwen
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r z-others/requirements.txt   # Qwen3-VL 仓内那份
```

服务端和训练端建两个环境、名字分开，是常见做法：服务脚本激活服务环境，训练脚本激活训练环境，互不干扰。**环境名是最容易出岔子的一处**：接手的机器上常常只有其中一个，或者名字不一样（有人建 `qwen`、有人建 `vllm`、有人干脆用 venv）。看到脚本起不来先核对这一点，改脚本里 `conda activate` 那一行就行，不要去改蓝图。

上面那个 `vllm==0.19.1` 是 PyPI 轮子路线。也可以用源码编一个更高版本（[§3.4](#34-从源码装另一条路)），不是 pip 装的，两条都能用，选一条就行。

训练还要 flash-attn，那一步在 [qwen3-vl.md](qwen3-vl.md) §3.1，装服务不需要。

flashinfer 若是用 conda 里新的 gcc 编出来的，跑之前要补一句，否则会报 `libstdc++` 版本不够：

```bash
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

这句要跟着环境走：用 conda 环境时指 `$CONDA_PREFIX`，用 venv 时指 `<venv>/lib`。指错了会变成找不到 `.so` 或加载到别的环境的库。

### 3.3 uv 路线（无 conda）

venv 放哪随便，记进 `workarea/link.md`。下面以 `0-VLM/vllm-env312` 为例，`vllm==0.19.1` 要求 `torch==2.10.0`：

```bash
UV=/snap/bin/uv
PY=<项目根>/0-VLM/vllm-env312/bin/python
CU=https://download.pytorch.org/whl/cu128

$UV venv --python 3.12 <项目根>/0-VLM/vllm-env312

$UV pip install --python $PY --index-strategy unsafe-best-match --extra-index-url $CU \
    torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0

$UV pip install --python $PY --index-strategy unsafe-best-match --extra-index-url $CU \
    'vllm==0.19.1' 'torch==2.10.0' 'torchvision==0.25.0' 'torchaudio==2.10.0'

$UV pip install --python $PY --index-strategy unsafe-best-match --extra-index-url $CU \
    'transformers==5.19.0'
```

**`--index-strategy unsafe-best-match` 必须带。** 只给 `--extra-index-url` 时，uv 的默认 first-index 策略会去 `download.pytorch.org/whl/cu128/vllm/` 找 vllm，那里没有兼容版本，直接报 `No solution found ... no version of vllm==X`。

装完确认 GPU 版没被盖掉：

```bash
$PY -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

有卡但 `cuda` 为 `False`，回去重装 cu128 的 torch，不要将就用 CPU 轮。

### 3.4 从源码装（另一条路）

源码装也可以：源码放 `0-VLM/0-vllm/vllm`，`git checkout` 到一个确认过的 commit，`pip install -e .` 编成 cu128 版，包名会带 `+<commit>` 后缀（实测有 `0.26.1.dev0+g568afb3a1` 这种）。装在单独那个服务环境里。

它和 PyPI wheel 不是一回事，**版本号不能互抄**：`0.19.1` 是 PyPI 路线在旧 glibc 机器上的上限，源码编的可以更高，两边不冲突。看到别人的版本号比自己高，先问是编的还是装的。

```bash
export MAX_JOBS=24
ulimit -v 67108864
cd <项目根>/0-VLM/0-vllm/vllm
git checkout <确认过的 commit>
pip install -e .
python -c "import vllm; print(vllm.__version__)"
```

编一次 15–20 分钟起步，编译机内存要够。编完同样要按 §3.1 的办法验 `_C*.so` 链的是 `libcudart.so.12`。

源码装适合驱动 / glibc 太旧、PyPI 上没合适 wheel 的机器；能装 wheel 就别编。

## 4 权重与启动配方

### 4.1 清单

放模型盘，不放根盘。

| 模型 | 量级 | 来源 |
| --- | --- | --- |
| Qwen3.8-27B | 约 52G，18 个 `model-0000X-of-00018.safetensors` 分片 | ModelScope / HuggingFace，仓库 id 看权重盘上的 `README.md` |
| Qwen3.6-35B-A3B | 双卡 MoE，比 27B 更大 | 同上；有的机器只留了启动脚本，权重没下 |
| GroundingPI | 约 9.2G（29 个 blob，9254.6 MB） | ModelScope `GroundingPI/GroundingPI` |

国内优先 ModelScope。两个模型的权重目录都自带 `README.md`（模型卡），**仓库 id 以那张卡为准**，不要凭文件名猜。

GroundingPI 的权重目录还自带 `modeling_groundingpi.py`、`image_processing_groundingpi.py`、`processing_groundingpi.py` 等自定义代码，**起服务必须带 `--trust-remote-code`**。目录里还有 `checksums.sha256` 和 `requirements.txt`，后者是它自己的依赖，装服务时对着看一眼。

### 4.2 ModelScope（推荐）

```bash
pip install modelscope
# GroundingPI
python -c "from modelscope import snapshot_download; snapshot_download('GroundingPI/GroundingPI', cache_dir='/path/to/models')"
# Qwen，id 换成权重卡上的那个
python -c "from modelscope import snapshot_download; snapshot_download('<org>/Qwen3.8-27B', cache_dir='/path/to/models')"
```

断点续传由 `snapshot_download` 处理。要自己控文件清单（比如跳过 `assets/`），GroundingPI 走直连：

- 单文件：`https://www.modelscope.cn/api/v1/models/GroundingPI/GroundingPI/repo?Revision=master&FilePath=<相对路径>`
- 文件清单：`https://www.modelscope.cn/api/v1/models/GroundingPI/GroundingPI/repo/files?Revision=master`

换别的模型把 id 换掉即可，`/api/v1/models/<org>/<name>/repo/files?Revision=master` 这套接口是通用的。

清单里 `Type=blob` 的才是权重，`assets` 是目录（Size=0），推理用不到，可以跳过。下载用 `curl -C -` 续传，每个文件失败重试几次。

GroundingPI 下完对一遍 `checksums.sha256`：26 个非 assets 文件应全部 `OK`，两个大 safetensors 的字节数分别是 `4995018360`、`4692384808`。跳过 `assets/` 的后果是这 5 个文件报 "No such file"，不影响推理。

### 4.3 HuggingFace

有的机器 `huggingface.co` 不通，全程改走 ModelScope。能通也要挂镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download <repo_id> --local-dir /path/to/models/<name>
```

### 4.4 GroundingPI 启动配方

官方 recipe：单卡、BF16、eager、单图、关视频。4B BF16 约 10GB 显存，一张 24G 卡够。

```bash
export CUDA_VISIBLE_DEVICES=0
unset CUDA_HOME
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

vllm serve /path/to/models/GroundingPI \
    --host 0.0.0.0 --port 8082 \
    --served-model-name groundingpi \
    --model-impl transformers \
    --dtype bfloat16 \
    --enforce-eager \
    --trust-remote-code \
    --tensor-parallel-size 1 \
    --max-model-len 16384 \
    --max-num-seqs 1 \
    --gpu-memory-utilization 0.70 \
    --limit-mm-per-prompt '{"image":1,"video":0}' \
    --allowed-local-media-path /home
```

`--max-num-seqs 1` 是官方设定，并发高了会排队，别误以为服务卡住。

`--allowed-local-media-path` 填的是**这台机器上图片实际所在的根**，示例里的 `/home` 只是常见值。客户端走 base64 传图时这个参数用不上；要让服务端直接读盘上的路径，才必须填对。

`unset CUDA_HOME` 不是随手写的：有的机器 `/usr/local/cuda` 指向很旧的 CUDA（见过 11.2），flashinfer 和 triton 的 JIT 会照着它找 nvcc，编译直接失败。宁可留空，让它们用 venv 里 pip 装的 `nvidia-cuda-nvcc-cu12`。

### 4.5 Qwen 启动配方

双卡 `0,1`，与 GroundingPI 争卡时通常要错开。

```bash
export CUDA_VISIBLE_DEVICES=0,1
# flashinfer 若是 conda 里新 gcc 编的，补这一句，否则报 libstdc++ 版本不够
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

vllm serve /path/to/models/Qwen3.8-27B \
    --host 0.0.0.0 --port 8081 \
    --served-model-name qwen3.8-27b \
    --tensor-parallel-size 2 \
    --max-model-len 131072 \
    --gpu-memory-utilization 0.85 \
    --trust-remote-code \
    --attention-backend FLASHINFER \
    --reasoning-parser qwen3 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --mm-processor-kwargs '{"max_pixels": 200704, "min_pixels": 784}' \
    --mm-encoder-attn-backend TORCH_SDPA \
    --allowed-local-media-path /home
```

- 双卡 24G 卡上 `max_model_len` 实际建议压到 16k–32k，131072 是上限不是建议值。
- 纯文本任务加 `--language-model-only`，省显存，代价是不能识图。
- 两个 Qwen 模型共用 8081，换模型等于停一个再起一个，`config/` 里的 `base_url` 不用改。
- `--tensor-parallel-size` 要等于 `CUDA_VISIBLE_DEVICES` 里卡的个数。脚本里按逗号切开自动算最省事。

启动脚本写在各机器上，**绝对路径与权重目录记在 `workarea/link.md`**，本篇只记参数口径。

## 5 验证

三跳，缺一跳都不算起来。

```bash
# 1) 包装对了
python -c "import vllm; print(vllm.__version__)"
ldd $(python -c "import vllm,os;print(os.path.dirname(vllm.__file__))")/_C*.so | grep libcudart

# 2) 端口在听、模型名对
ss -lntp | grep 8082
curl -s http://127.0.0.1:8082/v1/models

# 3) 真发一条请求
curl -s http://127.0.0.1:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"groundingpi","messages":[{"role":"user","content":[
        {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,<...>"}},
        {"type":"text","text":"红色矩形"}]}],
      "skip_special_tokens":false,"spaces_between_special_tokens":false}'
```

日志里要出现 `Application startup complete.`，PID 与日志路径记进 `server/ledger/runs.md`。只看端口开着不算起来。

GroundingPI 的坐标是 `<0>`…`<999>` 量化 token，两个 `skip_special_tokens` 开关必须是 `false`，否则坐标被吞，看着像空回复。返回形如：

```
<|object_ref_start|>红色矩形<|object_ref_end|><|box_start|><93><125><406><416><|box_end|>
```

换算回像素是 `x/1000*宽`、`y/1000*高`。拿一张知道框在哪的测试图对一遍，框对上了才算验完。

## 6 已知问题

在几台机器上实测出来的，接手先看这张表。

| 现象 | 原因 | 解法 |
| --- | --- | --- |
| `ImportError: libcudart.so.13` | wheel 是 CUDA 13 构建（0.22+） | 降到 0.19.1，并卸掉带进来的 CUDA 13 残留包 |
| 0.21.0 也报 `.so.13` | 元数据写 cu12，wheel 实际链 `.so.13` | 一样排除，别信元数据 |
| 0.20.x 装不上 | wheel 标签 `manylinux_2_35`，要 glibc ≥ 2.35；glibc 2.31 的机器装不上 | 排除，见 [§3.1](#31-先挑版本再动手) |
| `No solution found ... no version of vllm==X` | uv 默认 first-index，去 pytorch index 找 vllm | 加 `--index-strategy unsafe-best-match` |
| 装了 vllm 后 torch 变 CPU 版 | PyPI 覆盖 | 用 pytorch cu128 index 重装 torch 覆盖回来 |
| `transformers` 被降到 4.x | vllm 依赖解析 | 装 `transformers==5.19.0` 覆盖（0.19.1 无上限） |
| flashinfer / triton JIT 编译报错 | `CUDA_HOME` 指向机器上那份旧 CUDA（见过指向 CUDA 11.2 的） | `unset CUDA_HOME`，用 venv 里 pip 装的 `nvidia-cuda-nvcc-cu12` |
| `import` 时报找不到自定义类 | GroundingPI 权重目录带自定义代码 | 启动带 `--trust-remote-code` |
| GroundingPI 返回空或只有文字 | 默认 `skip_special_tokens=true` 吞掉 `<0>`..`<999>` | 请求里两个开关都设 `false` |
| 权重下到一半断 | `huggingface.co` 国内不通 | 走 ModelScope，`curl -C -` 续传 |
| 起服务后显存爆 | 同卡上有训练或另一个服务 | 先 `nvidia-smi` 看占用，再决定错开还是换卡 |
| 脚本报 `conda: command not found` / 激活了错的环境 | 脚本里写死了某台机器的 conda 根路径 | 改成这台机器实际的 `conda.sh` 路径，或改用 venv |
| 换了机器端口起不来 | 端口上已有别人的进程（不一定是自己的） | 先 `ss -lntp` 看归属，别直接动别人的 |

还有两条不属于版本问题的：

- **不要当算法仓整理**：它是上游源码，套 `standard-project_merge` 会搞乱结构。
- **端口不一定空着**：别人的 uvicorn / celery 之类可能正占着某个端口，起服务前先看端口归属，不要动别人的进程。

## 7 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 起服务：脚本绝对路径、权重目录 | `workarea/link.md` |
| 端口、模型名、请求注意点 | `.cursor/server/services/qwen.md`、`services/groundingpi.md` |
| 程序读的地址 | `.cursor/server/config/vllm_server.json` |
| 起停台账 | `.cursor/server/ledger/runs.md` |
| 装完自检 | `python server/util/probe.py` |
| Qwen 的训练环境与微调 | [qwen3-vl.md](qwen3-vl.md) |

## 8 参考

- 上游：https://github.com/vllm-project/vllm
- Qwen3-VL 仓内 `README.md` 第 1、4 节（vLLM 可选安装、`2-vllm` 服务脚本）
- GroundingPI：https://www.modelscope.cn/models/GroundingPI/GroundingPI
