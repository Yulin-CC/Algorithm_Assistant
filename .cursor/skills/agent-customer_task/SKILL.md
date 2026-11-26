---
name: agent-customer-task
description: >-
  Scaffolds a customer ticket under customer/<kind>-<yymmdd>-<slug>/ with
  .skill, require, util, and todo.md. Use when adding a customer job, 客户任务,
  or asking how customer folders should look. Does not copy DataEngine engines.
---

# 📦 Agent-CustomerTask（客户任务包）

  - **概述**: 在 `customer/` 新建客户票。**.skill** 写通用流程并 **路由到 require**；具体类名/路径/点写在 **require**。干活走 `tools/` 叶，不要复制引擎。`proj` 票是项目工单，不绑叶子。
  - **日期**: 2026-11-18

---

## 0 执行前检查

  - **触发**：新建客户任务、对齐 `customer/` 目录、项目工程师开 `proj` 票。
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
        ├── .skill/SKILL.md          # 通用：走哪片叶、闸门、确认、交付；proj 票不写叶路径
        ├── require/require.md       # 本单工单：类 / 路径 / GoldSet / 点；proj 写步骤口径
        ├── todo.md                  # 进度；不抄 require 里的类表
        └── util/                    # 可选；本单胶水，禁止复制叶引擎
    ```

  | 字段 | 规则 |
  | --- | --- |
  | `kind` | `image` / `cd` / `gd` / `proj` |
  | `yymmdd` | 开单日期 |
  | `slug` | 能力 + 场景，如 `classify-field`；项目票写项目名 |

  **项目票**：默认一项目一票 `proj-<yymmdd>-<slug>/`。`todo.md` 是全部步骤。只有步骤跨不同 `data_root`、或完全不同 `kind`（如纯分类 vs 开集）时才拆多票。现有 `image` / `cd` / `gd` 票不动。

  必有：`.skill/SKILL.md`、`require/require.md`、`todo.md`。

  **分流**：换类别、换点、换数据根 → **只改 require**。叶流程变了才改 `.skill`。

---

## 2 通用规定

  **(1)** `data_root` 写在 require，禁止猜测。
  **(2)** 能力叶：分类 → `1-Image-Classify/qwen`；检测分割 → `2-Image-DetSeg/<backend>`（只有 `groundingpi`、`yolo26`、`sam3`，旧的 qwen 叶已删）；图像理解 / 定档 / 误检过滤 / 补标 → `0-General/0-SmartImage`（调度 `agent-smart_image`）；整理 → `0-Data-Organize`。定档 adjust 的改形也走该叶，不改原标注。
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
    data_root: D:\path\to\data
    images: images
    classes:
      - 类A
      - 类B
    sites:            # 可省略：省略则 data_root 本身当一个数据集
      - subset-1
    guide: 一句口径
    ---
    ```

  项目票头：

    ```yaml
    ---
    kind: proj
    goal_file: D:\path\to\goals.md
    success: 一句总成功标准
    ---
    ```

  `goal_file` 必须是用户给的绝对路径。正文版式见 **§7**。缺的路径标「待确认」，禁止猜盘。

---

## 4 包内 Skill（通用，不要写死类名）

  开跑第一步：**Read `require/require.md`**。确认清单用 require 字段填空。执行抄对应叶；有 `sites` 再用本包 `util/`。

  **项目票**：`.skill/SKILL.md` 只写下面三句，不写叶路径。执行看 `require/require.md`。

    ```markdown
    # 项目工单

    步骤、路径、技能以 `require/require.md` 为准。组长按 S1、S2… 点名工程师。本文件不绑叶子。
    ```

---

## 5 新建清单

  - [ ] 目录 `kind-yymmdd-slug`
  - [ ] `.skill/SKILL.md` 只写叶 + 闸门；**项目票不写叶路径**
  - [ ] `require/require.md` 写本单口径；**项目票按 §7**
  - [ ] `todo.md` 阶段字段，细节指向 require；**项目票 Checklist 只写 S1、S2**
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
  | 项目票 | `customer/proj-<yymmdd>-<slug>/` | 项目工程师工单，不绑叶子。正文见 §7 |

