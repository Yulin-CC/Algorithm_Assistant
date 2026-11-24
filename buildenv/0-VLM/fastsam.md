# FastSAM

快速分割。基于 YOLOv8-seg。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/CASIA-IVA-Lab/FastSAM` |
| 装到 | 项目根下 `0-VLM/7-SAM/FastSAM` |
| 环境 | conda `FastSAM`，Python 3.9 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

```bash
cd <项目根>/0-VLM/7-SAM
git clone https://github.com/CASIA-IVA-Lab/FastSAM.git
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-Agent-demo`、`0-QuickStart`、`config`、`data`、`fastsam`、`ultralytics`、`utils`，不用重建。

## 3 装环境

需要 Python ≥ 3.9。**本仓 vendored `ultralytics==8.0.120`，不要再 `pip install ultralytics`。**

```bash
conda create -n FastSAM python=3.9 -y
conda activate FastSAM

cd <项目根>/0-VLM/7-SAM/FastSAM
ln -sf z-others/requirements.txt requirements.txt
pip install --upgrade pip setuptools wheel
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install git+https://github.com/openai/CLIP.git
```

按 CUDA 版本调整：12.1 改 `cu121`，11.8 改 `cu118`。

### 3.1 权重

`weights/FastSAM.pt`。来源见 `0-QuickStart/` 的下载脚本或上游 release。

## 4 验证

```bash
conda activate FastSAM
python 0-QuickStart/scripts/inference.py --dataset ./images/dogs.jpg --weights ./weights/FastSAM.pt
```

默认值来自 `config/default.yaml`，CLI 优先。

## 5 已知问题

- **不要装 PyPI 的 ultralytics**：仓内 vendored 了 8.0.120，装了会冲突。
- **`pyproject.toml` / `requirements.txt` 软链不要提交**：装环境时建，提交前删。
- **`pip install -r requirements.txt` 等价于根目录 `pip install -e .`**，靠这个定位 `fastsam/` 和 `ultralytics/`。
- **要装 CLIP**：单独一条 `pip install git+https://github.com/openai/CLIP.git`。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 推理 | `0-QuickStart/1-inference.sh` 或 `scripts/inference.py` |
| 训练 | `skills/agent-auto_demo` |

## 7 参考

- 上游：https://github.com/CASIA-IVA-Lab/FastSAM
