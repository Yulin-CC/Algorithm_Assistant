---
name: tool-annotation
description: >-
  把检测框裁进 img_crop/<类名>/，人工挪文件夹改类后回写 LabelMe json 或 YOLO txt。
  Use when the user says 改标签、换类别、纠错标注、BoxCrop、裁框改类, or names tool-annotation.
---

# 🏷️ Tool-Annotation（裁框改类）

  - **概述**: 用户要对已有检测框改类别时触发。先裁框到类名文件夹，等人挪完再回写 GT。不预标、不训练。
  - **日期**: 2026-10-21

---

## 0 执行前检查

  未确认数据集路径前，不裁图、不改 GT。

  - **仓库根 `REPO`**：`skills/` 的上一级。
  - **工具**：`REPO/tools/1-DataEngine/0-Data-Organize/util/BoxCrop_cls.py`。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。`NEED_TORCH=no`，`PKGS=tqdm pillow`，slug=`organize`。有 `--yaml` 时再加 `pyyaml`。
  - **数据根**：必须由用户给出。自动识别：有 `jsons/` → LabelMe；有 `labels/`（或 `detect/labels`）→ YOLO。
  - **不做**：不改框坐标、不跑模型、crop 后未等人确认不得 `update`。

---

## 1 向用户确认

    ```markdown
    请确认后回复「按此开跑」：

    1. 数据集：[绝对路径]
    2. 格式：[auto | labelme | yolo]
    3. 扩展倍数：[1.5]
    4. YOLO 类名表：[classes.yaml | 无（文件夹用数字 ID）]
    ```

---

## 2 落盘

  相对数据集根目录：

    ```text
    images/
    jsons/          # LabelMe
    labels/         # YOLO
    img_crop/<类名>/{stem}_{序号:02d}.jpg
    ```

  - **注意**：裁图文件名不要改。把图挪到正确类文件夹即改类；删文件或放进 `_` 开头文件夹（如 `_drop`）= 丢掉该框。新建文件夹名即新类名（YOLO 须能在 yaml 里对上，或文件夹本身是数字 ID）。

---

## 3 执行

  工作目录：`REPO/tools/1-DataEngine/0-Data-Organize`。解释器 = `$PY`。

### 3.1 裁框

    ```bash
    "$PY" util/BoxCrop_cls.py --Path "<data_root>" --status crop --format auto --expand_ratio 1.5
    ```

  YOLO 要用类名文件夹时加 `--yaml classes.yaml`。完成后把 `img_crop/` 交给用户，**停止**。

### 3.2 人工改类

  等用户明确说「分完了 / 可以回写」。期间不跑 update。

### 3.3 回写

    ```bash
    "$PY" util/BoxCrop_cls.py --Path "<data_root>" --status update --format auto
    ```

  LabelMe 直接改 `jsons/` 的 `shapes[].label`（缺裁图的 shape 删除）。YOLO 直接覆盖 `labels/`。不另写 bak。

---

## 4 工具索引

  - 工具根目录：`REPO/tools/1-DataEngine/0-Data-Organize/`

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 通用 | `util/BoxCrop_cls.py` | 检测框 → `img_crop/<类>/`；按文件夹回写 json / txt |
