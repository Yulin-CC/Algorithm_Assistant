# SAM3

分割。开放词汇，用文本提示出掩膜。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/Yulin-CC/SAM3`（官方 `facebookresearch/sam3` 基础上，几乎无改动） |
| 装到 | 项目根下 `0-VLM/7-SAM/SAM3` |
| 环境 | conda `sam3`，Python 3.12 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

```bash
cd <项目根>/0-VLM/7-SAM
git clone https://github.com/Yulin-CC/SAM3.git
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-QuickStart`、`1-data-process`、`config`、`data`、`weights`，不用重建。

## 3 装环境

```bash
conda create -n sam3 python=3.12 -y
conda activate sam3
pip install -e ".[train]"
pip install pycocotools
```

### 3.1 权重

`weights/` 下要有 `sam3.pt`。来源见 `server/env_building.md` 或问团队。

## 4 验证

```bash
conda activate sam3
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## 5 已知问题

- **环境名要一致**：启动脚本默认 `conda activate sam3`。环境名或 conda 根不同时，改脚本里的 `CONDA_ENV` / `CONDA_BASE`，或 `export`。
- **`sam3.pt` 缺了要单独要**：叶说明里提到缺权重时会给百度云链接。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 预标（文本提示出框/掩膜） | `skills/agent-data_engine` 的 sam3 叶 |
| 训练 / 推理 | `skills/agent-auto_demo` |

## 7 参考

- 团队仓：https://github.com/Yulin-CC/SAM3
- 上游：https://github.com/facebookresearch/sam3
