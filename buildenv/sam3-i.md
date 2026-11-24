# SAM3-I

SAM3 的交互式版本。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/debby-0527/SAM3-I`（上游 `facebookresearch/sam3`） |
| 装到 | 项目根下 `0-VLM/7-SAM/SAM3-I` |
| 环境 | conda `sam3i`，Python 3.10 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

```bash
cd <项目根>/0-VLM/7-SAM
git clone https://github.com/debby-0527/SAM3-I.git
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-QuickStart`、`config`、`data`、`sam3`、`weights`，不用重建。

## 3 装环境

Python ≥ 3.8，建议 3.10。需 CUDA GPU。**环境名 `sam3i` 必须与 `0-QuickStart/*.sh` 里的 `conda activate` 一致。**

```bash
conda create -n sam3i python=3.10 -y
conda activate sam3i

cd <项目根>/0-VLM/7-SAM/SAM3-I
ln -sf z-others/requirements.txt requirements.txt
pip install --upgrade pip setuptools wheel
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

CUDA 12.1 可把 `cu128` 改 `cu121`；11.8 改 `cu118`。

## 4 验证

```bash
conda activate sam3i
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## 5 已知问题

- **软链要重建**：`requirements.txt` 是软链，指向 `z-others/`。
- **环境名必须是 `sam3i`**：QuickStart 脚本里写死了。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 训练 / 推理 | `skills/agent-auto_demo` |

## 7 参考

- 团队仓：https://github.com/debby-0527/SAM3-I
- 上游：https://github.com/facebookresearch/sam3
