---
name: image-detseg-yolo26
description: >-
  YOLO26 detect/segment prelabel from local weights. sample writes vis;
  run writes LabelMe jsons-det-pre (rectangle) or jsons-seg-pre (polygon).
  Does not overwrite jsons/ or labels/. Use when agent-dataengine
  dispatched backend=yolo26, or the user says YOLO26 预标, yolo 出框.
disable-model-invocation: true
---

# 检测/分割 · YOLO26（`2-Image-DetSeg/yolo26`）

  - **概述**: YOLO26 权重预标。`sample` 写叠图给人看；`run` 按任务写矩形或多边形。不写回正式 `jsons/` / `labels/`。流程：`confirm → sample（看 vis）→ run`。
  - **日期**: 2026-09-11

---

## 0 执行前检查

  - **触发**：YOLO26 预标、yolo 出框、权重推理打框；由 `agent-dataengine` 指定 `backend=yolo26`。
  - **本包根目录 `PKG_ROOT`**：`.skill/` 的上一级。
  - **数据根目录 `data_root`**：必须由用户给出；须有 `images/`（或根下直接放图）。
  - **落盘**（相对 `data_root`）：

    ```text
    <data_root>/
      images/
      draft/detseg-yolo26/cache/sample/
        vis/{stem}.jpg          # sample 叠图（给人看）
        jsons/{stem}.json       # sample LabelMe；imagePath 相对该 json
      jsons-det-pre/{stem}.json     # run + detect：rectangle 两点
      jsons-seg-pre/{stem}.json # run + segment：polygon
    ```

    不写正式 `jsons/`、`labels/`。sample 不写全量目录。`imagePath` 由脚本按 json 位置相对到原图。
  - **权重目录 `WEIGHTS_DIR`**：`tools/1-DataEngine/_weights/`。先问用户有无指定模型，**无指定**再按 [§0.2] 搜本机 / 下官方。
  - **任务**：`detect`（矩形）或 `segment`（多边形，权重须为 `*-seg.pt`）。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。本叶：`NEED_TORCH=yes`，`PKGS=ultralytics`，临时 venv slug=`yolo26`。有卡先 GPU torch 再装 ultralytics。Windows 控制台 `PYTHONUTF8=1`。
  - **不做**：不训练、不导出、不跑金字塔/基类互补、不在本叶调 VLM 滤框（要滤框用 `1-Image-Classify` 另开 Customer 任务）。不执行 `uv cache clean` / `pip uninstall`。

---

### 0.1 环境初始化（未通过不得跑）

  按 `skills/tool-build_env/SKILL.md`：先看卡，uv 建 `$YoloVenv`，有卡先装 GPU torch，再：

    ```bash
    uv pip install --python "$PY" ultralytics
    ```

  验收用 `$PY`：`import ultralytics, torch`，并打印 `cuda`。有卡但 `cuda` 为 `False` → 停。本任务命令都用 `$PY`。交付后或失败退出前只删 `$YoloVenv`。

---

