---
name: smart-image
description: >-
  Image understanding and false-positive checks on existing boxes or masks,
  plus a short analysis of those verdicts. Use when agent-smart-image
  dispatched this package. describe.py writes a short visible-content
  description. label_grade.py scores boxes and polygon masks as
  fit/adjust/wrong. overlay.py only draws. label_miss.py reports miss
  points and writes 640 crops. opt_fill.py asks for a mask or a box
  first, then locates with GroundingPI or SAM3 and can refine with
  Triton SAM. opt_adjust.py uses an adjust-grade box center as that
  point and runs the same chain. Change detection passes --masks, confirms
  the locate prompt first, then uses a Qwen point plus Triton SAM.
  analysis.py
  groups false positives, loose regions, and any miss file already written.
  It does not rewrite the original LabelMe.
disable-model-invocation: true
---

# 图像理解（`0-General/0-SmartImage`）

  - **概述**: Qwen 图像理解叶。单图走描述、逐框定档和结果分析。漏检定位与补标裁窗已分开。定档 adjust 的框中心走同一条补标链。数据集根下有对齐的 `A/`、`B/` 时，变化检测仍把两期左右拼在一起。不改原标注。
  - **日期**: 2026-11-11

---

## 0 执行前检查

  - **触发**：识图、描述图像、图像理解、误检过滤、叠图质检、漏检、补标、标签调整；由 `agent-smart-image` 指定本叶。
  - **本包根目录 `PKG_ROOT`**：`.skill/` 的上一级。
  - **数据**：单张绝对路径，或数据集目录（`images/` 或根下直接放图）。禁止猜测。
  - **落盘**（数据集，相对 `data_root`）：`model/` 是发给模型的图；`vis/` 是给人看的整图和表；`result/` 是 json。理解图像写 `draft/describe/result/jsons/{stem}.json`，两期拼图另存 `draft/describe/model/{stem}.jpg`。预标过滤写 `draft/overlay/`。`wrong` 和 `adjust` 的裁图另抄到 `draft/to_check/<类别>/wrong` 与 `adjust`。变化检测 `--masks` 另抄 `fit`。结果分析：变化检测不写 `draft/`，写 `repro/<版本>/analysis/`；目标框写 `draft/analysis/`。都不写正式 `labels/`，不改已有 LabelMe。旧路径 `draft/descriptions/` 仅作续跑读取。
  - **服务**：vLLM `server/config/vllm_server.json`。联通检查由 **总调度** 先做（`--skip-sam`）。本叶不再探测、**不下任何权重**。
  - **共享客户端**：`REPO/server/util/`（`vllm_client.py` / `common.py`）。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。本叶：`NEED_TORCH=no`，venv slug=`describe-qwen`，`PKGS=tqdm`（叠图质检另加 `opencv-python numpy`）。Windows 控制台 `PYTHONUTF8=1`。用户指定 conda `yulin` 时用该解释器，不另建 venv。
  - **不做**：不分类、不出框、不分割、不写 `labels/`、不下载 Qwen 权重。不改写 `jsons-det-pre*` 或任何已有 LabelMe。调整只写 `draft/adjust/`。不执行 `uv cache clean`。不写 `agent-auto_demo`。不把 DetSeg 的 `--gate` 当本叶入口。

---

### 0.1 环境初始化（未通过不得跑）

  按 `skills/tool-build_env/SKILL.md`：uv 建 `$DescVenv`（**不装 torch**），再：

    ```bash
    uv pip install --python "$PY" tqdm
    ```

  验收：`"$PY" -c "import tqdm; print('ok')"`。失败 → 停。命令都用 `$PY`。交付后或失败退出前只删 `$DescVenv`。

---

## 1 向用户确认（未确认不得开跑）

    ```markdown
    请确认后回复「按此开跑」：

    1. 图像：[单张绝对路径 | 数据集目录]
    2. 规模：[先 --limit 1 | 直接全量]（仅数据集）
    3. 续跑：[不 --force（默认） | --force]
    4. workers：[4]
    ```

  路径未给 → 只问第 1 项。单张图不写台账。

---

