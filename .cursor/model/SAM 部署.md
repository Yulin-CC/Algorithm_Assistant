# 🎯 SAM 部署

AnyLabel 自动分割有两条路：**Triton 远程服务**（多人共用 GPU）和 **本机 ONNX**（单机离线）。exe 不封装权重，侧栏只是客户端。Qwen 检测/分割走同一套 Triton（`sam_client.py` 读 `model/config/sam.json`）。

---

## 0 落盘前确认（Agent 必做）

动手 `mkdir` / 下权重 / `docker pull` **之前**，先把目录树发给用户，等确认落盘位置。不要猜路径，不要默默写到工作区或 `/tmp`。

分清两处磁盘，树里两处都要写：

| 落盘 | 写什么 | 典型位置 |
|------|--------|----------|
| **项目目录** | 脚本、ONNX、`model_repository/` | 用户指定的绝对路径 |
| **Docker 镜像** | `tritonserver:24.08-py3` 解压后约 **26GB** | `docker info` 的 **Docker Root Dir**（常见 `/var/lib/docker`，往往在 **根盘 `/`**，不是项目盘） |

先跑：

```bash
hostname; whoami
df -h / "$HOME"
docker info 2>/dev/null | grep -E 'Docker Root Dir|Runtimes'
nvidia-smi -L
```

把下面这棵树填上绝对路径发给用户，改括号即可。未回复「按此落盘」不要写盘、不要 pull。

```markdown
请确认落盘位置，回复「按此落盘」（改括号即可）：

1. 项目目录：[绝对路径]
2. 只上标准 SAM，还是连 HQ？：[标准 / 标准+HQ]
3. GPU / 对外 gRPC 端口：[GPU id、<PORT>；<PORT> 须是防火墙已开放的口]
4. Docker Root Dir 剩余空间：[df -h 对应分区；镜像建议 ≥40G 空闲]
```

示意树（路径按用户确认改）：

```
<项目目录>/                              # 用户确认的绝对路径
├── README.md
├── 0-QuickStart/
│   ├── 0-download.sh                    # 下 ViT-H 量化 ONNX 并拷入仓库
│   ├── 1-start.sh                       # docker run（GPU / 端口在脚本顶部）
│   ├── 2-probe.sh                       # HTTP ready + 假图 encode/decode
│   └── scripts/probe.py
├── weights/                             # 原始 onnx（encoder ~627M，decoder ~8.4M）
└── model_repository/                    # Triton 仓库；目录名不要改
    ├── sam_vit_h_encoder/
    │   ├── config.pbtxt
    │   └── 1/model.onnx
    └── sam_vit_h_decoder/
        ├── config.pbtxt
        └── 1/model.onnx
```

Docker 镜像**不**进这棵树，进 Docker Root Dir。根盘和项目盘不是同一块时，只看项目盘剩余会误判。

真实 IP、对外端口、项目绝对路径只写在本机 `1-start.sh` / `sam.json`，**不要**写进这份会公开的文档。`1-start.sh` 启动时应打印远程怎么连（外网 `host:port`，不要加 `http://`）。

---

## 1 环境搭建

### 1.1 客户端（AnyLabel）

- **创建并激活虚拟环境**

  ```bash
  conda create -n anylabel python=3.10 -y
  conda activate anylabel
  ```

- **安装依赖**

  ```bash
  cd 1-annotation-tool/anylabel
  pip install -r z-others/requirements.txt
  pip install "tritonclient[grpc]"   # 方案 A 必装
  ```

- **启动标注软件**

  ```bash
  # Windows
  0-start.bat

  # Linux
  bash z-others/0-start.sh
  ```

- **验证**

  ```bash
  python -c "import PyQt5, onnxruntime, tritonclient.grpc; print('ok')"
  ```

本机 ONNX 要走 GPU：再装 `onnxruntime-gpu`，并把 `anylabeling/app_info.py` 里 `__preferred_device__` 改成 `GPU`。

Qwen 探测脚本用本机标注 conda（`tritonclient[grpc]`、`opencv-python`、`numpy`），不要装进正在跑 vLLM 的环境。

### 1.2 服务端（仅方案 A）

