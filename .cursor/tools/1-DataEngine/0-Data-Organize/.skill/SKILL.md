---
name: data-organize
description: >-
  Organize datasets into YOLO, YOLOE open-set, CD, or YOLOE-val layouts.
  Open-set labels use jsons-GD_<model>; the only wired model is yoloe
  (jsons-GD_yoloe). Use when agent-dataengine dispatched capability=organize,
  or the user says 整理数据集, 转 YOLO, Grounding 整理, 变化检测划分.
disable-model-invocation: true
---

# 数据集整理（`0-Data-Organize`）

  - **概述**: 把已有数据整理成可训练/可发布布局。确认规范 → 是否重命名 → 缺什么补什么。开集目录为 `jsons-GD_<model>/`，当前只接 `yoloe`。不预标、不训练。
  - **日期**: 2026-11-12

---

## 0 执行前检查

  - **触发**：整理数据集、转 YOLO/YOLOE 开集/CD、划分 train/val；由 `agent-dataengine` 指定 `capability=organize`。
  - **本包根目录 `PKG_ROOT`**：`.skill/` 的上一级。
  - **数据根目录 `data_root`**：必须由用户给出，禁止猜测。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。默认 `NEED_TORCH=no`，`PKGS=pyyaml tqdm pillow opencv-python numpy`，venv slug=`organize`。仅 `grounding_generate_cache.py` 需要 `NEED_TORCH=yes` + `ultralytics`。
  - **不做**：不下载权重、不跑预标叶、不生成 SAM mask（本包无该脚本）。不执行 `uv cache clean`。

---

## 1 向用户确认

    ```markdown
    请确认后回复「按此开跑」：

    1. 数据集目录：[绝对路径]
    2. 目标规范：[YOLO | YOLOE 开集 | CD-校验 | CD-训练 | YOLOE val]
    3. 任务（YOLO / YOLOE 开集）：[detect | segment]
    4. 是否按规范重命名：[否（默认）| 是 → 范式 Train-[project]-[date]-xxxxx]
    5. classes.yaml：[路径 | 无]
    ```

  未确认不得转换、划分、覆盖写盘。重命名须成对同步（images↔labels、A↔B↔label、images↔jsons），并更新 LabelMe `imagePath`。

---

## 2 执行

  工作目录：`PKG_ROOT`。解释器 = tool-build_env 的 `$PY`。已合规则跳过；不合规则最小补齐。子目录平铺、无二级 `train/`/`val/`（划分只用 txt 列表，除非用户要 `--mode dir`）。

  完成后按对应 §4 检查流程核对：文件数、basename 对齐、train/val。

---

## 3 工具索引

  全部在 `util/`。

  | 规范 | 工具 | 用途 |
  | --- | --- | --- |
  | YOLO | `convert_json2txt.py` | LabelMe → `labels/`（`--task detect\|segment`） |
  | YOLO | `convert_xml2txt.py` | VOC XML → `labels/` |
  | YOLO | `convert_txt2json.py` | YOLO txt → LabelMe |
  | YOLO | `convert_txt2xml.py` | YOLO txt → VOC XML |
  | YOLO | `convert_labelme2coco.py` | LabelMe → 多类 COCO bbox |
  | YOLO | `convert_coco2txt.py` | COCO → `labels/` |
  | YOLO | `split.py --layout yolo` | `train.txt` / `val.txt` |
  | YOLO | `yolo_check_label.py` | 子集类别覆盖表 |
  | 通用 | `merge_jsons_det_segm.py` | `jsons-det-pre` + `jsons-seg-pre` → `jsons/` |
  | YOLOE | `convert_json2coco.py` | `jsons-GD_yoloe/` → `*_segm.json`（默认该目录） |
  | YOLOE | `convert_geoai2coco.py` | LabelMe/rectangle + caption → `*_segm.json` |
  | YOLOE | `grounding_generate_cache.py` | `train_segm.json` → `.cache`（须 ultralytics） |
  | CD 校验 | `cd_register.py` | 双时相配准 |
  | CD 校验 | `cd_image_tiling.py` | cropped 切片 |
  | CD 训练 | `convert_json2mask.py` | json polygon → `label/` mask |
  | CD 训练 | `split.py --layout cd` | `train.txt` / `val.txt`（文件名） |

    ```bash
    "$PY" util/convert_json2txt.py --dataset "<data_root>" --yaml classes.yaml --task detect
    "$PY" util/split.py --dataset "<data_root>" --layout yolo --mode txt --split-ratio 0.9 --seed 42
    "$PY" util/split.py --dataset "<data_root>" --layout cd --mode txt
    ```

  - **注意**：多年份共用同一份 `names` 顺序。bbox 补 polygon 不在本叶（无 SAM mask 脚本）。

