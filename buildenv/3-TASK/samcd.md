# SAM-CD

建筑变化检测。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/Yulin-CC/SAM-CD` |
| 装到 | 项目根下 `3-TASK/SAM-CD` |
| 环境 | conda `samcd`，Python 3.12 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

```bash
cd <项目根>/3-TASK
git clone https://github.com/Yulin-CC/SAM-CD.git
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-Agent-demo` 三槽（每槽有 `SKILL.md`）、`0-QuickStart`、`config`、`data`、`models`、`weights`，不用重建。

## 3 装环境

```bash
conda create -n samcd python=3.12
conda activate samcd
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r z-others/requirements.txt
```

## 4 验证

```bash
conda activate samcd
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## 5 已知问题

- 仓根有 `install_tbr.sh`，是补丁安装脚本。**先确认它是否适用于本仓**（SCM 那个是改 ultralytics，不要混用）。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 训练 / 推理 / 评估 | `skills/agent-auto_demo`，三槽是 `_demo_train` / `_demo_infer` / `_demo_eval` |
| 变化检测分析 | `skills/agent-smart_image` 的 `analysis.py --pred` |

## 7 参考

- 团队仓：https://github.com/Yulin-CC/SAM-CD