- **机器**：NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- **镜像**：`nvcr.io/nvidia/tritonserver:24.08-py3`（需能拉 NGC）
- **验证（镜像已在本地后）**

  ```bash
  docker run --rm --gpus all nvcr.io/nvidia/tritonserver:24.08-py3 tritonserver --help
  ```

### 1.3 拉 Triton 镜像（容易翻车，先看空间再 pull）

`24.08-py3` 压缩层约 9GB，落到 Docker Root Dir 后大约 **26GB**。解压峰值比最终占用更大。

**拉之前：**

```bash
docker info | grep 'Docker Root Dir'
df -h /                          # 若 Root Dir 在根盘，看这一行的 Avail
```

| 根盘剩余 | 结果（本机 2026-09- 11） |
|----------|-------------------------|
| ~20G | 层能下完，解压 `libonnxruntime_providers_cuda.so` 时报 `no space left on device`，镜像作废 |
| ~69G | 可以拉完（结束后根盘大约还剩 44G） |
| 建议 | **Avail ≥ 40G** 再 pull；不够就扩容根盘，或把 Docker Root Dir 改到大盘（要改 daemon 并重启 Docker，需用户点头） |

**拉取：**

```bash
docker pull nvcr.io/nvidia/tritonserver:24.08-py3
```

- NGC 账号一般不必登。`curl` 清单返回 `401` 仍可能匿名 pull 成功。
- `TLS handshake timeout`：网络抖，隔一会儿再拉，或交给用户在能出网的终端手动 pull。Agent 连不上时不要死循环。
- 大层解压时日志会停很久，`docker images` 也暂时看不到完整镜像，用 `df -h /` 是否在涨判断还在写盘。
- pull 失败后执行 `docker system prune -af`，避免半截层占着根盘。

拉完核对：

```bash
docker images nvcr.io/nvidia/tritonserver:24.08-py3
# 期望 DISK USAGE 大约 26GB
```

用户说「我手动拉」时，等对方确认 `docker images` 里有 `24.08-py3` 再跑 `1-start.sh`。

---

## 2 方案怎么选

| 方案 | 适用场景 | 侧栏入口 |
|------|----------|----------|
| **A Triton** | 多人共用、机器没大显存；Qwen 检测/分割 | 下拉默认两项 |
| **B 本机 ONNX** | 单机、可离线 | 自定义模型，自己选 yaml |

客户端连 Triton 走 **gRPC**，地址格式 `host:port`。Triton 容器内 gRPC 默认 **8001**，对外映射成防火墙已开放的 `<PORT>`（`-p <PORT>:8001`）。HQ 若另起再映射另一个已开放端口。Qwen 客户端只要标准 SAM；HQ 可后加。

---

## 3 方案 A：Triton 远程服务

软件把图和点/框发到服务器，服务器返回 mask。侧栏 / `sam.json` 的模型名必须和 Triton 仓库里的名字对上：

| 侧栏模型 | Triton 模型名（硬编码，勿改） |
|----------|------------------------------|
| Triton Segment Anything | `sam_vit_h_encoder` + `sam_vit_h_decoder` |
| Triton SAM HQ | `sam_hq_pv_encoder` + `sam_hq_pv_decoder` |

入口（落盘确认后；在用户指定的项目目录下）：

```bash
cd <项目目录>/0-QuickStart
bash 0-download.sh    # ONNX → model_repository
bash 1-start.sh       # GPU / 对外端口在脚本顶部；启动时打印远程怎么连
bash 2-probe.sh       # 假图 encode/decode（用本机标注 conda，不要用 vLLM 那个）
```

### 3.1 权重下载

