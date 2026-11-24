# nanochat

最便宜的 ChatGPT 训练框架。一行命令训练 GPT-2，然后和它聊天。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/karpathy/nanochat` |
| 装到 | 项目根下 `0-VLM/17-NanoChat/nanochat` |
| 环境 | **uv**（不是 conda），GPU 用 `--extra gpu` |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

```bash
cd <项目根>/0-VLM/17-NanoChat
git clone https://github.com/karpathy/nanochat.git
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-QuickStart`、`config`、`dev`、`scripts`、`tasks`、`tests`、`nanochat`，不用重建。

## 3 装环境

用 **uv** 做依赖管理，不用 conda。

```bash
cd <项目根>/0-VLM/17-NanoChat/nanochat

# uv.lock 和 pyproject.toml 归档在 z-others/，要建软链
ln -sf z-others/uv.lock uv.lock
ln -sf z-others/pyproject.toml pyproject.toml

# GPU 环境（CUDA A100/H100 等）
uv sync --extra gpu

# CPU / MPS 环境（MacBook）
# uv sync --extra cpu

# 激活虚拟环境
source .venv/bin/activate
```

### 3.1 开发环境

```bash
uv sync --extra gpu --group dev
```

会额外装 `pytest`、`matplotlib`、`ipykernel`、`transformers` 等。

## 4 验证

```bash
python -c "import nanochat; print('环境 OK')"
```

## 5 已知问题

- **用 uv 不用 conda**：`uv sync` 自动建 `.venv`，激活走 `source .venv/bin/activate`。
- **软链要重建**：`uv.lock`、`pyproject.toml` 在仓根是软链，真文件在 `z-others/`。
- **GPU / CPU 二选一**：`--extra gpu` 和 `--extra cpu` 按机器选，不要都装。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 训练 / 推理 | `0-QuickStart/`、`scripts/` |
| 任务脚本 | `tasks/` |

## 7 参考

- 上游：https://github.com/karpathy/nanochat
- uv 文档：https://docs.astral.sh/uv/