---

## 7 项目工单（proj）

  给组长看的执行说明写在 `require/require.md`。`todo.md` 只记勾选。拆单先读 `workarea/habits.md`，只用状态为已确认的条。地图不清就停在 §0，不把「待确认」写进步骤当已定。已确认习惯对得上的，请组长定里写进建议和依据。不改 `habits.md`。

### 7.1 章节（固定顺序）

  | 节 | 写什么 |
  | --- | --- |
  | 标题 | `# 工单 · <一句话目标>` |
  | 0 核对 | **产物对照**（工单要的 ↔ 盘上已有）；**现在拍板**（用户层，人话，最多 2 条，盘上已齐的不准出现）；**请组长定**（执行空格，每条建议 + 依据） |
  | 1 范围 | 本机待处理目录名单、张数、不挖哪些。数字来自地图或对已确认根的一层清点 |
  | 2 步骤 | `### S1 …` `### S2 …` 每步一张字段表，字段不得增删 |
  | 3 顺序 | 一行：S1 → S2 → … 和点名的工种 |

  主节之间用 `---`。

### 7.2 每步字段（不得增删、不得换序）

  | 字段 | 写什么 |
  | --- | --- |
  | 工种 | `ops-engineer` / `data-engineer` / `train-engineer` / `test-engineer` |
  | 依赖 | `S1` 或 `—` |
  | 本机 | 绝对路径。没有本机动作写 `—` |
  | 远端 | 绝对路径。没有远端动作写 `—`。未确认写 `待确认`，不要填别的机器上的旧路径 |
  | 技能 | `skills/` 下的名字，或叶路径。没有命令也要写技能 |
  | 做法 | 一两句。路径加引号。不写散文 |
  | 交付 | 落盘目录或要核对的张数 |
  | 成功 | 组长能用来判断这一步做完的那一条 |

  模型、权重、规则名：只抄地图或用户原话。地图没有「当前最新」，进 **请组长定**（建议上一张同类票或交接路径），步骤里可暂写 `待确认`，不要写 `latest`，不要问用户。

  房间里已有人在做同一段（`working` / `waiting` 接着做 / `stale` 且无 `done`）：本单不新开该步。§0 写清承接谁；第一步写成等对方 `done`，或运维盯进程。`stale` 不是挖完，也不是可以重开。

  **现在拍板**只写用户层、用人能听懂的话：新数据根从没给过、会新增类别或改这轮要训哪些类、要停别人正在用的卡/进程、工单列表看不懂、从没做过的新类型任务。后步一定要人拍板的，拆单时一次写在这里。不要把房间项目名、内部目录名、张数加总一次丢出去。

  **请组长定**：主机确认列空着但 Data/Project 已确认、vLLM、训练槽、整理落盘子路径、从哪份权重起训。每条写建议和依据（`workarea/habits.md` 里已确认的条、`standard-dataset_merge`、上一张同类票、`HANDOFF`、测试建议）。不要把请组长定抄进给用户那段。

### 7.2.1 问用户

  交回必须有 **给用户** 段，顺序：结论 → 怎么走（人话步骤，**进行中的挖掘/定档写进第一步**）→ **请核对工单**（编号列出 `require/require.md` 路径，支持改）→ 已齐 / 先不用操心 → **最后**才是现在拍板，并请人看一眼工单：有要改的直接说；没问题回我一声，我们就按这个开始。口吻温柔、商量。不要「盖章」。这段只给组长在「用户点过拆单」时转述；用户没提项目工程师、只是商量时，组长不要照抄。盘上已有且没人再改的写进「已齐」。别人还在往同一套里追加，不算收口。禁止工种、房间 id、请组长定；票路径要给。

