# GroundingDINO

开放集检测，文本提示出框。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/longzw1997/Open-GroundingDino` |
| 装到 | 项目根下 `0-VLM/6-GroundingDINO` |
| 环境 | conda（环境名自定），Python 3.10 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

```bash
cd <项目根>/0-VLM
git clone https://github.com/longzw1997/Open-GroundingDino.git 6-GroundingDINO
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-QuickStart`、`2-label-process`、`config`、`data`、`datasets`、`models`、`util`，不用重建。

## 3 装环境

环境名自定（README 用的是 `<envname>`）。既有机器上跑的是 `yvlm`。

```bash
conda create -n <envname> python=3.10
conda activate <envname>
cd <项目根>/0-VLM/6-GroundingDINO
pip install -r z-others/requirements.txt
```

### 3.1 权重

`groundingdino_swint_ogc.pth` 来自 `huggingface.co/ShilongLiu/GroundingDINO`。还有 `bert-base-uncased`。

## 4 验证

```bash
conda activate <envname>
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## 5 已知问题

- **环境名不固定**：README 写 `<envname>`，实际机器上用 `yvlm`。起脚本前先确认 `CONDA_ENV`。
- **`2-label-process/` 是团队加的**，上游没有。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 推理 | `0-QuickStart/` 或根目录 `inference.py` |
| 训练 | 根目录 `train.py` |

## 7 参考

- 上游（Open 版）：https://github.com/longzw1997/Open-GroundingDino
- 权重：https://huggingface.co/ShilongLiu/GroundingDINO
