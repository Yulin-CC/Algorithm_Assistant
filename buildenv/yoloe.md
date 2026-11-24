# YOLOE

开放集目标检测与分割。支持文本 / 视觉 / Prompt-Free 三种推理。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/THU-MIG/yoloe`（上游）；团队版在其上改了数据流程与 QuickStart |
| 权重 | `huggingface.co/jameslahm/yoloe` + MobileCLIP |
| 装到 | 项目根下 `0-VLM/16-YOLO-E/YOLOE` |
| 环境 | conda `yoloe`，**Python 3.10**，torch cu128 |
| 选装 | conda `sam2`，Python 3.10.16（标签只有 bbox 时要它生成掩膜） |
| 依赖 skill | `standard-project_merge`、`standard-quickstart`、`tool-build_env` |

> 团队版与上游的差异：多了 `0-QuickStart/` 四个入口脚本、`1-data-process/` 两套预处理、`3-review_server/`、`data/` 的 yaml 自动生成。这些不在上游。

## 1 拉源码

上游 clone 后，把团队的 `0-QuickStart`、`1-data-process`、`2-annotation-tool`、`3-review_server`、`data`、`config` 覆盖进去。

```bash
cd <项目根>/0-VLM/16-YOLO-E
git clone https://github.com/THU-MIG/yoloe.git YOLOE
```

团队版的这三处必须一起拿，缺了跑不通：

| 路径 | 是什么 |
| --- | --- |
| `0-QuickStart/` | 四个入口：`0-train_open.sh`、`0-train_pe.sh`、`1-inference.sh`、`2-eval.sh` |
| `1-data-process/` | PE 与 Grounding 两套数据预处理 |
| `config/` | `train_open.yaml`、`train_pe.yaml`、`vocab/`、`mobileclip:blt/` |

**问团队要一份完整包**，或从已有机器拷（`z-others/` 里的改动也在内）。

## 2 整理项目

按 `skills/standard-project_merge` 走，这一步别跳，否则后面的脚本找不到文件：

1. 读上游 `README.md`，确认目录约定
2. 建 `0-QuickStart/`（团队版已有，跳过）
3. 按 `skills/standard-project_agentdemo` 建 `0-Agent-demo` 三槽：`_demo_train`、`_demo_infer`、`_demo_eval`
4. 散落文件归档到 `z-others/`
5. 重写根 `README.md`（团队版已有）

## 3 装环境

### 3.1 主环境

```bash
conda create -n yoloe python=3.10 -y
conda activate yoloe

cd <项目根>/0-VLM/16-YOLO-E/YOLOE
ln -sf z-others/pyproject.toml pyproject.toml
ln -sf z-others/requirements.txt requirements.txt
pip install --upgrade pip setuptools wheel
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**注意**：`pyproject.toml` 和 `requirements.txt` 在仓根是软链，真文件在 `z-others/`。clone 上游后这两个软链不存在，必须手动建。

**注意**：装之前先搜一遍 `source /path/to/miniconda3/etc/profile.d/conda.sh`，改成实际的 conda 路径。QuickStart 脚本里写死了。

### 3.2 预训练权重

推理和微调都要。

```bash
mkdir -p weights
pip install huggingface-hub==0.26.3
export HF_ENDPOINT=https://hf-mirror.com

huggingface-cli download jameslahm/yoloe yoloe-11s-seg.pt     --local-dir weights/
huggingface-cli download jameslahm/yoloe yoloe-11s-seg-pf.pt  --local-dir weights/
huggingface-cli download jameslahm/yoloe yoloe-11s-seg-coco.pt --local-dir weights/

wget -O weights/mobileclip_blt.pt \
  https://docs-assets.developer.apple.com/ml-research/datasets/mobileclip/mobileclip_blt.pt
```

`HF_ENDPOINT` 必须设，否则国内拉不动。

### 3.3 选装：SAM2

**只在标签只有 bbox、需要生成掩膜时才装。**

```bash
conda create -n sam2 python=3.10.16
conda activate sam2
pip install -r third_party/sam2/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install -e third_party/sam2/ -i https://pypi.tuna.tsinghua.edu.cn/simple
mkdir -p weights
wget -O weights/sam2.1_hiera_large.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
```

## 4 验证

```bash
conda activate yoloe
cd <项目根>/0-VLM/16-YOLO-E/YOLOE

# 看环境对不对
python -c "import torch, ultralytics; print(torch.__version__, torch.cuda.is_available())"

# 跑一次推理（先改 1-inference.sh 里的权重和图片路径）
bash 0-QuickStart/1-inference.sh
```

能出框图就算装好。`cuda` 为 `False` 就停下查 torch 和驱动，不要继续。

## 5 已知问题

- **Python 必须是 3.10**。上游 `pyproject.toml` 钉死了，3.12 装不上。
- **软链会丢**。clone 上游后 `pyproject.toml` / `requirements.txt` 两个软链不存在，必须重建。
- **`config/mobileclip:blt/` 是目录名带冒号**，在 Windows 上不合法。这仓只能在 Linux 上跑。
- **`config/vocab/` 是词表**，训练前要确认这轮用的词表在不在（`proj-261123-yoloe-gd05` 那次就是为词表做消融）。
- **开集训练要合并 yaml**：`data/train_colorcar.yaml` 别手改，走 `data/` 下的生成脚本。

## 6 后续

装好之后：

| 要做的事 | 走哪个 |
| --- | --- |
| 准备数据 | `skills/agent-data_engine` 的 organize，或 `1-data-process/` |
| 训练 | `skills/agent-auto_demo` 的 `_demo_train` 槽 |
| 推理 / 评估 | `skills/agent-auto_demo` 的 `_demo_infer` / `_demo_eval` |
| 预标 | `skills/agent-data_engine` |
| 看这台机器上它在哪 | `workarea/env-<主机>/projects.md` |

## 7 参考

- 上游：https://github.com/THU-MIG/yoloe
- 权重：https://huggingface.co/jameslahm/yoloe/tree/main
- 团队调研笔记：https://www.wolai.com/6BYdTivH3Pe7YG6CdDehom
- 源码适配（把上游某功能切进本仓）：`skills/agent-source_adapt`
