---
name: standard-dataset-merge
description: >-
  Normalizes a dataset toward YOLO, YOLOE open-set, CD, or YOLOE val.
  Open-set labels use jsons-GD_<model>; the only wired model is yoloe
  (jsons-GD_yoloe). Use when the user says 整理数据集, 规范化数据集,
  数据集合并, Grounding 整理, or convert labels to a train/publish spec.
---

# 📦 数据集整理规范

  - **概述**: 当用户要求**整理数据集**、**规范化数据集**、**做数据集合并/转换**时，按本 Skill 执行：确认路径与规范类型 → **确认是否重命名** → 检查合规性 → 调用工具补齐 → 最终校验并报告。开集目录统一为 `jsons-GD_<model>/`，当前只接 `yoloe`。CD 须先确认 **校验** 或 **训练**；YOLOE val 走 [4.4]。
  - **日期**: 2026-11-12

---

## 0 执行前检查

  - **触发场景**：「帮我做一下数据集整理」「整理成 YOLO / YOLOE 开集 / CD / YOLOE val 规范」等。
  - **目标**：将目标数据集整理到可用于 **[训练]** 或 **[发布]** 的程度。
  - **原则**：已合规则跳过；不合规则最小改动补齐；关键字段符合即可，不要求逐字节一致；**合规检查由 Agent 按 §4.x.2 检查流程执行**，不依赖独立校验脚本。

---

## 1 执行步骤

  **(1)** 确认数据集路径；用户未提供则询问。

  **(2)** 分析路径下文件结构，判断单个或批量处理。

  **(3)** 向用户确认目标规范：

  - **a** YOLO → [4.1 规范-YOLO 数据集]
  - **b** CD（变化检测）→ 再确认 **校验** | **训练** → [4.2 规范-CD 数据集]
  - **c** YOLOE 开集 → [4.3 规范-YOLOE 开集]；源目录 `jsons-GD_yoloe/`
  - **d** YOLOE val → [4.4 规范-YOLOE val 数据集]；若路径下有**多个**子数据集，须先确认是否合并（见 §4.4.2）

  **(4)** **执行数据规范前**，向用户确认是否对文件做重命名：

  - **a** 默认询问：「是否按规范重命名图像/标注（及成对同名文件）？」须得到明确答复后再继续。
  - **b** 用户选择 **是** → 再确认命名范式（默认 `Train-[project_name]-[date]-xxxxx`，扩展名保持原样或按规范统一）；成对文件（如 `images/`↔`labels/`、`A/`↔`B/`↔`label/`、`images/`↔`jsons/`）须同步改名，保持 basename 一致；标注内引用路径（如 Labelme `imagePath`）一并更新。
  - **c** 用户选择 **否** → 跳过重命名，保持现有文件名进入下一步。
  - **d** 未确认前不得开始转换、划分或覆盖写盘。

  **(5)** 检查是否已符合目标规范：

  - **a** 工具目录：`REPO/tools/1-DataEngine/0-Data-Organize/util/`（`REPO` 为本工作区 `.cursor/`）。不在该目录里的工具，按 [3 工具索引] 的说明处理；确需外部工具时再询问用户路径。
  - **b** 调用 [3 工具索引] 中对应脚本逐一调整，后台监督执行。
  - **c** 完成后由 Agent 按对应规范的 **检查流程**（§4.1.2 / §4.2.1 / §4.2.2 / §4.3.2 / §4.4.2）做最终核对，向用户报告并打印数据集统计（文件数、train/val 划分等）。

---

## 2 通用约束

  - 各数据子目录下应为**平铺文件**，无二级目录；如有 `train/`、`val/` 等，分析后将文件拢到上级并删除空目录。
  - 标注软件产物（`annotations/`、`jsons/`、`json/`）仅作中间格式，合规后可保留，不作为最终训练必需项（**YOLOE val** 的 `annotations/lvis_v1_val.json` 除外，见 [4.4]）。
  - 格式不合但关键字段可识别时，先尝试已有工具；无法转换时再分析结构并考虑新建工具。
  - 开集标注目录统一为 `jsons-GD_<model>/`，与 `images/` 并排。`<model>` 是消费这套标签的模型名。当前只接 `yoloe`，目录为 `jsons-GD_yoloe/`。
  - 以后的模型沿用同一前缀，单独建目录、单独转换。不把别的模型的标注写入 `jsons-GD_yoloe/`，也不改 YOLOE 已有的 `train_segm.json` / `train_segm.cache`。
  - 磁盘上若还有无后缀的 `jsons-GD/`，直接改名为 `jsons-GD_yoloe/`。LabelMe 中间目录 `jsons/` 不改名。

