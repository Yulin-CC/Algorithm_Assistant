# Qwen3-VL

团队整理的 Qwen3-VL 工作流：环境安装、标注、微调、推理与 vLLM 服务。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/Yulin-CC/Qwen3-VL` |
| 装到 | 项目根下 `0-VLM/12-Qwen3-VL/Qwen3-VL` |
| 环境 | conda `qwen`，Python 3.12 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

官方源码在仓内 `Qwen/`，归档资料在 `z-others/`。

## 1 拉源码

```bash
cd <项目根>/0-VLM/12-Qwen3-VL
git clone https://github.com/Yulin-CC/Qwen3-VL.git
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-QuickStart`、`0-Agent-demo`、`config`、`data`，不用重建。

## 3 装环境

conda 根用 `CONDA_BASE`（默认 `$HOME/miniconda3`）。驱动 CUDA 12.8+ 用 `cu128`；12.4 / 12.6 改 `cu124`。**有卡时先装 GPU torch 再装其它包**，否则 PyPI 会把 torch 盖成 CPU 版。

```bash
conda create -n qwen python=3.12
conda activate qwen
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r z-others/requirements.txt
```

### 3.1 flash-attn（训练需要）

默认 `attn_implementation: flash_attention_2`。装不上时把 `config/default.yaml` 的 `attn_implementation` 改 `sdpa`，`data_flatten` 设 `false`。

```bash
export MAX_JOBS=24
export MAKEFLAGS="-j24"
ulimit -v 67108864
pip install --no-cache-dir --force-reinstall --no-build-isolation --no-deps \
  git+https://github.com/Dao-AILab/flash-attention.git@v2.8.3
```

### 3.2 vLLM（服务端需要）

```bash
export MAX_JOBS=24
ulimit -v 67108864
git clone https://github.com/vllm-project/vllm.git
cd vllm && pip install -e .
python -c "import vllm; print(vllm.__version__)"
```

版本要按 glibc 和 CUDA 挑，见 `.cursor/server/env_building.md` §3.1。

### 3.3 uv 备选

无 conda 时用项目 `.venv`，后续命令一律用 `$PY`。QuickStart 脚本里的 `conda activate qwen` 要改成 `source .venv/bin/activate`。

```bash
uv venv --python 3.12 .venv
PY="$(pwd)/.venv/bin/python"
uv pip install --python "$PY" torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python "$PY" -r z-others/requirements.txt
```

## 4 验证

```bash
conda activate qwen
python -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available())"
```

有卡但 `cuda` 为 `False` 就停下核对驱动与 `cu128` / `cu124`，不要改装 CPU 轮。

## 5 已知问题

- **`CUDA` 版本选错**：驱动 12.8+ 用 `cu128`，12.4/12.6 用 `cu124`。
- **vLLM 版本**：PyPI 上 0.22+ 是 CUDA 13 构建，glibc 2.31 的机器只能落 0.19.1。详见 `server/env_building.md` §3.1。
- **flash-attn 编译**：要设 `MAX_JOBS` 和 `ulimit -v`，否则 OOM。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 训练 / 推理 | `skills/agent-auto_demo` |
| 起 vLLM 服务 | `.cursor/server/env_building.md` §1 |

## 7 参考

- 团队仓：https://github.com/Yulin-CC/Qwen3-VL
- 上游：https://github.com/QwenLM/Qwen3-VL
