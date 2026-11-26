# Qwen3-VL

团队整理的 Qwen3-VL 工作流：环境安装、标注、微调、推理。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/Yulin-CC/Qwen3-VL` |
| 装到 | 项目根下 `0-VLM/12-Qwen3-VL/Qwen3-VL` |
| 环境 | conda `qwen`，Python 3.12 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

官方源码在仓内 `Qwen/`，归档资料在 `z-others/`。

**本篇只管训练这条线。** 起 vLLM 服务、vLLM 装哪个版本、Qwen 权重从哪拉，都在 [vllm.md](vllm.md)——vLLM 是 Qwen 和 GroundingPI 共用的后端。

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
nice -n 19 pip install --no-cache-dir --force-reinstall --no-build-isolation --no-deps \
  git+https://github.com/Dao-AILab/flash-attention.git@v2.8.3
```

装完验一下，报错就先卸干净再重来：

```bash
python -c "import flash_attn; print(flash_attn.__version__)"
pip uninstall flash-attn -y 2>/dev/null || true
pip cache purge
```

### 3.2 uv 备选

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
- **flash-attn 编译**：要设 `MAX_JOBS` 和 `ulimit -v`，否则 OOM。
- **`max_pixels` / `max_model_len` 调太大**：双卡 24G 卡上会直接爆显存，参数口径见 [vllm.md](vllm.md) §4.5。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 训练 / 推理 | `skills/agent-auto_demo` |
| 起 vLLM 服务（Qwen / GroundingPI） | [vllm.md](vllm.md) |
| 权重从哪拉 | [vllm.md](vllm.md) §4 |
| 服务端口与模型名 | `.cursor/server/services/qwen.md` |

## 7 参考

- 团队仓：https://github.com/Yulin-CC/Qwen3-VL
- 上游：https://github.com/QwenLM/Qwen3-VL