---

## 3 工具索引

  全部在 `REPO/tools/1-DataEngine/0-Data-Organize/util/`（`REPO` = 本工作区 `.cursor/`），解释器见该叶 `.skill/SKILL.md`。旧的 `/path/to/home/1-project/1-PROCESS` 与本表旧写法 `tools/`、`utils/` 均已废弃：服务器上该目录不存在，`cd_dataset_division.py`、`yolo_dataset_division.py` 也从未有过，划分一律用 `split.py`。

  | 规范 | 工具 | 用途 |
  |------|----------|------|
  | YOLO | `convert_json2txt.py --task detect\|segment` | Labelme JSON → `labels/` |
  | YOLO | `convert_xml2txt.py` | VOC XML → `labels/` |
  | YOLO | `convert_labelme2coco.py` | LabelMe → **多类** COCO bbox JSON（供 SAM / `convert_coco2txt`） |
  | YOLO | `convert_coco2txt.py` | COCO instances JSON → `labels/`（`detect` / `segment`） |
  | YOLO | `convert_txt2json.py` / `convert_txt2xml.py` | YOLO txt → LabelMe / VOC（反向） |
  | YOLO | `split.py --layout yolo` | 生成 `train.txt` / `val.txt` |
  | YOLO | `yolo_check_label.py` | 子集类别覆盖表 |
  | 通用 | `merge_jsons_det_segm.py` | `jsons-det-pre` + `jsons-seg-pre` → `jsons/` |
  | YOLOE | `convert_json2coco.py` | `jsons-GD_yoloe/` → `train_segm.json`（默认 `--jsons-dir jsons-GD_yoloe`） |
  | YOLOE | `convert_geoai2coco.py` | LabelMe `description_en` → caption span，再写入 `train_segm.json` |
  | YOLO / YOLOE | `tools/generate_sam_masks.py` | 对 COCO JSON 中的 **bbox** 补 `segmentation`，输出 `*_segm.json` |
  | YOLOE | `grounding_generate_cache.py` | 由 `train_segm.json` 生成 `train_segm.cache` |
  | CD 校验 | `cd_register.py` | 双时相配准 → `A_cropped/` `B_cropped/` 等 |
  | CD 校验 | `cd_image_tiling.py` | 对 cropped 切片 → 输出 `A/` `B/` 子图 |
  | CD 训练 | `convert_json2mask.py` | json/ → label/ mask（仅 polygon；空 shapes 出全 0 png） |
  | CD 训练 | `split.py --layout cd` | 生成 `train.txt` / `val.txt`（每行文件名，以 A 侧为准） |
  | 弱标签 | `square_crop.py` / `gt_rectify.py` / `weak_label_report.py` | 见 `skills/tool-gt_rectify/SKILL.md` |

  - **注意**：执行前确认 `classes.yaml`（YOLO）等依赖文件是否存在；多子目录/多年份共用**同一份** `names` 顺序，保证 class id 一致。
  - **注意**：`generate_sam_masks.py` 输入是带 **bbox** 的 COCO JSON（`--json-path`）+ `images/`（`--img-path`），**不是** `.cache`。默认权重优先 `yoloe-main/weights/sam2.1_hiera_large.pt`，可用 `--checkpoint` 覆盖；默认 `--gpus 0,1,2,3`。密框图请加 **`--batch`**（单图框很多时按块推理，降低显存峰值）。调用前确认 **sam2** 环境可用。
  - **注意**：`convert_json2coco.py` 默认读 `jsons-GD_yoloe/`。`convert_geoai2coco.py` 仍读 LabelMe `jsons/`，再写成训练 JSON。
  - **注意**：`grounding_generate_cache.py` **唯一依赖 ultralytics**；调用前须询问用户 **yoloe 环境是否已装好**，确认后在 yoloe 环境中执行：

    ```bash
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate yoloe
    python "<REPO>/tools/1-DataEngine/0-Data-Organize/util/grounding_generate_cache.py" \
      --json-path /path/to/train_segm.json \
      --img-path /path/to/images
    ```

    可用 `conda run -n yoloe python -c "import ultralytics"` 快速验证环境；未安装则提示用户先配置 yoloe，**不得**用系统 Python 强行运行。