### 0.2 权重（未就绪不得跑）

  **先向用户确认有无指定模型**（`.pt` / `.engine` 绝对路径，或「无 / 用官方」）。未得到答复前，**禁止搜盘、禁止下载**。

  - **有指定** → 检查文件可读。可用则作为 `--weights`（可拷一份进 `WEIGHTS_DIR` 留档，不覆盖已有同名）。不要再搜、不要下官方。
  - **无指定** → 再走下面 1 → 2（官方默认 **s**）。

  官方发布页：[ultralytics/assets v8.4.0](https://github.com/ultralytics/assets/releases/tag/v8.4.0)  
  直链根：`https://github.com/ultralytics/assets/releases/download/v8.4.0/`  
  文档：[YOLO26](https://docs.ultralytics.com/models/yolo26/)

  | 任务 | 默认文件 | 直链 |
  | --- | --- | --- |
  | detect | `yolo26s.pt` | https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s.pt |
  | segment | `yolo26s-seg.pt` | https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s-seg.pt |

  同系列还有 `yolo26n/m/l/x.pt` 与 `yolo26n/m/l/x-seg.pt`。仅当用户无指定、且点名其它尺度时才换文件名。

  `WEIGHTS_DIR`：`PKG_ROOT/../../_weights`（即 `tools/1-DataEngine/_weights`）。没有则建。

  **1.（仅无指定）本机已有 `yolo26*.pt`** → 拷贝进 `WEIGHTS_DIR`（已在则跳过，不覆盖）。只搜这些根，**不要扫整盘**：

  - `WEIGHTS_DIR`
  - 用户主目录 `Downloads/`、`Desktop/`
  - Ultralytics 缓存：`~/.ultralytics/`（Windows 另加 `%USERPROFILE%\AppData\Roaming\Ultralytics`）

    ```bash
    cp "<found>/yolo26s.pt" "$WEIGHTS_DIR/yolo26s.pt"
    ```

  命中多份 → 列出路径与大小，让用户选；未选则用任务默认 **s**。

  **2.（仅无指定且 `WEIGHTS_DIR` 仍缺所需文件）** → 从官方直链下到该目录：

    ```bash
    mkdir -p "$WEIGHTS_DIR"
    curl -L --fail -o "$WEIGHTS_DIR/yolo26s.pt" \
      "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s.pt"
    # segment 把文件名换成 yolo26s-seg.pt
    ```

  Windows 无 curl 时用 `Invoke-WebRequest -Uri ... -OutFile ...`。下完检查文件非空。

  无指定时 `--weights` 用 `$WEIGHTS_DIR/<文件>`。

---

## 1 向用户确认（未确认不得跑）

    ```markdown
    请确认后回复「按此开跑」（改括号即可）：

    1. 数据集目录：[绝对路径；含 images/]
    2. 任务：[detect | segment]
    3. 权重：[指定绝对路径 | 无 → 官方 yolo26s / yolo26s-seg]
    4. 写出：随 task（detect→jsons-det-pre | segment→jsons-seg-pre）
    5. conf：[0.35]
    6. 试跑样本数：[12]
    7. device：[0 | cpu]
    ```

---

## 2 执行

  工作目录：`PKG_ROOT`。解释器 = [§0.1] 的 `$PY`。segment 必须用 `*-seg.pt`。

### 2.1 sample 叠图检阅

    ```bash
    "$PY" util/batch_prelabel_json.py sample --dataset "<data_root>" --weights "$WEIGHTS_DIR/yolo26s.pt" --task detect --n 12 --seed 0 --device 0
    # segment 把 --task 与权重换成 segment / yolo26s-seg.pt
    ```

  完成后把 **`draft/detseg-yolo26/cache/sample/vis/`** 给用户看。

  - **注意**：**此处必须停止**。用户说「直接全量」→ §2.2。vis 不像样 → 说明后停，不要硬 run。

### 2.2 全量写盘

    ```bash
    "$PY" util/batch_prelabel_json.py run --dataset "<data_root>" --weights "$WEIGHTS_DIR/yolo26s.pt" --task detect --device 0
    "$PY" util/batch_prelabel_json.py run --dataset "<data_root>" --weights "$WEIGHTS_DIR/yolo26s-seg.pt" --task segment --device 0
    ```

  detect → `jsons-det-pre/`（rectangle）；segment → `jsons-seg-pre/`（polygon）。已有非空 json 默认跳过；覆盖须 `--force`。CPU 解释器 `--device cpu`。可选 `--classes "person,car"` 只保留这些类。

---

## 3 工具索引

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 权重 | `../../_weights/` | 官方 `yolo26*.pt`（[v8.4.0](https://github.com/ultralytics/assets/releases/tag/v8.4.0)） |
  | 入口 | `util/batch_prelabel_json.py` | `sample` / `run` |
  | 基类互补 | `customer/image-260827-class-complement/` | 不在本叶 |

---
