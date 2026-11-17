---
name: image-detseg-sam3
description: >-
  SAM3 text-prompt detect/segment prelabel from local sam3.pt. sample writes
  vis; run writes LabelMe jsons-det-pre (rectangle) or jsons-seg-pre (polygon).
  Does not overwrite jsons/ or labels/. Use when agent-dataengine dispatched
  backend=sam3, or the user says SAM3 预标, sam3 出框, 文本提示分割.
disable-model-invocation: true
---

# 检测/分割 · SAM3（`2-Image-DetSeg/sam3`）

  - **概述**: SAM3 文本提示预标。`sample` 写叠图给人看；`run` 按任务写矩形或多边形。不写回正式 `jsons/` / `labels/`。流程：`confirm → sample（看 vis）→ run`。
  - **日期**: 2026-09-11

---

## 0 执行前检查

  - **触发**：SAM3 预标、sam3 出框、文本提示分割、概念分割；由 `agent-dataengine` 指定 `backend=sam3`。
  - **本包根目录 `PKG_ROOT`**：`.skill/` 的上一级。
  - **数据根目录 `data_root`**：必须由用户给出；须有 `images/`（或根下直接放图）。
  - **落盘**（相对 `data_root`）：

    ```text
    <data_root>/
      images/
      draft/detseg-sam3/cache/sample/
        vis/{stem}.jpg          # sample 叠图（给人看）
        jsons/{stem}.json       # sample LabelMe；imagePath 相对该 json
      jsons-det-pre/{stem}.json     # run + detect：rectangle 两点
      jsons-det-pre-<class>/{stem}.json  # 单类约定，如 jsons-det-pre-car（--jsons）
      jsons-seg-pre/{stem}.json # run + segment：polygon
      draft/detseg-sam3/progress.json  # run 进度（可用 --progress 改路径）
    ```

    不写正式 `jsons/`、`labels/`。sample 不写全量目录。`imagePath` 由脚本按 json 位置相对到原图。
  - **权重目录 `WEIGHTS_DIR`**：`tools/1-DataEngine/_weights/`。先问用户有无指定模型，**无指定**再按 [§0.2] 搜本机 / 请用户从百度云下载。
  - **任务**：`detect`（矩形）或 `segment`（多边形）。同一套 `sam3.pt` + 文本 `--prompt`。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。本叶：`NEED_TORCH=yes`，`PKGS=ultralytics`，临时 venv slug=`sam3`。有卡先 GPU torch 再装 ultralytics。Windows 控制台 `PYTHONUTF8=1`。
  - **不做**：不训练、不导出 trainer ckpt、不跑金字塔/基类互补、不在本叶调 VLM 滤框。不执行 `uv cache clean` / `pip uninstall`。

---

### 0.1 环境初始化（未通过不得跑）

  按 `skills/tool-build_env/SKILL.md`：先看卡，uv 建 `$SamVenv`，有卡先装 GPU torch，再：

    ```bash
    uv pip install --python "$PY" ultralytics
    ```

  验收用 `$PY`：`from ultralytics.models.sam import SAM3SemanticPredictor`，并 `import torch` 打印 `cuda`。有卡但 `cuda` 为 `False` → 停。

  若推理报 `SimpleTokenizer` / `'clip' object is not callable`：

    ```bash
    uv pip install --python "$PY" "git+https://github.com/ultralytics/CLIP.git"
    ```

  本任务命令都用 `$PY`。交付后或失败退出前只删 `$SamVenv`。CPU → `--device cpu --no-half`。

---

