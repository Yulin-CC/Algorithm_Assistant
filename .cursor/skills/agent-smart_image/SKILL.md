---
name: agent-smart-image
description: >-
  Dispatches image understanding, box/mask checks, and result analysis
  to tools/0-General/0-SmartImage. Boxes and polygon masks are scored
  fit/adjust/wrong by label_grade.py. label_miss.py reports points and
  crops.   opt_fill.py locates with GroundingPI or SAM3, then Triton SAM
  can refine the edge. Before fill or adjust, ask whether to write a
  mask or a box. opt_adjust.py treats an adjust-grade shape as that
  point, then uses the same crop and fill chain. Change detection passes
  --masks, confirms the locate prompt first, then uses a Qwen point plus
  Triton SAM and does not call GroundingPI. Use when the user says
  识图, 描述图像, 图像理解, 误检过滤, 叠图质检, 掩膜分析, 漏检, 标签调整,
  or names agent-smart_image. Does not rewrite the original LabelMe.
---

# 图像理解

  - **概述**: 调度到叶子 `tools/0-General/0-SmartImage`。理解图像，逐框定档。漏检和 adjust 都先落到一个点再裁图，然后由 GroundingPI 或 SAM3 定位，Triton SAM 修边。切服务在这两步之间，由组长做。不改原标注。
  - **日期**: 2026-11-11

## 1 能力

  | # | 能力 | 落点 | 状态 |
  | --- | --- | --- | --- |
  | 1 | 理解图像 | `util/describe.py` | 已实现，归数据工程师，由组长派 `data-engineer`。单图写可见内容。有 `A/` 与 `B/` 时左前右后拼在一起，描述两期变化 |
  | 2 | 搭配掩膜/框做误检过滤 | `util/label_grade.py` | 已实现，归数据工程师，由组长派 `data-engineer`。框和掩膜同一套 `grade`：`fit` 贴合，`adjust` 目标在但区域过大、不完整或错位，`wrong` 是误检。叠图在 `util/overlay.py`。产物 `draft/overlay/`，`wrong` 和 `adjust` 的裁图抄到 `draft/to_check/<类别>/`。变化检测 `--masks` 另抄 `fit`。**不改写**原标注 |
  | 4 | 掩膜/框结果分析 | `util/analysis.py` | 已实现，归测试工程师，由组长派 `test-engineer`。测试可视化：`--pred`、**省略 `--gt`**。变化检测写 `repro/<版本>/analysis/`（jsons + analysis.json），裁图用 `crop/analysis_crop/`。缺结果时问 Qwen；已有 json 且不 `--force` 则不重问。`wrong` 是误检，`adjust` 单列。变化检测有 `repro/<版本>/draft/miss/` 时计入漏检，没有就写未做 |
  | 3 | 按理解调整掩膜和框 | `util/opt_adjust.py` | 已实现，归数据工程师，由组长派 `data-engineer`。检测分割：定档 `adjust` 的框中心当作报点，再走补标链。变化检测 `--masks` 由 Qwen 按确认过的提示词重新报点，再交 Triton SAM，不走 GroundingPI。跑前先确认定位什么。不改原标注 |

  分类、出框、分割预标不走这里（数据引擎）。GroundingPI 检测或检测+Triton SAM 分割后的默认校验由 `agent-data_engine` §2.2 链式调度到本叶（中途不另问切服务）。框和掩膜都记 `grade=fit|adjust|wrong`。模型先答 `present`：目标在却给 `wrong` 时改成 `adjust`。`wrong` 是误检；`adjust` 是目标在但区域要改，交给 `opt_adjust.py`。定档这一步不改形状。`verdict=ok` 覆盖 `fit` 和 `adjust`。本叶不改原标注。DetSeg 的 `--gate` 不是本技能入口。

## 2 执行

  对上后 Read `REPO/tools/0-General/0-SmartImage/.skill/SKILL.md`，闸门 `skills/standard-leaf_run`。理解图像、定档和漏检定位都先 `probe.py --skip-sam`。结果分析复用已有结果，不另开模型。变化检测测试分析写 `repro/<版本>/analysis/`，Qwen 用 `crop/analysis_crop/`；漏检/补标/调整拢在 `repro/<版本>/draft/`（`miss/`、`fill/`、`adjust/`）。目标框仍写数据集根 `draft/analysis/`。预标过滤写 `draft/overlay/`：`model/` 发给模型的裁图（变化检测连通域裁窗 4.5 倍），`vis/` 给人看的整图和 `summary.md`，`result/` 是判定 json。`wrong` 和 `adjust` 抄到 `draft/to_check/<类别>/`。检测分割抄裁图，`fit` 不抄。变化检测 `to_check` 全景只画当前连通域，一块一张，并另抄 `fit`。叠图不写编号也不写 T1/T2，小于 32 像素的碎斑不送模型，也不决定这张图进负样本还是正样本。不小于 32 像素的才问模型。漏检整图在 `draft/miss/`，已有目标盖成灰色掩膜后再报点。矩形默认经 Triton SAM 收成掩膜，`--sam off` 时直接涂整框。挨在一起的点并成一张裁图，不在图像边上就放大到车身完整，放不下再拆开。裁图在 `draft/miss/crop/`。灰色区域不落点。补标结果在 `draft/fill/`。`label_miss` 只用 Qwen。跑完后由组长切到定位服务。跑 `opt_fill` 前先问用户要补标框还是掩膜。掩膜传 `--shape mask`，结果是 Triton SAM 多边形。框传 `--shape box`，默认仍是 GroundingPI 加 Triton SAM，再取掩膜的水平最小外接矩形。只有用户明确说定位模型直出框时才加 `--refine off`。`grade=adjust` 不另问 Qwen：框中心就是报点，写 `draft/adjust/`，命令是 `opt_adjust.py`，形状确认和补标相同。脚本自己不切服务，也不启动 vLLM / SAM。跑完定档后，把 `draft/overlay/vis/summary.md` 的逐条表格贴回给用户，并给出该文件路径和 `draft/to_check/`。

  变化检测的漏检和差检不走 GroundingPI。开跑前先贴确认单，用户回复「按此开跑」才执行。`--prompt` 与 `--prompt-file` 都空则脚本退出。

  ```markdown
  请确认后回复「按此开跑」：

  1. 数据集目录：
  2. 本单要定位的变化：（用户原话，例如新建或拆除的建筑、耕地占用）
  3. 提示词正文：
  4. 链路：Qwen 报点，Triton SAM 出掩膜，不走 GroundingPI
  5. 不覆盖原来的 png。漏检在 `draft/miss/` 与 `draft/fill/`，差检在 `draft/adjust/`
  ```

  漏检：`label_miss.py --dataset <cd_root> --masks label --prompt "<确认过的句子>"`。补标：`opt_fill.py --dataset <cd_root> --shape mask --locate off --refine sam`。差检：`opt_adjust.py --dataset <cd_root> --masks label --prompt "<确认过的句子>"`。
