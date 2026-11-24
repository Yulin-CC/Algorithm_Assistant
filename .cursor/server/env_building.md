# 🔨 环境搭建

怎么把服务装起来。端口、模型名、请求方式看 `services/`。哪台机器用哪个脚本起，看 `workenv/link.md`。

**Windows 不起 vLLM / SAM。**这些都装 Linux 服务器上，装之前先看 GPU 和磁盘。

- [1 vLLM（Qwen / GroundingPI）](#1-vllmqwen--groundingpi)
- [2 Triton SAM](#2-triton-sam)
- [3 已知坑](#3-已知坑)
- [4 装完要做的三件事](#4-装完要做的三件事)

---

## 1 vLLM（Qwen / GroundingPI）

Qwen 和 GroundingPI 都跑 vLLM，装法共用一套。摘自在用仓库 `0-VLM/12-Qwen3-VL/Qwen3-VL/README.md` 第 2 节、第 5 节。

### 1.1 conda 路线

默认 conda 环境 `qwen`，Python 3.12。conda 根用 `CONDA_BASE`（默认 `$HOME/miniconda3`）。

驱动 CUDA 12.8+ 用 `cu128`；12.4 / 12.6 改 `cu124`。**有卡时先装 GPU torch，再装其它包**，否则 PyPI 会把 torch 盖成 CPU 版。

```bash
conda create -n qwen python=3.12
conda activate qwen
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r z-others/requirements.txt
```

训练默认要 flash-attn。装不上时把 `config/default.yaml` 的 `attn_implementation` 改成 `sdpa`，`data_flatten` 设 `false`：

```bash
export MAX_JOBS=24
export MAKEFLAGS="-j24"
ulimit -v 67108864
pip install --no-cache-dir --force-reinstall --no-build-isolation --no-deps \
  git+https://github.com/Dao-AILab/flash-attention.git@v2.8.3
```

### 1.2 服务端另外装 vLLM

只在跑服务时用，训练不需要。从源码装：

```bash
export MAX_JOBS=24
ulimit -v 67108864
git clone https://github.com/vllm-project/vllm.git
cd vllm && pip install -e .
python -c "import vllm; print(vllm.__version__)"
```

**版本不是随便挑的**，见 [§3.1](#31-vllm-版本要按-glibc-和-cuda-挑)。

### 1.3 uv 备选

没 conda 时用项目 `.venv`。后续命令一律用 `$PY`，不要用系统 `python`。原有的 `conda activate qwen` 改成 `source .venv/bin/activate`，或把解释器指到 `$PY`。

```bash
uv venv --python 3.12 .venv
PY="$(pwd)/.venv/bin/python"
uv pip install --python "$PY" torch torchvision --index-url https://download.pytorch.org/whl/cu128
"$PY" -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available())"
uv pip install --python "$PY" -r z-others/requirements.txt
```

有卡但 `cuda` 为 `False` 时停下核对驱动与 `cu128` / `cu124`，不要擅自改装 CPU 轮。

### 1.4 权重

两个权重目录都不小，放模型盘，不放根盘：

| 模型 | 量级 | 来源 |
| --- | --- | --- |
| Qwen3.8-27B | 约 52G，18 个 safetensors 分片 | HuggingFace / ModelScope |
| GroundingPI | 约 9.2G | ModelScope `GroundingPI/GroundingPI` |

国内优先 ModelScope，`snapshot_download` 解决断点续传：

```bash
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('GroundingPI/GroundingPI', cache_dir='/path/to/models')"
```

GroundingPI 的权重目录自带 `modeling_groundingpi.py`、`image_processing_groundingpi.py` 等自定义代码，起服务必须带 `--trust-remote-code`。

## 2 Triton SAM

摘自在用仓库 `0-VLM/7-SAM/sam/README.md`。

### 2.1 前置

| 项 | 要求 |
| --- | --- |
| GPU | NVIDIA，单卡 |
| Docker | 已装 |
| NVIDIA Container Toolkit | 已装且 `nvidia-container-runtime` 在 `/usr/bin/` |
| 镜像 | `nvcr.io/nvidia/tritonserver:24.08-py3`，解压后约 26GB |
| 磁盘 | 镜像放 Docker Root Dir，**建议 ≥40G 空闲** |

先确认能跑 GPU 容器：

```bash
docker run --rm --gpus all nvcr.io/nvidia/tritonserver:24.08-py3 tritonserver --help
```

拉不下镜像时先手动拉：

```bash
docker pull nvcr.io/nvidia/tritonserver:24.08-py3
```

### 2.2 权重

ViT-H 量化 ONNX 两个文件，共约 665MB。从 GitHub release 下载（国内慢，脚本里挂 `ghfast.top` 镜像）：

- `sam_vit_h_4b8939.encoder.quant.onnx` —— 657MB
- `sam_vit_h_4b8939.decoder.quant.onnx` —— 8.7MB

下载后拷进 Triton 仓库时**文件名必须是 `model.onnx`**，放在 `model_repository/<模型名>/1/model.onnx`。

### 2.3 客户端环境

只需要 `tritonclient[grpc]`、`opencv-python`、`numpy`，纯客户端不占 GPU：

```bash
pip install "tritonclient[grpc]" opencv-python numpy
```

轻量探测只用标准库 TCP 连接，不需要这几位。要做真实的 encode/decode 探测才需要。

### 2.4 起容器

关键参数：

| 参数 | 值 |
| --- | --- |
| GPU | `--gpus device=<id>` |
| gRPC 映射 | `-p 6621:8001` |
| HTTP 映射 | `-p 8000:8000` |
| 模型仓库 | `-v <repo>:/models` |
| 启动参数 | `tritonserver --model-repository=/models --strict-model-config=false` |
| 共享内存 | `--shm-size=1g` |
| 重启策略 | `--restart unless-stopped` |

`--strict-model-config=false` 让 Triton 从 ONNX 自动推导输入输出，不用手写 config。

## 3 已知坑

下面几条是在用机器上实测出来的，和 README 写的不一致。接手时先看这里。

### 3.1 vLLM 版本要按 glibc 和 CUDA 挑

在 106 上装 GroundingPI 时踩过一整轮：

| 版本 | 为什么不选 |
| --- | --- |
| vllm 0.22+ | PyPI 上是 CUDA 13 构建 |
| vllm 0.21.0 | 元数据写 CUDA 12，实际仍链 `libcudart.so.13` |
| vllm 0.20.x | 要 glibc 2.35，本机只有 2.31 |
| **vllm 0.19.1** | manylinux_2_31，只链 `libcudart.so.12`，可用 |

驱动 550 只能到 CUDA 12，所以上面的 0.22 / 0.21 / 0.20 全排除。装完验证：

```bash
python -c "import vllm; print(vllm.__version__)"
ldd $(python -c "import vllm,os;print(os.path.dirname(vllm.__file__))")/_C*.so | grep libcudart
```

第二句必须只出现 `libcudart.so.12`。出现 `.so.13` 就是装错了。

### 3.2 `aria2c` 不在默认环境里

SAM 的权重下载脚本用 `aria2c -c -x 16 -s 16` 多源续传，单靠 `wget` 在 GitHub 上会慢到按小时算。但 `aria2c` 不是系统自带：

```bash
sudo apt-get install -y aria2
command -v aria2c || echo "没装，下载脚本会失败"
```

### 3.3 `tritonclient` 不一定在 conda `yulin` 里

旧文档写「客户端探测用 conda `yulin`」。实测：`/path/to/home/miniconda3` 不存在，`yulin` 这个环境也没有；`tritonclient` 实际装在某台机器的 `7-SAM/sam/.venv` 里（Python 3.14），而且**那个 venv 缺 `PIL`**。

探测脚本如果只 import `tritonclient`、`cv2`、`numpy`，能跑；一旦用到图像读写就会因缺 `PIL` 报错。先验一遍：

```bash
<python> -c "import tritonclient.grpc, cv2, numpy; print('ok')"
<python> -c "import PIL; print('PIL ok')"    # 可能失败
```

缺就先补：`pip install pillow`。

### 3.4 启动脚本里的 `public_ip` 是硬编码

SAM 的启动脚本里有一行 `public_ip="<HOST>"`，换机器后不会自动更新（脚本会用 `ifconfig.me` 兜底，但内网机器拿不到）。换机器时顺手改掉，或者只看脚本打印的 `127.0.0.1:6621`。

### 3.5 106 上 `/path/to/home` 是软链

`/path/to/home` → `/data`。所以：

- `/path/to/home/1-project` 与 `/data/1-project` 是同一个目录。
- 但 **conda 和权重在 `/path/to/home`，不在 `/path/to/home`**。`/path/to/home/miniconda3` 才是真的 conda 根。
- 登录用户、conda 根、权重根、数据根**不在同一个 home**。路径写错就会找不到环境。

### 3.6 Qwen3.6-35B-A3B 权重不在 106 上

`/path/to/home/models/` 只有 `Qwen3.8-27B` 和 `GroundingPI`。Qwen3.6 那条启动脚本在，但权重目录不存在，现在起不来。

### 3.7 <HOST> 那台不用 conda

`<HOST>`（4×3090，用户 `caiyulin`）是 uv venv，不走 conda：

| 项 | 值 |
| --- | --- |
| venv | `/path/to/home/1-project/0-VLM/vllm-env312`（Python 3.12） |
| 权重 | `/path/to/home/models/GroundingPI` |
| 仓库 | `/path/to/home/1-project/0-VLM/12-Qwen-VL/QwenVL`（注意是 `12-Qwen-VL`，不是 106 上的 `12-Qwen3-VL`） |
| 版本 | torch 2.10.0+cu128 / transformers 5.19.0 / vllm **0.19.1** |

这台机器驱动是 550（CUDA 12 上限），glibc 2.31，所以 vLLM 只能落 0.19.1，原因见 §3.1。它和 106 的脚本同名但完全是另一份，`weight`、`venv`、`port` 都不同，改之前先看清在哪台机器上。

8080 上有别人的 uvicorn 在跑，不要动。GroundingPI 用 8082。

## 4 装完要做的三件事

1. 把服务地址写进 `config/vllm_server.json`（vLLM 系）或 `config/sam.json`（Triton 系）。这是程序真正读的地方。
2. 把这台机器的启动脚本绝对路径和权重目录写进 `workenv/link.md`。
3. 跑探活，确认通了：

```bash
py -3 server/util/probe.py
```

探完把结果和 PID 记进 `server/ledger/runs.md`。