公开权重来自 [X-AnyLabeling Releases](https://github.com/CVHub520/X-AnyLabeling/releases)。标准 SAM 用 ViT-H 量化；HQ 用 ViT-L（仓库名仍须叫 `sam_hq_pv_*`，和客户端一致）。

`wget` 单连接走 GitHub 可能只有几十 KB/s（本机 encoder 626MB 曾显示 ETA 十七小时）。`0-download.sh` 用 **aria2 多连接**，并备 `https://ghfast.top/<原URL>`。

```bash
# 标准 SAM（ViT-H 量化）encoder ~627M / decoder ~8.4M
# 优先跑 0-download.sh；手工时用 aria2，不要裸 wget
aria2c -c -x 16 -s 16 -k 1M --file-allocation=none \
  -o sam_vit_h_4b8939.encoder.quant.onnx \
  "https://ghfast.top/https://github.com/CVHub520/X-AnyLabeling/releases/download/v0.2.0/sam_vit_h_4b8939.encoder.quant.onnx" \
  "https://github.com/CVHub520/X-AnyLabeling/releases/download/v0.2.0/sam_vit_h_4b8939.encoder.quant.onnx"

aria2c -c -x 16 -s 16 -k 1M --file-allocation=none \
  -o sam_vit_h_4b8939.decoder.quant.onnx \
  "https://ghfast.top/https://github.com/CVHub520/X-AnyLabeling/releases/download/v0.2.0/sam_vit_h_4b8939.decoder.quant.onnx" \
  "https://github.com/CVHub520/X-AnyLabeling/releases/download/v0.2.0/sam_vit_h_4b8939.decoder.quant.onnx"

# HQ-SAM（ViT-L 量化，效果更好；本机暂未上）
# https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.0.0/sam_hq_vit_l_encoder_quant.onnx
# https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.0.0/sam_hq_vit_l_decoder.onnx
```

自训 HQ 权重同样按下面目录放，**目录名不要改**。

### 3.2 模型仓库

```
model_repository/
├── sam_vit_h_encoder/
│   ├── config.pbtxt
│   └── 1/
│       └── model.onnx          # ← encoder.quant.onnx 改名拷入
├── sam_vit_h_decoder/
│   ├── config.pbtxt
│   └── 1/
│       └── model.onnx          # ← decoder.quant.onnx
├── sam_hq_pv_encoder/          # 可选；本机未部署
│   ├── config.pbtxt
│   └── 1/
│       └── model.onnx
└── sam_hq_pv_decoder/
    ├── config.pbtxt
    └── 1/
        └── model.onnx
```

`config.pbtxt` 最小写法（四个模型各一份，只改 `name`）：

```
name: "sam_vit_h_encoder"
backend: "onnxruntime"
max_batch_size: 0
instance_group [{ kind: KIND_GPU, count: 1 }]
```

其余三个把 `name` 换成 `sam_vit_h_decoder` / `sam_hq_pv_encoder` / `sam_hq_pv_decoder`。输入输出名由 onnx 自行推断。

整理示例：

```bash
REPO=/path/to/model_repository
ENC=sam_vit_h_encoder
# DEC=sam_vit_h_decoder   # 标准 SAM 再做一份

mkdir -p $REPO/$ENC/1
cp sam_vit_h_4b8939.encoder.quant.onnx $REPO/$ENC/1/model.onnx
cat > $REPO/$ENC/config.pbtxt << EOF
name: "$ENC"
backend: "onnxruntime"
max_batch_size: 0
instance_group [{ kind: KIND_GPU, count: 1 }]
EOF
```

ViT-H 量化大约占 **5–6GB** 显存。绑单卡（`1-start.sh` 顶部 `devices`），不要和占满同一张卡的训练硬叠。`--gpus all` 在多卡机上容易抢错卡。

### 3.3 启动服务

优先 `1-start.sh`（`--gpus device=$devices`）。等价命令：

```bash
REPO=<项目目录>/model_repository
docker run --gpus device=$devices -d --name sam-triton --restart unless-stopped \
  --shm-size=1g \
  -p 8000:8000 -p <PORT>:8001 -p 8002:8002 \
  -v "$REPO":/models \
  nvcr.io/nvidia/tritonserver:24.08-py3 \
  tritonserver --model-repository=/models --strict-model-config=false
```

- `<PORT>:8001`：对外 gRPC，客户端填 `<HOST>:<PORT>`（与 Qwen 同机时 `<HOST>` 用同一台外网地址；不要加 `http://`）
- HQ 单独一台/另起容器时，另映射一个已开放的端口即可
- 容器内只有一张可见 GPU 时，日志里的 `GPU device 0` 对应宿主机绑的那张卡
- `1-start.sh` 起来后应打印：远程外网 `<HOST>:<PORT>`、本机 `127.0.0.1:<PORT>`

看是否起来：

```bash
docker logs -f sam-triton          # 两行 READY：sam_vit_h_encoder / sam_vit_h_decoder
curl -s localhost:8000/v2/health/ready
bash <项目目录>/0-QuickStart/2-probe.sh
```

探测通过后改 `model/config/sam.json` 的 `url` 为 `<HOST>:<PORT>`，`encoder` / `decoder` 不要改。停服务：`docker stop sam-triton`。改 GPU/端口后先 `docker rm -f sam-triton` 再启动。

### 3.4 客户端怎么连

改 `config/default.yaml`（或侧栏地址栏）。换服务器时只改 **IP 和端口**，格式必须是 `host:port`，不要加 `http://` / `grpc://`：

```yaml
triton_url: "<HOST>:<PORT>"                  # 全局默认；未单独指定的模型走这里
auto_labeling_servers:
  segment_anything_triton: "<HOST>:<PORT>"   # 标准 SAM
  sam_hq_pv_triton: "<HOST>:<PORT>"          # HQ-SAM
```

示例：`<HOST>:<PORT>`、`127.0.0.1:<PORT>`。`<PORT>` 填 Docker 映射出来的 **对外 gRPC 端口**（容器内仍是 `8001`）。真实地址只写 `sam.json` / `1-start.sh`。

Qwen：`~/.cursor/model/config/sam.json` 的 `url` 同样是 `host:port`。

解析顺序：`auto_labeling_servers[模型type]` → `triton_url`。界面里改过的地址会进 `~/.anylabelrc`，空值不会盖掉这份 yaml。

标注软件里：

1. 打开自动标注侧栏
2. 下拉选 **Triton Segment Anything** 或 **Triton SAM HQ**
3. 确认地址 `ip:port`，状态灯变绿（在线）即可用
4. 灯红：服务没起、端口不对、或仓库里缺对应模型名

---

## 4 方案 B：本机 ONNX

不启 Triton。第一次按 yaml 里的链接下载 encoder/decoder，之后走本地缓存。

| 推荐 | yaml | 权重 |
|------|------|------|
| 先试小的 | `anylabeling/configs/auto_labeling/edge_sam.yaml` | [encoder](https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.2.0/edge_sam_encoder.onnx) / [decoder](https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.2.0/edge_sam_decoder.onnx) |
| 效果更好 | `anylabeling/configs/auto_labeling/sam_hq_vit_l_quant.yaml` | [encoder](https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.0.0/sam_hq_vit_l_encoder_quant.onnx) / [decoder](https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.0.0/sam_hq_vit_l_decoder.onnx) |
| 标准 ViT-H | `anylabeling/configs/auto_labeling/segment_anything_vit_h_quant.yaml` | [encoder](https://github.com/CVHub520/X-AnyLabeling/releases/download/v0.2.0/sam_vit_h_4b8939.encoder.quant.onnx) / [decoder](https://github.com/CVHub520/X-AnyLabeling/releases/download/v0.2.0/sam_vit_h_4b8939.decoder.quant.onnx) |

缓存目录：

```
~/anylabeling_data/models/<yaml 里的 name>/   # Linux
%USERPROFILE%\anylabeling_data\models\...     # Windows
```

手动预下载（可选，避免界面里等）：

```bash
# Linux 示例：HQ-SAM
DIR=~/anylabeling_data/models/sam-hq_vit_l_quant-r20231111
mkdir -p "$DIR"
wget -O "$DIR/sam_hq_vit_l_encoder_quant.onnx" \
  https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.0.0/sam_hq_vit_l_encoder_quant.onnx
wget -O "$DIR/sam_hq_vit_l_decoder.onnx" \
  https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.0.0/sam_hq_vit_l_decoder.onnx
```

用法：

1. 打开自动标注侧栏
2. 选 **加载自定义模型**
3. 选上表某个 yaml，等加载（或下载）完成
4. 在图上点 / 画框出 mask

想让某模型出现在默认下拉列表，把它写进 `anylabeling/configs/auto_labeling/models.yaml`。

---

## 5 标注操作（两套方案相同）

1. `Ctrl+U` 打开数据集（至少有 `images/`）
2. 选好模型，等就绪
3. 点或框选目标，按 `F` 完成当前对象（完成前标签面板不可编辑）

| 快捷键 | 作用 |
|--------|------|
| `Q` | 正点（目标上） |
| `E` | 负点（排除） |
| 画框 | 框选目标 |
| `F` | 完成当前对象 |
| `B` | 清除当前提示 |

侧栏可切输出：**矩形 / 多边形 / 旋转框**。