---

## 4 数据集规范

### 4.1 规范-YOLO 数据集

#### 4.1.1 文件夹结构

  ⭐ 为必须存在的项。

  ```markdown
  ├── dataset
  │   ├── annotations/       # 标签[.xml]
  │   │   ├── `xxx.xml`
  │   │   └── ...
  │   ├── images/            # ⭐ 图像[.jpg]/[.png]
  │   │   ├── `xxx.jpg`
  │   │   └── ...
  │   ├── jsons/             # 标签[.json] 标注软件产生
  │   │   ├── `xxx.json`
  │   │   └── ...
  │   ├── labels/            # ⭐ 标签[.txt]
  │   │   ├── `xxx.txt`
  │   │   └── ...
  │   ├── `train.txt`        # ⭐ 训练读取文件
  │   └── `val.txt`          # ⭐ 验证读取文件
  ```

#### 4.1.2 检查流程

  - 向用户确认任务类型：`detect` | `segment`。
  - 最小合规：`images/`、`labels/`、`train.txt`、`val.txt`。
    - 无 `images/` → 报错 ❌
    - 缺 `labels/` 或划分文件 → 调用工具生成
  - 有 `annotations/` 或 `jsons/` → 检查关键字段，符合则转换生成 `labels/`。
      - **a** `detect`：`rectangle` / bbox → `convert_json2txt.py --task detect`（或 XML / COCO 对应工具）。
      - **b** `segment` 且源为 **polygon** → `convert_json2txt.py --task segment`（或 `convert_coco2txt.py --task segment`）。
      - **c** `segment` 但源仅有 **rectangle / bbox**（无 polygon）→ **可选**走 SAM 补分割后再转 YOLO txt：
        - **(a)** `convert_labelme2coco.py` + 共用 `classes.yaml` → 多类 `*_bbox.json`（保留真实 categories）
        - **(b)** 确认 sam2 可用后：`generate_sam_masks.py --gpus 0,1,2,3 --batch` → `*_bbox_segm.json`
        - **(c)** `convert_coco2txt.py --task segment` → `labels/`（SAM 过滤掉的实例可丢弃；无有效 mask 的图可无 txt，划分时只收成对样本）
        - **(d)** 若用户明确接受「框当 4 点伪 mask」、不跑 SAM，再另议；默认优先询问是否用 SAM
        - **(e)** 多年份/子目录先逐年整理，合并放到第二阶段；合并前 class id 必须一致
  - 最终检查：
    - `images/` 与 `labels/` 的 **数量** 和 **basename** 一致
    - `train.txt` / `val.txt` 中路径均有对应图像和标签
    - 若 §1**(4)** 已确认重命名：命名符合约定范式（默认 `Train-[project_name]-[date]-xxxxx`）
  - 通过 → ✅