## 2 执行

  工作目录：`PKG_ROOT`。解释器 = `$PY`。

  **(1)** 单张：

    ```bash
    "$PY" util/describe.py --image "<path.jpg>"
    "$PY" util/describe.py --image "<a.jpg>" --image "<b.jpg>" --prompt "……"
    ```

  Python：`from describe import describe_file, describe_files`（工作目录 `PKG_ROOT/util`，或把该目录加入 `sys.path`）。

  **(2)** 数据集：先 `--limit 1` 给人看形态，点头后再全量。

    ```bash
    "$PY" util/describe.py --dataset "<data_root>" --workers 4 --timeout 600
    ```

  失败占位（`source=failed`）续跑不要加 `--force`。空 `--base_url` / `--model` 读 `vllm_server.json` 的 default。可用 `--prompt` 覆盖默认中文提示词。数据集根下有 `A/` 和 `B/` 时自动左前右后拼接，不再走单图。

  **(3)** 叠图质检（已有框/掩膜，不改写标注）：

    ```bash
    "$PY" util/label_grade.py --dataset "<data_root>" --jsons jsons-det-pre-car --mode instance --workers 2
    "$PY" util/label_grade.py --dataset "<data_root>" --jsons jsons-seg-pre --mode instance --workers 2
    "$PY" util/label_grade.py --dataset "<cd_root>" --masks label --workers 2
    ```

  变化检测的漏检和差检不走 GroundingPI。开跑前把数据集、要定位的变化、提示词正文贴给用户，回复「按此开跑」才执行。`--prompt` 为空则退出。

    ```bash
    "$PY" util/label_miss.py --dataset "<cd_root>" --masks label --prompt "<确认过的句子>" --workers 2
    "$PY" util/opt_fill.py --dataset "<cd_root>" --shape mask --locate off --refine sam
    "$PY" util/opt_adjust.py --dataset "<cd_root>" --masks label --prompt "<确认过的句子>"
    ```

  变化检测要求 `<cd_root>/A` 与 `B` 同名且已对齐。`--masks` 是 png 变化图，每个连通域裁同一窗口，左右都叠上掩膜。`grade=wrong` 是假变化。

  发给模型的矩形内部铺淡色，给人看的仍是亮框。类别名里带颜色时，发给模型的框和掩膜只描边，内部不铺色。多边形画半透明掩膜。两者都记 `grade`：`fit` 贴合，`adjust` 目标在但区域过大、不完整或错位（`issue=oversize|incomplete|shifted`），`wrong` 误检。同一次回复先判断类别是否存在，再判断区域质量。`present=true` 却给 `wrong` 时改成 `adjust`。`adjust` 不算误检。预标过滤：`draft/overlay/model/`（裁图；变化检测连通域裁窗 4.5 倍）、`vis/`（整图，绿贴合、橙要改、红误检）、`vis/summary.md`（逐条表格：档位、理由、裁图、整图）、`result/jsons/`、`result/summary.json`、`progress.json`。`wrong` 与 `adjust` 抄到 `draft/to_check/<类别>/`。检测分割抄裁图，`fit` 不抄。变化检测 `to_check` 是全景整图、只画当前这一块连通域（一块一张，文件名带序号），并另抄 `fit`。叠图和发给 Qwen 的裁图都不写字（无编号、无 T1/T2），只留彩色轮廓；小于 32 像素的碎斑不送模型，也不决定这张图进负样本还是正样本。不小于 32 像素的才按地物判断。跑完把 `summary.md` 的表格贴回给用户，并给出该文件路径和 `draft/to_check/`。

  **(4)** 掩膜结果分析（在定档上汇总，不改写标注。有漏检结果就计入，没有就写未做）：

    ```bash
    "$PY" util/analysis.py --dataset "<data_root>" --pred jsons-seg-pre --gt jsons --workers 2
    "$PY" util/analysis.py --dataset "<cd_root>" --pred "<bcd_map>" --gt label --workers 2
    ```

  `--gt` 可省略。**变化检测** `--pred` 指向 `repro/<版本>/bcd_map` 时，Qwen 用同级 `crop/analysis_crop/`（不另写 `model/`），判定写 `repro/<版本>/analysis/jsons/` 与 `analysis.json`（计数融进该文件，不再写 `summary.json`）。已有 json 且不加 `--force` 时不重问。

    ```text
    repro/<版本>/bcd_map/               二值预测
    repro/<版本>/crop/analysis_crop/    Qwen 识图（无 GT）；窗名单以同级 vismask_crop 为准，同名取图，缺图不补写
    repro/<版本>/crop/vismask_crop/     GT 分色裁窗；定档按这里的窗枚举
    repro/<版本>/crop/vismask_crop/     同一窗口裁全图 GT 分色叠图
    repro/<版本>/vismask/               全图：有 GT 时绿交叠 / 红仅预测 / 蓝仅 GT；无 GT 只叠红预测
    repro/<版本>/analysis/jsons/        每张图判定
    repro/<版本>/analysis/analysis.json 汇总（含原 summary 计数）
    ```

  目标框定档仍写 `draft/analysis/`（`model/` / `vis/` / `result/`）。`grade=wrong` 算误检；`grade=adjust` 单列；GT 上的 `wrong` / `adjust` 算标签问题。旧结果里的 `fit=miss` 按 `wrong` 读。

---