### 0.2 权重（未就绪不得跑）

  **先向用户确认有无指定模型**（`.pt` 绝对路径，或「无 / 用官方 sam3.pt」）。未得到答复前，**禁止搜盘、禁止下载**。

  - **有指定** → 检查文件可读。可用则作为 `--weights`（可拷一份进 `WEIGHTS_DIR` 留档，不覆盖已有同名）。不要再搜。
  - **无指定** → 再走下面 1 → 2。

  默认网盘（`sam3.pt`）：[百度云](https://pan.baidu.com/s/1G7rFifymejbvUS9GchrGzQ?pwd=pmix)　提取码 **`pmix`**  
  文档：[Ultralytics SAM 3](https://docs.ultralytics.com/models/sam-3/)  
  备选：[huggingface.co/facebook/sam3](https://huggingface.co/facebook/sam3)（须申请访问）

  `WEIGHTS_DIR`：`PKG_ROOT/../../_weights`（即 `tools/1-DataEngine/_weights`）。没有则建。

  **1.（仅无指定）本机已有 `sam3*.pt`** → 拷贝进 `WEIGHTS_DIR`（已在则跳过，不覆盖）。只搜这些根，**不要扫整盘**：

  - `WEIGHTS_DIR`
  - 用户主目录 `Downloads/`、`Desktop/`
  - Ultralytics 缓存：`~/.ultralytics/`（Windows 另加 `%USERPROFILE%\AppData\Roaming\Ultralytics`）

    ```bash
    cp "<found>/sam3.pt" "$WEIGHTS_DIR/sam3.pt"
    ```

  命中多份 → 列出路径与大小，让用户选。

  **2.（仅无指定且 `WEIGHTS_DIR` 仍缺 `sam3.pt`）** → **停**，把网盘地址和提取码发给用户，请自行下载到 `$WEIGHTS_DIR/sam3.pt`（或给出绝对路径）后再继续。**禁止** `curl` / `wget` 百度云（需登录）。不要用 yolo 权重顶替。HF 仅当用户明确说走 HF 时再用。

  无指定且已找到时 `--weights` 用 `$WEIGHTS_DIR/sam3.pt`。须为推理权重，不要把 trainer `best.pt` 直接当 `--weights`。

---

## 1 向用户确认（未确认不得跑）

    ```markdown
    请确认后回复「按此开跑」（改括号即可）：

    1. 数据集目录：[绝对路径；含 images/]
    2. 任务：[detect | segment]
    3. 权重：[指定绝对路径 | 无 → 本机 / 百度云 sam3.pt，提取码 pmix]
    4. prompt：[英文概念，逗号分隔，如 person,boat]
    5. 写出：随 task（detect→jsons-det-pre | segment→jsons-seg-pre）
    6. conf：[0.45]
    7. 试跑样本数：[12]
    8. device：[0 | cpu]
    ```

---

## 2 执行

  工作目录：`PKG_ROOT`。解释器 = [§0.1] 的 `$PY`。`--prompt` 必填。

### 2.1 sample 叠图检阅

    ```bash
    "$PY" util/batch_prelabel_json.py sample --dataset "<data_root>" --weights "$WEIGHTS_DIR/sam3.pt" --task detect --prompt "person,boat" --n 12 --seed 0 --device 0
    # segment 只改 --task segment
    ```

  完成后把 **`draft/detseg-sam3/cache/sample/vis/`** 给用户看。

  - **注意**：**此处必须停止**。用户说「直接全量」→ §2.2。vis 不像样 → 说明后停，不要硬 run。

### 2.2 全量写盘

    ```bash
    "$PY" util/batch_prelabel_json.py run --dataset "<data_root>" --weights "$WEIGHTS_DIR/sam3.pt" --task detect --prompt "person,boat" --device 0
    "$PY" util/batch_prelabel_json.py run --dataset "<data_root>" --weights "$WEIGHTS_DIR/sam3.pt" --task detect --prompt car --jsons jsons-det-pre-car --device 0
    "$PY" util/batch_prelabel_json.py run --dataset "<data_root>" --weights "$WEIGHTS_DIR/sam3.pt" --task segment --prompt "person,boat" --device 0
    ```

  detect → `jsons-det-pre/`（rectangle）；segment → `jsons-seg-pre/`（polygon）。已有非空 json 默认跳过；覆盖须 `--force`。CPU：`--device cpu --no-half`。

---

## 3 工具索引

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 权重 | `../../_weights/` | `sam3.pt`（[百度云 pmix](https://pan.baidu.com/s/1G7rFifymejbvUS9GchrGzQ?pwd=pmix)） |
  | 入口 | `util/batch_prelabel_json.py` | `sample` / `run` |
  | 金字塔 | `customer/image-260811-pyramidlabel/` | 不在本叶 |
  | 基类互补 | `customer/image-260827-class-complement/` | 不在本叶 |

---
