---
name: tool-gt-rectify
description: >-
  基于当前 GT 和某模型某版本的推理结果，把误检裁成正方形，分成真误检与假误检，再把假误检写成带 _m 的弱标签。
  Use when the user says 弱标签、假误检、真误检、矫正 gt，或「基于 xx 模型 xx 版本，做一下这个测试集场景的弱标签」。
---

# 🏷️ Tool-GtRectify（弱标签矫正）

  - **概述**: 用户说「我想基于 xx 模型 xx 版本，做一下这个测试集场景的弱标签」时触发。先做前期检查，再把当前误检裁出来人工分拣，最后只把假误检写进 GT。
  - **日期**: 2026-09-27

---

## 0 执行前检查

  未完成下面三项、用户未确认前，不推理、不裁图、不改 GT。

  1. xx 模型 xx 版本 是否存在，向用户确认路径
  2. 确认测试集路径，是否有 gt 的 jsons 文件
  3. 询问用户是否需要建 customer 票

  - **仓库根 `REPO`**：`skills/` 的上一级。
  - **工具**：`REPO/tools/1-DataEngine/0-Data-Organize/`。裁图、落盘、评测都走这里，不把脚本抄进 customer 票。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。本流程 `NEED_TORCH=no`，`PKGS=pyyaml opencv-python numpy`，venv slug=`organize`。推理若另开 YOLO 叶，再按那个叶装 torch。
  - **数据根**：测试集场景目录必须由用户给出，禁止猜测。
  - **不做**：不改强标签，不把真误检写进 GT，不在 `假误检` 已有图片时重刷 `真误检`。

---

## 1 向用户确认

  读一张 GT、一张预测（若已有），把类名对照写进确认单。预测类名和 GT 类名不一致时必须给出 alias，否则全部会被当成误检。

    ```markdown
    请确认后回复「按此开跑」：

    1. 模型权重：[绝对路径]（版本 [vX.Y.Z | 无]，文件存在 / 不存在）
    2. 测试集：[场景绝对路径]
    3. GT：[jsons 目录，N 个 json，示例类名]
    4. 预测：[已有 jsons-det-pre 目录 | 还没有，需要先推理]
    5. 类别对照：[已修复裂缝 → YiXiuFuLieFeng]
    6. 是否建 customer 票：[否（默认）| 是]
    ```

  第 6 项选「是」：Read `skills/agent-customer_task/SKILL.md` 建票。票里只写路径和本 Skill，不复制 `0-Data-Organize`。选「否」或未答：不建票，直接在场景目录落盘。

---

## 2 落盘

  相对测试集场景目录。有版本才加版本这一级；没有版本则 `repro/<模型名>/误检/`。模型目录名沿用该场景 `repro/` 里已有的名字。

    ```text
    repro/xxx模型/xx版本(如有)/误检/真误检（默认结果落盘）
    repro/xxx模型/xx版本(如有)/误检/假误检（人工挑选 _m 弱标签）
    ```

  其下再按 `cls-<预测类名>/` 放裁图，文件名 `{图名}_{序号}.jpg`。`误检/index.json` 记下每张图对应的预测框，挑选时不要改文件名，`cls-*` 目录一并移动。

  - **注意**：crop 策略遵循 2 倍然后以长边为边长，裁剪正方形。框画浅绿色。实现是 `util/square_crop.py`。

---

## 3 执行

  工作目录：`REPO/tools/1-DataEngine/0-Data-Organize`。解释器是 tool-build_env 的 `$PY`。判定与 `2-test_report-gt.py` 一致：IoU **大于** 0.30 算对上；先强标签再 `_m` 弱标签；对上任一都算正检；只有没对上的强标签算漏检，弱标签漏了不计。

### 3.1 导出真误检

  没有预测 json：停，确认权重、conf、device 后再推理。已有同版本预测：直接用，不重跑。

  预测对上强标签或已有弱标签的，不导出。其余全部进入 `真误检`。`假误检` 先空着。

    ```bash
    "$PY" util/gt_rectify.py dump \
      --gt-dir "<场景>/jsons-gt-xxx" \
      --pre-dir "<场景>/repro/<模型>/<版本>/jsons-det-pre-xxx" \
      --images "<场景>/images" \
      --out "<场景>/repro/<模型>/<版本>/误检" \
      --alias alias.yaml \
      --iou 0.30 --expand 2
    ```

  `alias.yaml` 只写类名对照，例如 `已修复裂缝: YiXiuFuLieFeng`。类名已经一致则省略 `--alias`。

### 3.2 人工挑选

  停。请用户把「模型检对了、不该算误检」的图从 `真误检` 移到 `假误检`。留在 `真误检` 的是真误检，不写 GT。用户明确说挑选完成之前，不执行写回。

### 3.3 写回弱标签

  人工挑选后，更新到 gt 中去。只追加矩形，标签为 `{对照后的类名}_m`，不删除、不改原强标签。先 dry-run，用户点头后再写。

    ```bash
    "$PY" util/gt_rectify.py apply --out "<场景>/repro/<模型>/<版本>/误检" --dry-run
    "$PY" util/gt_rectify.py apply --out "<场景>/repro/<模型>/<版本>/误检"
    ```

  - **注意**：假误检和旁边的强标签 IoU 不超过 0.30 时，写回后这条预测不再算误检，但那个没对上的强标签仍然算漏检。同一条缝只是框大小差很多时，要不要改强标签另问用户，本流程不自动改。

### 3.4 弱标签评测

    ```bash
    "$PY" util/weak_label_report.py --gt-dir "<场景>/jsons-gt-xxx" --pre-dir "<预测目录>" --alias alias.yaml --iou 0.30
    ```

  正检含对上弱标签的预测。漏检率的分母是强标签数量。
