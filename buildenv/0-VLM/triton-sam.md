# Triton SAM

标准 SAM ViT-H（量化 ONNX）的 Triton 远程服务。给分割补边、变化检测报点加 SAM 用。

| 项 | 值 |
| --- | --- |
| 来源 | **无项目地址**。纯 Docker 服务，自建 |
| 装到 | 项目根下 `0-VLM/7-SAM/sam` |
| 环境 | 容器 `nvcr.io/nvidia/tritonserver:24.08-py3` |
| 依赖 skill | `standard-project_merge` |

服务本身的端口、模型名、请求方式看 `.cursor/server/services/triton-sam.md`。这里只讲怎么从零搭起来。

## 1 拿源码

没有 git 地址。**从已有机器拷整个目录**，或问团队要压缩包。

要拷的目录：

```
sam/
├── 0-QuickStart/          # 0-download.sh、1-start.sh、2-probe.sh
│   └── scripts/probe.py
├── model_repository/      # Triton 仓库，目录名不要改
│   ├── sam_vit_h_encoder/
│   └── sam_vit_h_decoder/
├── embed_store_lib/
└── README.md
```

`weights/` 和 `model_repository/*/1/model.onnx` 可以由 `0-download.sh` 重新下，不必拷。

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓不是普通算法仓，没有 `0-Agent-demo`，整理时只做：

1. 确认 `0-QuickStart/` 三个脚本完整
2. 散落文件归档到 `z-others/`
3. 重写根 `README.md`（已有）

## 3 装环境

### 3.1 前置

| 项 | 要求 |
| --- | --- |
| GPU | NVIDIA，单卡 |
| Docker | 已装 |
| NVIDIA Container Toolkit | 已装，`nvidia-container-runtime` 在 `/usr/bin/` |
| 磁盘 | 镜像解压后约 26GB，Docker Root Dir 建议 ≥40G 空闲 |

验证能跑 GPU 容器：

```bash
docker run --rm --gpus all nvcr.io/nvidia/tritonserver:24.08-py3 nvidia-smi -L
```

### 3.2 拉镜像

```bash
docker pull nvcr.io/nvidia/tritonserver:24.08-py3
```

### 3.3 下权重

```bash
cd <项目根>/0-VLM/7-SAM/sam/0-QuickStart
bash 0-download.sh
```

脚本会从 GitHub release 下两个量化 ONNX（encoder 657MB + decoder 8.7MB），挂 `ghfast.top` 镜像加速，然后拷进 `model_repository/*/1/model.onnx`。

**依赖 `aria2c`**，没装会失败：

```bash
sudo apt-get install -y aria2
```

### 3.4 客户端环境（可选）

只在要跑 `2-probe.sh` 时需要。装 `tritonclient[grpc]`、`opencv-python`、`numpy`，纯客户端不占 GPU。

```bash
pip install "tritonclient[grpc]" opencv-python numpy
```

或用仓内 `.venv`。

## 4 起服务与验证

```bash
cd <项目根>/0-VLM/7-SAM/sam/0-QuickStart
bash 1-start.sh      # 起容器，GPU 1，gRPC 6621

# 等 READY
docker logs -f sam-triton

# 探活
bash 2-probe.sh
```

`1-start.sh` 顶部可改的参数：`devices`（GPU id）、`grpc_port`（6621）、`http_port`（8000）、`name`（容器名 `sam-triton`）。

日志里出现 READY 才算起来。只看端口开着不算。

## 5 已知问题

- **`aria2c` 不在默认环境**：`0-download.sh` 用它多源续传，没有就会失败。
- **启动脚本里 `public_ip` 是硬编码**：换机器不会自动更新，只看它打印的 `127.0.0.1:6621`。
- **客户端不是 conda `yulin`**：旧文档这么写，实际 `tritonclient` 常在 `7-SAM/sam/.venv`，且那 venv 可能缺 `PIL`。
- **改 GPU 或端口要先删容器**：改 `1-start.sh` 顶部后 `docker rm -f sam-triton` 再起，直接 restart 不生效。
- **ViT-H 量化仍占几个 GB 显存**：不要和占满同卡的训练叠。
- **HQ 版暂不提供**。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 客户端怎么连 | `.cursor/server/services/triton-sam.md` |
| 装完写地址 | `server/config/sam.json` 的 `url` |
| 起停台账 | `server/ledger/runs.md` |

## 7 参考

- 仓内 `README.md`（最详细）
- 安装坑：`.cursor/server/env_building.md` §2 与 §3.2–3.4