### 7.3 写法示例

  用户只写「土地负样本挖掘」。下面是对照本地地图 `env-local/datasets.md` §3.2 之后应有的层次。**服务器落点和模型版本地图没写：写成请组长定 + 建议，不编进步骤当已定，也不问用户。**

    ```markdown
    ---
    kind: proj
    goal_file: D:\path\to\goals.md
    success: 待挖的土地 toclean 在服务器上按已确认模型挖完，产物可拷回
    ---

    # 工单 · 土地负样本挖掘

    来源：用户目标文件。地图：`workarea/env-local/datasets.md` §3.2。

    ## 0 核对

    | 项 | 值 | 出处 |
    | --- | --- | --- |
    | 在岗 | 读 `online.json` / `room.md`。已有人在挖则本单不新开挖掘 | 房间，只读不进 |
    | 本机数据根 | `/path/to/data` | `link.md` 已确认 |
    | 待处理 | `/path/to/data\1-ChangeDetect\2-FieldChange\toclean` | 本地地图 §3.2 |
    | 服务器数据根 | 待确认 | `link.md` Data 已确认根未写子路径。请组长定 |
    | 土地模型 | 待确认 | `projects.md` 未写版本。请组长定 |

    ### 现在拍板

    无。

    ### 请组长定

    - 远端落哪一层：建议已确认数据根 `/path/to/home/0-data/1-ChangeDetect/2-FieldChange/toclean` 同级，依据 `link.md` Data 行 + 本地地图 §3.2。
    - 土地模型：建议用上一张同类票或房间写过的挖掘版本，不编 `latest`。

    ---

    ## 1 范围

    待处理根下，地图点名的目录：

    | 目录 | A / B | 备注 |
    | --- | --- | --- |
    | `GEOAI-((ChangeD_Zhongke))-Selfcollect-2609-(D)(OL)` | 31820 | 无 json / label |
    | `GEOAI-((ChangeD_Zhongke_dsample))-Selfcollect-2609-(D)(OL)` | 12448 | 无 json / label |
    | `toclean-GEOAI-dsample` | 3112 | 有 `draft` |
    | `toclean-new` | 2571 | 其下 `tiles_1024` 只有 `draft` |

    不挖（已是挖掘产物，除非用户改口）：`dsample`（3052）、`sample`（1705）。

    待确认：上面 4 个里挖哪几个；是否包含 `toclean-new/tiles_1024`。

    ---

    ## 2 步骤

    ### S1 拷到服务器

    | 字段 | 填写 |
    | --- | --- |
    | 工种 | `ops-engineer` |
    | 依赖 | — |
    | 本机 | `/path/to/data\1-ChangeDetect\2-FieldChange\toclean\<已确认的 GEOAI-…>` |
    | 远端 | 待确认 |
    | 技能 | `skills/tool-remote_link` |
    | 做法 | 按 tool-remote_link 上传并核对张数。路径加引号 |
    | 交付 | 远端同名目录，A / B 张数与本机表一致 |
    | 成功 | `ls` 对上 §1 点名的那几套 |

    ### S2 负样本挖掘

    | 字段 | 填写 |
    | --- | --- |
    | 工种 | `data-engineer` |
    | 依赖 | S1 |
    | 本机 | — |
    | 远端 | 待确认（S1 落点） |
    | 技能 | 待确认（地图未写用哪条挖掘链） |
    | 做法 | 用已确认的土地模型对 S1 目录挖掘。模型名待确认后写入 |
    | 交付 | 远端 `dsample` / 票内约定目录 |
    | 成功 | 产物张数写入本票 todo，可拷回 |

    ---

    ## 3 顺序

    `ops-engineer` S1 → `data-engineer` S2。S1 的远端和 S2 的模型、技能未齐之前，不派工。
    ```

### 7.4 todo.md（项目票）

    ```markdown
    # TODO

    - **ticket**: customer/proj-yymmdd-slug
    - **require**: require/require.md
    - **phase**: 待确认
    - **current**: 核对未齐
    - **next**: 用户核对工单点头后 S1
    - **blocked**: 列 require §0 里值为待确认的项，不抄目录表

    ## Checklist

    - [ ] S1 拷到服务器 · ops-engineer · 依赖 —
    - [ ] S2 负样本挖掘 · data-engineer · 依赖 S1
    ```