#### 4.1.3 数据结构示例

  - **images/**：图像为 `.jpg` / `.png`；不合规则统一转 `.jpg`。

  - **annotations/xxx.xml**

    ```xml
    <annotation>
    <folder>DATA</folder>
    <filename>Train-Fall_elevator01-2509-0009.jpg</filename>
    <size>
       <width>1920</width>
       <height>1080</height>
       <depth>3</depth>
    </size>
    <object>
       <name>fall</name>
       <bndbox>
          <xmin>700</xmin><ymin>402</ymin>
          <xmax>898</xmax><ymax>744</ymax>
       </bndbox>
    </object>
    </annotation>
    ```

  - **jsons/xxx.json**（Labelme）

    ```json
    {
      "version": "0.1.4",
      "shapes": [
        {
          "label": "person",
          "points": [[112.0, 73.0], [175.0, 73.0], [175.0, 187.0], [112.0, 187.0]],
          "shape_type": "rectangle"
        },
        {
          "label": "person",
          "points": [[124.0, 73.0], [121.0, 75.0], ...],
          "shape_type": "polygon"
        }
      ],
      "imagePath": "..\\images\\Public_VOC_0016.jpg",
      "imageHeight": 333,
      "imageWidth": 500
    }
    ```

  - **labels/xxx.txt**

    ```markdown
    # detect
    25 0.475759 0.414523 0.951518 0.672422

    # segment
    0 0.381688 0.589417 0.341203 0.585667 0.316719 0.581896 ...
    ```

  - **train.txt | val.txt**

    ```markdown
    ./images/000000182611.jpg
    ./images/000000182612.jpg
    ...
    ```

---

### 4.2 规范-CD 数据集

  选 CD 后先确认分支：**校验** | **训练**。

#### 4.2.1 校验规范

  **终态结构**（仅保留这两项；过程目录用完即删）：

  ```markdown
  ├── dataset
  │   ├── A/                   # ⭐ 时相 A 子图
  │   └── B/                   # ⭐ 时相 B 子图（与 A 同名成对）
  ```

  **检查流程**：

  - 起点：根目录有同名成对的 `A/`、`B/`；缺一则 ❌。
  - **(1)** `cd_register.py` → 产出 `A_cropped/`、`B_cropped/`（需开启裁剪重叠区）。
  - **(2)** `cd_image_tiling.py` 对 cropped 切片 → 临时目录中的 `A/`、`B/` 子图。
  - **(3)** 用切片结果**替换**根目录 `A/`、`B/`。
  - **(4)** 删除中间目录：`A_cropped/`、`B_cropped/`、`B_registered/`、`warp_meta/`、切片临时目录等。
  - 最终：`A/` 与 `B/` basename 一致 → ✅。

#### 4.2.2 训练规范

  **文件夹结构**：

  ```markdown
  ├── dataset
  │   ├── A/                   # ⭐ 时相 A[.jpg]/[.png]
  │   ├── B/                   # ⭐ 时相 B（与 A 同名）
  │   ├── label/               # ⭐ 变化 mask[.png]
  │   ├── json/                # 标注中间产物（可选）
  │   ├── `train.txt`          # ⭐
  │   └── `val.txt`            # ⭐
  ```

  **检查流程**：

  - 默认假定 `A/`、`B/` 已是校验终态；无则 ❌ 或请用户先走校验分支。
  - 最小合规：`A/`、`B/`、`label/`、`train.txt`、`val.txt`。
    - 缺 `label/` 或划分文件 → 调用工具生成（mask 用 `convert_json2mask.py`；划分用 `split.py --layout cd`）
  - 有 `json/` → 转 `label/` mask（`convert_json2mask.py`；仅 polygon；扩展字段可选）。
  - 最终：`A/`、`B/`、`label/` basename 一致（label 为 `.png`）；划分列表中文件名三处均有对应 → ✅。

  **数据结构要点**：

  - **label/**：二值灰度，`0`=背景，`255`=变化。
  - **json/**：Labelme polygon；`imageHeight` / `imageWidth` / `shapes` 即可；`change_detection` 等扩展字段可选。
  - **train.txt | val.txt**：每行一个文件名（以 `A/` 侧为准，如 `xxx.jpg`）。

---

### 4.3 规范-YOLOE 开集

#### 4.3.1 文件夹结构

  ```markdown
  ├── dataset
  │   ├── images/                  # ⭐ 图像[.jpg]/[.png]
  │   │   ├── `xxx.jpg`
  │   │   └── ...
  │   ├── jsons-GD_yoloe/          # ⭐ 每图一条 YOLOE grounding JSON
  │   │   ├── `xxx.json`
  │   │   └── ...
  │   ├── `train_segm.json`        # ⭐ 合并结果（YOLOE 读死这个文件名）
  │   └── `train_segm.cache`       # ⭐ 训练缓存（YOLOE 读死这个文件名）
  ```

  - **注意**：训练 yaml（`data/0-Grounding.yaml`）只需 `img_path`（指向 `images/`）；YOLOE 在数据集根目录固定读 `train_segm.json` / `train_segm.cache`。不要再写 `json_file`。新模型不要往这两个文件里写。
  - **注意**：人工 LabelMe 仍可留在 `jsons/`。那是中间格式，合入前须变成带 `caption` / `tokens_positive` 的 `jsons-GD_yoloe/`。
  - **注意**：若仍有 `jsons-GD/`，先改名为 `jsons-GD_yoloe/` 再合并。不覆盖已有的 `jsons-GD_yoloe/`。

#### 4.3.2 检查流程

  - 向用户确认任务类型：`detect` | `segment`。
  - 最小合规：`images/`、`train_segm.json`、`train_segm.cache`。

    - 无 `images/` → 报错 ❌
    - 缺合并 JSON 或 cache → 调用工具生成

  - 有 `jsons-GD_yoloe/` → 检查 YOLOE 关键字段（`caption`、`tokens_positive`），符合则调用转换工具合并生成大 JSON 及 cache。`convert_json2coco.py` 默认读该目录。
      - **a** `train_segm.json`：先确认源为 polygon | rectangle。已有 polygon 可直接合并；仅有 bbox/`rectangle` 时，先合并出带 bbox 的 COCO JSON，再调用 `generate_sam_masks.py`（见 [3 工具索引]）补 `segmentation`（输入为该 JSON，**非** `.cache`；事先确认 sam2 可用）。终态文件名固定为 `train_segm.json`。
      - **b** `.cache`：基于已含 `segmentation` 的 `train_segm.json` 运行 `grounding_generate_cache.py`（见 [3 工具索引]），生成 `train_segm.cache`（事先确认 yoloe 可用）。
  - 最终检查：
    - `images/` 与 `jsons-GD_yoloe/` 的 **数量** 和 **basename** 一致
    - `train_segm.json` 中 `images[].file_name` 对应 `images/` 实际文件
    - 标注短语来自 `caption[tokens_positive]`
  - 通过 → ✅

#### 4.3.3 数据结构示例

  - **images/**：图像为 `.jpg` / `.png`；不合规则统一转 `.jpg`。

  - **`train_segm.json`**

    ```json
    {
      "info": [],
      "licenses": [],
      "categories": [{"id": 1, "name": "object", "supercategory": "object"}],
      "images": [
        {
          "id": 0,
          "file_name": "3359636318.jpg",
          "height": "334",
          "width": "500",
          "original_img_id": 3359636318,
          "sentence_id": 0,
          "caption": "Two people are talking outside of the video game shop ...",
          "tokens_negative": [[0, 91]],
          "tokens_positive_eval": [[[0, 10]], [[34, 53]], ...],
          "dataset_name": "flickr"
        }
      ],
      "annotations": [
        {
          "id": 0,
          "image_id": 0,
          "category_id": 1,
          "bbox": [144.0, 166.0, 64.0, 168.0],
          "segmentation": [[163.0, 168.0, ...]],
          "tokens_positive": [[0, 10]],
          "iscrowd": 0,
          "area": 10752.0
        }
      ]
    }
    ```

  - **jsons-GD_yoloe/xxx.json**（按物理图拆分，每图多条 caption）

    ```json
    {
      "info": [],
      "categories": [{"id": 1, "name": "object", "supercategory": "object"}],
      "images": [
        {
          "id": 0,
          "file_name": "1000092795.jpg",
          "height": "500",
          "width": "333",
          "original_img_id": 1000092795,
          "sentence_id": 0,
          "caption": "Two young guys with shaggy hair look at their hands ...",
          "tokens_negative": [[0, 83]],
          "tokens_positive_eval": [[[0, 14]], [[20, 31]], ...],
          "dataset_name": "flickr"
        }
      ],
      "annotations": [
        {
          "id": 0,
          "image_id": 0,
          "category_id": 1,
          "bbox": [180.0, 125.0, 26.0, 31.0],
          "segmentation": [[192.0, 124.0, ...]],
          "tokens_positive": [[20, 31]],
          "iscrowd": 0,
          "area": 806.0
        }
      ]
    }
    ```

  - **注意**：`images[].id` 按 caption 条目编号（如 Flickr 每图 5 句 → 5 条 image 记录）。

---

### 4.4 规范-YOLOE val 数据集

  开集验证集：DataLoader 读 YOLO `labels/`，官方 AP 读 LVIS JSON。`is_lvis` 是评测协议开关，不是公开 LVIS 数据集。

#### 4.4.1 文件夹结构

  ```markdown
  ├── dataset
  │   ├── images/                         # ⭐ 图像[.jpg]/[.png]，平铺
  │   ├── labels/                         # ⭐ YOLO segment txt（与图像同 basename）
  │   ├── jsons-GD_yoloe/                 # 开集源（caption + tokens_positive；可保留）
  │   ├── annotations/
  │   │   └── `lvis_v1_val.json`          # ⭐ 官方评测 GT（文件名写死）
  │   └── `val.txt`                       # ⭐ ./images/xxx.jpg，覆盖全部 val 图
  ```

  配套 yaml（如 `data/val-yolo_dataset/*.yaml`）：`path` 指向本根目录；`val: val.txt`；`names` 与 label class id 对齐（0-based）。

#### 4.4.2 检查流程

  - 向用户确认：开集短语 val（`jsons-GD_yoloe` / caption）还是闭环类名 val（`jsons-segm` / `label`）。默认开集。若仍有 `jsons-GD/`，先改名为 `jsons-GD_yoloe/`。
  - **多个数据集时**须再确认是否合并（评测只读一份 `annotations/lvis_v1_val.json`，合并才符合当前训练 val 形态）：
    - **a** 默认询问：「多个 val 集合并成一份 `images/`+`labels/`+`val.txt`+`lvis_v1_val.json` 吗？」未确认前不得写盘。
    - **b** **是** → 拢到同一根目录（平铺、basename 冲突则加前缀）；`names` 全局去重对齐 class id；生成**一份** `val.txt` 与 `lvis_v1_val.json`；yaml 只指向该根。
    - **c** **否** → 各集单独整理、各写一份 JSON 与 yaml（当前 `0-YOLO.yaml` 的 val 只能挂其中一份）。
  - 最小合规：`images/`、`labels/`、`val.txt`、`annotations/lvis_v1_val.json`、yaml `names`。
    - 无 `images/` → ❌
    - 缺 `labels/` → 由源 json 转 YOLO segment txt
    - 缺 `val.txt` → 列出全部 `images/`（`./images/xxx.jpg`）
    - 缺 LVIS JSON → 由 `labels/` + `names` 生成（`category_id = cls_id + 1`，`image_id` 为整数，与 `file_name` 可互查）
  - 开集源为 `jsons-GD_yoloe`：短语取 `caption[tokens_positive]`，一图多 caption 合并进同一 txt；同 phrase+近似框去重。
  - **禁止**与对应 YOLOE 开集训练集图像 basename 重叠；有重叠则从训练侧删除并重出 `train_segm.json` / `.cache`。
  - 最终检查：
    - `images/` 与 `labels/` 数量、basename 一致；`val.txt` 路径均可解析
    - yaml `names` 条数 = 独特短语数；label 中 `cls_id` 均落在 `0 .. nc-1`
    - `lvis_v1_val.json`：`images[].file_name` 对得上 `images/`；`category_id` 从 1 起
  - 通过 → ✅

#### 4.4.3 数据结构要点

  - **labels/xxx.txt**（segment，归一化）：`cls x1 y1 x2 y2 ...`；`cls` 与 yaml `names` 同序。
  - **val.txt**：`./images/GEOAI-Car-210602-0059.jpg`
  - **`lvis_v1_val.json`**：`categories` / `images` / `annotations`；`bbox` 为 xywh 像素；`segmentation` 为绝对坐标 polygon；`categories[].frequency` 按本集出现次数标 `r`/`c`/`f`（供 APr/APc/APf）。
  - **注意**：训练 yaml 开 `is_lvis: true` 后，进图靠 `labels/`，最终 AP 靠本 JSON。改标注须两边一起更新。
