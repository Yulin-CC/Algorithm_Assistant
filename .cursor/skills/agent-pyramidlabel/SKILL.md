---
name: agent-pyramidlabel
description: >-
  Pyramid iterative labeling: gold/ seed, toclean/ pool, stair sample, train,
  prelabel, human check. Use when the user says 金字塔, pyramid label, 迭代标注,
  or names a pyramidlabel customer ticket. Paths and classes live in require/.
---

# 🪜 Agent-PyramidLabel（台阶扩标）

  - **概述**: 用户说「金字塔 / 迭代标注 / pyramid label」时触发。先定位客户票 → Read `require/` → 确认台阶与审标模式 → 按轮选样、训练、预标、等人审。类名与路径只写在 require。
  - **日期**: 2026-10-19

---

## 0 执行前检查

  - **闸门**：`skills/standard-leaf_run/SKILL.md`。环境：`tool-build_env`（训练 `NEED_TORCH=yes`）。
  - **票**：`customer/*-pyramidlabel*/`。无票先走 `agent-customer_task` 建票，禁止在数据根裸跑。
  - **工单**：先 Read 该票 `require/require.md`。`project` / `data_root` / `work_root` 空 → 停，问用户并写回。
  - **台账**：该票 `todo.md`（⭐ 强制维护）。不要再写 `todo-<project>.md` 到数据集。
  - **训练**：仓库 `0-QuickStart/`。票内 `util/` 只做选样/预标胶水，禁止复制叶引擎。
  - **整理**：LabelMe↔YOLO / split 走 `tools/1-DataEngine/0-Data-Organize`。
  - **不做**：不猜路径；不覆盖 `gold/`；不把 `toclean` 脏标当金标；未确认不开 round；人审未完成不训下一轮。

  目录约定（相对 `data_root`，子目录名以 require 为准）：

  | 路径 | 含义 |
  | --- | --- |
  | `gold/` | 种子金标 + 各轮人审 \(C_k\) |
  | `toclean/` | 待标池 \(U\)，只读图源 |
  | `pre/round-k/` | 本轮预标缓存 |
  | `pseudo/` | 仅 **keep 模式** 使用 |

  `work_root`：`datasets/<project>/round-k/`（软链集）、`runs/`。

---

## 1 进度台账（todo.md）

  - **路径**：票根 `todo.md`。对话与文件冲突时以 **台账 + 磁盘** 为准。

  **(1)** 开跑 / 续跑前先 Read；禁止无故重做 `done`。
  **(2)** 每完成一个可恢复节点立即更新 `phase` / `current` / `next` / Rounds 表。
  **(3)** 用户说「继续 / check 进度」：读台账 → 摘要 → 执行 `next`。
  **(4)** 文件不存在：按模板新建后再开跑。

  `phase`：`confirm` | `sample` | `train` | `prelabel` | `wait_review` | `ingest` | `done`。

    ```markdown
    # Pyramid TODO

    - **updated**: YYYY-MM-DD HH:MM
    - **ticket**: customer/<kind>-<yymmdd>-pyramidlabel-<slug>
    - **phase**: confirm
    - **current**: …
    - **next**: …
    - **blocked**: 无

    ## Meta
    - data_root / work_root / backend / classes: （见 require）
    - review_mode: all | keep
    - N / n0 / U: …

    ## Checklist
    - [ ] §2 确认 require（路径、类、台阶、审标模式）
    - [ ] 统计 n0 / U（toclean 未搬完只记预估）
    - [ ] 各轮 round
    - [ ] 交付摘要

    ## Rounds
    | k | |S| | L | C | keep | U_left | status | note |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | 1 |  |  |  |  |  | pending | |

    ## Notes
    - …
    ```

---

## 2 确认工单

  把 require 列给用户：`project`、`backend`、`data_root`、`work_root`、`classes`、台阶 `schedule_pct`、审标模式。未确认不得开 round。

  审标模式（读 require，不要猜）：

  | 模式 | 判定 | 人审 | 自动入库 |
  | --- | --- | --- | --- |
  | **all** | `human_review_all: true` 或 `check_frac=1` 且 `pass2_enabled: false` | \(S_k\) 全部进 check | 无；审过才进 `gold/` |
  | **keep** | 默认 | 约 `check_frac` 进 check | pass2 过 `conf_pass2` 进 `pseudo/` |

  - **all**：`conf_pass1` 只作推理下限，不筛给人看的框。不强制双库盖满 \(N\)。
  - **keep**：\(\lvert\mathrm{gold}\cup\mathrm{pseudo}\rvert=N\)，同 stem 不得两边都有。末轮残留可空框进 `pseudo/`。
  - **注意**：`check_enabled: false` 须用户原话。toclean 未搬完只记预估 \(N_U\)，不按半成品开全量台阶。

---

## 3 一轮怎么跑

  \(L\) = gold stems；\(U\) = toclean 未审；\(S_k\) = 本轮抽样；\(C_k\) = 人审通过。

  **all**：选样 → 训主模型 → 预标 \(S_k\) → **停等人审** → \(C_k\) 入 gold → 更新 \(L,U\)。

  **keep**：选样 → 训主模型 → pass1 → check（停等人）→ \(C_k\) 入 gold → 训校验模型 → pass2 keep 入 pseudo → 更新 \(L,U\)。

  **(1)** 统计 \(n_0,U\) 写入 todo。`seed.txt` 记初始 gold stems。
  **(2)** `util/pyramid_build_round.py` → `work_root/datasets/<project>/round-k/`（只软链大图）。
  **(3)** 训练：\(k=1\) 用 `seed_weights`；\(k\ge2\) 热启上轮。入口 `bash 0-QuickStart/0-train.sh`，yaml 见 require `data_yaml`。
  **(4)** `util/pyramid_prelabel.py`。all 模式 `--check-ratio 1`；keep 模式用 `check_frac` / `conf_pass1`。
  **(5)** 人审后拷 \(C_k\) 进 `gold/`（图 + json）。已在 gold 的 stem 不得进 pseudo。
  **(6)** 本节完成后：更新 Rounds 行、`phase`、`next`。`wait_review` 时停，下一轮从台账续。

---

## 4 工具索引

  - 胶水根：该票 `util/`（没有则从 `customer/image-260811-pyramidlabel/util/` 对照，不要拷 DetSeg 叶）。

  | 分类 | 路径 | 用途 |
  | --- | --- | --- |
  | 工单 | 票 `require/require.md` | 项目 / 路径 / 类 / 台阶 / 模式 |
  | 选样 | 票 `util/pyramid_build_round.py` | \(U\) → round-k 软链集 |
  | 预标 | 票 `util/pyramid_prelabel.py` | 权重 + \(S_k\) → txt / check json |
  | json | 票 `util/pyramid_txt2json.py` | YOLO txt → LabelMe json |
  | 训练 | `0-QuickStart/0-train.sh` | gold → 本轮权重 |
  | 整理 | `tools/1-DataEngine/0-Data-Organize/util/` | json↔txt / split |
  | 台账 | 票 `todo.md` | 断点续跑；强制读写 |

  - **注意**：训练 / 预标用 `$PY`（见 `tool-build_env`），不得用系统 Python 硬跑。

---

## 5 交付

  摘要各轮 \(|S_k|\) / \(C_k\) / keep（若有）/ 权重 / `pre/`。默认不合并正式 `labels/`（用户点名才做）。keep 模式再对账双库无交叉。
