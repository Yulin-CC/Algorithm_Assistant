---
name: agent-customer-task
description: >-
  Scaffolds a customer ticket under customer/<kind>-<yymmdd>-<slug>/ with
  .skill, require, util, and todo.md. Use when adding a customer job, 客户任务,
  or asking how customer folders should look. Does not copy DataEngine engines.
---

# 📦 Agent-CustomerTask（客户任务包）

  - **概述**: 在 `customer/` 新建客户票。**.skill** 写通用流程并 **路由到 require**；具体类名/路径/点写在 **require**。干活走 `tools/` 叶，不要复制引擎。
  - **日期**: 2026-09-11

---

## 0 执行前检查

  - **触发**：新建客户任务、对齐 `customer/` 目录。
  - **根目录 `CUST_ROOT`**：`REPO/customer/`。
  - **参照**：`image-260911-classify-field/`（分类）；`image-260827-class-complement/`（互补）；`image-261020-smartcity-complement/`（互补实单）；`image-260811-pyramidlabel/`（金字塔）。
  - **互补票**：建包后第一句提醒用户粘贴互补矩阵，位置是该票 `require/require.md` 的「## 互补矩阵」。不要用金标共现代填。
  - **不做**：不落地 `0-Qwen/`、`4-Agent-label/`；不把叶脚本拷进 customer。

---

## 1 目录约定

    ```text
    customer/
    ├── .skill/SKILL.md
    └── <kind>-<yymmdd>-<ascii-slug>/
        ├── .skill/SKILL.md          # 通用：走哪片叶、闸门、确认、交付
        ├── require/require.md       # 本单工单：类 / 路径 / GoldSet / 点
        ├── todo.md                  # 进度；不抄 require 里的类表
        └── util/                    # 可选；本单胶水，禁止复制叶引擎
    ```

  | 字段 | 规则 |
  | --- | --- |
  | `kind` | `image` / `cd` / `gd` |
  | `yymmdd` | 开单日期 |
  | `slug` | 能力 + 场景，如 `classify-field` |

  必有：`.skill/SKILL.md`、`require/require.md`、`todo.md`。

  **分流**：换类别、换点、换数据根 → **只改 require**。叶流程变了才改 `.skill`。

---

## 2 通用规定

  **(1)** `data_root` 写在 require，禁止猜测。
  **(2)** 能力叶：分类 → `1-Image-Classify/qwen`；检测分割 → `2-Image-DetSeg/<backend>`；图像理解 / 误检过滤 → `0-General/0-SmartImage`（调度 `agent-smart-image`）；整理 → `0-Data-Organize`。定档 adjust 的改形也走该叶，不改原标注。
  **(3)** 落盘跟叶 Skill。customer 不另起产物目录。
  **(4)** 台账：本票 `todo.md`。数据集 `draft/` 只放产物。
  **(5)** 环境：`tool-build_env`；Qwen 叶先 `probe.py`。
  **(6)** 先小后全。覆盖须 `--force`。失败占位不加 `--force`。
  **(7)** 分类知识只留 `knowledge.json`。

---

## 3 require 头（YAML）

  `require/require.md` 以 `---` 头供脚本读，正文给人看。

    ```yaml
    ---
    leaf: tools/1-DataEngine/1-Image-Classify/qwen
    data_root: /path/to/...
    images: images
    classes:
      - 类A
      - 类B
    sites:            # 可省略：省略则 data_root 本身当一个数据集
      - subset-1
    guide: 一句口径
    ---
    ```

---

## 4 包内 Skill（通用，不要写死类名）

  开跑第一步：**Read `require/require.md`**。确认清单用 require 字段填空。执行抄对应叶；有 `sites` 再用本包 `util/`。

---

## 5 新建清单

  - [ ] 目录 `kind-yymmdd-slug`
  - [ ] `.skill/SKILL.md` 只写叶 + 闸门
  - [ ] `require/require.md` 写本单口径
  - [ ] `todo.md` 阶段字段，细节指向 require
  - [ ] 需要才加 `util/`
  - [ ] 不改其它票、不改叶默认行为

---

## 6 工具索引

  | 分类 | 路径 | 用途 |
  | --- | --- | --- |
  | 本规范 | `skills/agent-customer_task/SKILL.md` | 建包 |
  | 调度 | `skills/agent-data_engine/SKILL.md` | 叶 |
  | 参照 | `customer/image-260911-classify-field/` | 分类票 |
  | 参照 | `customer/image-260827-class-complement/` | 互补票 |
  | 参照 | `customer/image-260811-pyramidlabel/` | 金字塔票 |
