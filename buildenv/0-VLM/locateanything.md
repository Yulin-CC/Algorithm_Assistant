# LocateAnything（eagle）

视觉定位。

| 项 | 值 |
| --- | --- |
| 来源 | `huggingface.co/nvidia/LocateAnything-3B` |
| 装到 | 项目根下 `0-VLM/15-LocateAnything/eagle` |
| 环境 | Python 3.10+（上游 README 示例里的 conda 环境名换成自己的） |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

模型来自 HuggingFace，需按上游说明下载。

```bash
cd <项目根>/0-VLM/15-LocateAnything
# 按 huggingface.co/nvidia/LocateAnything-3B 的说明下载到 eagle/
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-QuickStart`、`config`、`testdir`、`utils`、`weights`，不用重建。

## 3 装环境

Python 3.10 以上。

```bash
conda create -n <envname> python=3.10
conda activate <envname>
cd <项目根>/0-VLM/15-LocateAnything/eagle
pip install -r requirements.txt
```

## 4 验证

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## 5 已知问题

- **来源是 HF 不是 git**：README 只给了模型页，没有源码仓地址。先确认 `eagle/` 里哪部分是源码、哪部分是权重。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 推理 | `0-QuickStart/` |

## 7 参考

- 模型：https://huggingface.co/nvidia/LocateAnything-3B
