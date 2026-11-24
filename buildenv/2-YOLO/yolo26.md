# YOLO26

检测仓。基于 ultralytics，加了场景文字 OCR 等团队功能。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/Yulin-CC/YOLO26` |
| 装到 | 项目根下 `2-YOLO/YOLO26` |
| 环境 | conda `yolo`，Python 3.10 |
| 依赖 skill | `standard-project_merge`、`tool-build_env` |

## 1 拉源码

```bash
cd <项目根>/2-YOLO
git clone https://github.com/Yulin-CC/YOLO26.git
```

## 2 整理项目

按 `skills/standard-project_merge` 走。本仓已有 `0-Agent-demo` 三槽（`_demo_train`、`_demo_infer`、`_demo_eval`）、`0-QuickStart`、`config`、`data`、`weights`，不用重建。

## 3 装环境

```bash
conda create -n yolo python=3.10 -y
conda activate yolo

cd <项目根>/2-YOLO/YOLO26
ln -sf z_others/pyproject.toml pyproject.toml
ln -sf z_others/LICENSE LICENSE
pip install -e .
```

**注意**：`pyproject.toml` 和 `LICENSE` 在仓根是软链，真文件在 `z_others/`。clone 后必须手动建，否则 `pip install -e .` 找不到。

## 4 验证

```bash
conda activate yolo
python -c "from ultralytics import YOLO; m = YOLO('yolo26n.pt'); print('OK')"
```

## 5 已知问题

- **软链要重建**：`pyproject.toml`、`LICENSE` 是软链，指向 `z_others/`。
- **ultralytics 版本是 8.4.90**，不要随手升级，团队改动基于这版。
- 仓内 `ultralytics/` 是 vendored 的，不走 PyPI 安装。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 训练 / 推理 / 评估 | `skills/agent-auto_demo` |
| 场景文字 OCR | `0-QuickStart/4-ocr.sh`，说明在 `z_others/ocr-port.md` |
| 预标 | `skills/agent-data_engine` 的 yolo26 叶 |

## 7 参考

- 团队仓：https://github.com/Yulin-CC/YOLO26
- 上游：https://github.com/ultralytics/ultralytics