### 3.1 弱标签矫正

  由 `skills/tool-gt_rectify/SKILL.md` 调度。本叶只裁图、落盘和评测，不加载权重。

  | 工具 | 用途 |
  | --- | --- |
  | `square_crop.py` | 框外扩 2 倍，按长边裁正方形 |
  | `gt_rectify.py dump` | 未命中预测写入 `误检/真误检` |
  | `gt_rectify.py apply` | `误检/假误检` 追加为 `{类}_m` |
  | `weak_label_report.py` | 强/弱标签的正检、误检、漏检 |

    ```bash
    "$PY" util/square_crop.py --image a.jpg --box 10 20 110 60 --out b.jpg --expand 2 --draw
    "$PY" util/gt_rectify.py dump --gt-dir "<gt>" --pre-dir "<pre>" --images "<images>" --out "<scene>/repro/<模型>/<版本>/误检" --alias alias.yaml
    "$PY" util/gt_rectify.py apply --out "<scene>/repro/<模型>/<版本>/误检" --dry-run
    "$PY" util/weak_label_report.py --gt-dir "<gt>" --pre-dir "<pre>" --alias alias.yaml --iou 0.30
    ```

---

## 4 数据集规范

### 4.1 YOLO

  必须：`images/`、`labels/`、`train.txt`、`val.txt`。可选 `jsons/`、`annotations/`。

  检查：确认 detect/segment → 无图 ❌ → 缺 labels 则 json/xml/coco 转换 → 缺划分则 `split.py --layout yolo` → images 与 labels basename 一致；txt 内路径可解析。

  `train.txt` 行格式：`./images/xxx.jpg`。detect txt：`cls cx cy w h`；segment：`cls x1 y1 ...`。

### 4.2 YOLOE 开集

  目录名是 `jsons-GD_<model>/`。当前 `<model>=yoloe`，源目录 `jsons-GD_yoloe/`。以后的模型另建后缀目录，不写入本套 `train_segm.json` / `train_segm.cache`。

  必须：`images/`、`jsons-GD_yoloe/`、`train_segm.json`、`train_segm.cache`。yaml 只写 `img_path`，根目录固定读这两个训练文件名。`convert_json2coco.py` 默认读 `jsons-GD_yoloe/`。见到 `jsons-GD/` 先改成这个名字，不覆盖已有目录。

  检查：源里有 polygon 可直接合；仅 rectangle 则合 bbox JSON，**本叶不补 SAM mask**（用户另开 SAM 或已有 polygon）。cache 用 `grounding_generate_cache.py`（先 uv 装 ultralytics）。

### 4.3 CD

  先确认 **校验** | **训练**。

  **校验终态**：只留成对 `A/`、`B/`。流程：`cd_register.py` → cropped → `cd_image_tiling.py` → 替换根目录 A/B → 删中间目录。

  **训练**：`A/`、`B/`、`label/`（0/255 png）、`train.txt`、`val.txt`（每行文件名）。缺 mask 用 `convert_json2mask.py`（仅 polygon）；缺划分 `split.py --layout cd`。三处 basename 一致。

### 4.4 YOLOE val

  必须：`images/`、`labels/`（segment txt）、`val.txt`、`annotations/lvis_v1_val.json`。多集是否合并须先问。开集源为 `jsons-GD_yoloe/`。禁止与对应 YOLOE 开集训练集 basename 重叠。本叶无独立 LVIS 生成脚本：有 labels 可写 `val.txt`；缺 JSON 则停并说明。

---