## 3 工具索引

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 1 理解图像 | `util/describe.py` | `--image` / `--dataset` → `{"description":"..."}` |
  | 2 误检定档 | `util/label_grade.py` | 框和掩膜 → `grade=fit|adjust|wrong`；叠图在 `util/overlay.py`；不改写标注 |
  | 2b 过滤误检 | `util/label_filter.py` | 读定档结果，去掉 `grade=wrong` 写进新目录（默认 `<原目录>-drop`）。源标注不动。`--dry-run` 只统计 |
  | 漏检定位 | `util/label_miss.py` | 整图把已有目标盖成灰色掩膜后再报点，并裁 640 到 `draft/miss/crop/`。只用 Qwen。变化检测 `--masks`，提示词先向用户确认 |
  | 补标 | `util/opt_fill.py` | 先问落掩膜还是落框。`--shape mask` 是 Triton SAM 多边形。`--shape box` 再取掩膜的水平最小外接矩形。直出框才 `--refine off`。变化检测 pair 记录只允许 `--locate off --refine sam` |
  | 调整 | `util/opt_adjust.py` | 定档 `adjust` 的框中心当报点，其余目标涂灰后裁图，再走补标。变化检测 `--masks` 由 Qwen 重新报点再交 Triton SAM，不走 GroundingPI |
  | 4 结果分析 | `util/analysis.py` | 误检、不贴合、已有漏检；不再问模型 |
  | 变化检测 | `util/label_grade.py --masks` | 两期 png 掩膜定档。整图绘制在 `util/overlay.py` |
  | 共享 | `REPO/server/util/` | vLLM / 扫图 |
  | 服务 | `REPO/server/config/vllm_server.json` | default vLLM |

---

## 4 交付

  摘要：路径、服务、图像数、`draft/describe/result/jsons/`（若有）。叠图质检必须把 `draft/overlay/vis/summary.md` 的逐条表格贴回，并写出该文件路径和 `draft/to_check/`。声明未做分类/检测/写 labels。台账 `phase=deliver`。

---

## 5 能力边界

  - **1 理解图像**：`util/describe.py`，已实现。
  - **2 误检过滤**：`util/label_grade.py`，已实现。叠图在 `util/overlay.py`。矩形画细框，多边形画半透明掩膜。两者都记 `grade=fit|adjust|wrong`。不删、不改原标注。`adjust` 交给 `opt_adjust.py`。变化检测是 `util/label_grade.py --masks`。
  - **2b 过滤落盘**：`util/label_filter.py`。读 `draft/<slug>/result/jsons/` 的定档结果，按 `index` 对回源标注的 `shapes`，去掉 `grade=wrong`（旧结果里 `fit=miss` / `verdict=wrong` 也算），写进新目录。源目录不动，也不写正式 `jsons/`。没定档的条目原样保留，不擅自删。`--dry-run` 只统计。
  - **漏检**：`util/label_miss.py` 先把已有目标盖成实心灰色。多边形直接涂，矩形默认用 Triton SAM 收成掩膜再涂，不把整框涂灰。`--sam off` 时矩形直接涂整框，不调 Triton SAM。再在整图上报点。挨在一起的点并成一张裁图。不在图像边上时，裁图放大到车身不被切断，最大 1280；放不下就拆成多张。贴着图像边缘才保持切到边上。写 `draft/miss/crop/`。灰色区域不落点。报点用 Qwen，收掩膜用已有的 Triton SAM。变化检测加 `--masks`：两期已有变化涂灰后拼接，按 `--prompt` 报点，裁选中时相的原图。提示词先向用户确认，空则退出。不走 GroundingPI。
  - **补标**：`util/opt_fill.py` 读这些裁图。跑之前先问用户落掩膜还是落框，`--shape` 必填。掩膜是 `--shape mask`，Triton SAM 多边形就是结果。框是 `--shape box`，默认 GroundingPI 定位再 Triton SAM，然后取掩膜的水平最小外接矩形。用户明确说定位模型直出框时才 `--refine off`。SAM3 是定位的另一选择。两段可以单独关，不能同时关，掩膜不能关修边。GroundingPI、SAM3、Triton SAM 调数据引擎或已有客户端，脚本不切服务。组长在 `label_miss` 之后、`opt_fill` 之前切。不改原标注。变化检测的 `pair: true` 记录只允许 `--shape mask --locate off --refine sam`。新掩膜与原变化图大面积重叠的丢掉，png 写到 `draft/fill/masks/`，不覆盖原掩膜。
  - **4 结果分析**：`util/analysis.py`，已实现，归测试工程师，由组长派 `test-engineer`。汇总误检、不贴合和已有漏检。不改标注，不再问模型。识图、定档和补标归数据工程师，由组长派 `data-engineer`。
  - **调整**：`util/opt_adjust.py` 读 `draft/overlay/` 里 `grade=adjust` 的框。框中心就是报点，不再问 Qwen。要改的目标不涂灰，其余目标按漏检那样涂灰，然后裁图。后面的定位、修边、落掩膜或落框与 `opt_fill.py` 相同。新形状必须罩住原来的中心，才替换这一条。结果在 `draft/adjust/`。不改原标注。变化检测加 `--masks` 和 `--prompt`：Qwen 在当前这块上重新报点，Triton SAM 出掩膜，新掩膜必须罩住这个新点。不走 GroundingPI，不要求罩住旧掩膜中心。png 写到 `draft/adjust/masks/`。
