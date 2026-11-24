---
name: agent-auto-demo
description: >-
  Runs train, eval, or infer from a repo 0-Agent-demo three-slot workspace
  without editing upstream source. Use when the user says 训练, 验证, 推理,
  跑 demo, autodemo, or asks to set up Agent-demo. Confirm Customer.md before run.
---

# 🧪 Agent AutoDemo（训练 / 验证 / 推理）

  - **概述**: 用户说「整理 Agent-demo / 帮忙训练、验证或推理 / 跑 demo / autodemo」时触发。组长派运维在派工前检查 `0-Agent-demo` 是否完备，把结论写入派工（已齐 / 已构建 / 用户跳过构建）。工程师按该结论执行；派工没有这句就停回组长。确认需求 → 发现本仓库入口 → 只在 `util/` 包一层 → 写台账与结果。三个槽流程相同、入口不同。**禁止改仓库源码**。不预设模型族。
  - **日期**: 2026-11-17

---

## 0 执行前检查

### 0.1 工作目录门禁（强制）

  算法仓上的训练 / 验证 / 推理，工作目录门禁由组长派运维在派工前做完。工程师不向用户再问「构建还是跳过」。未写入派工结论前不得开跑、不得改源码。

  **组长（派工前）**

  **(1)** 定位 `work_root`：默认仓库根下的 `0-Agent-demo`。换仓库时询问，禁止猜绝对路径。把仓库和本轮槽写入派给运维的 prompt。

  **(2)** 运维对照 [§3] 检查完备性：

  | 检查项 | 完备条件 |
  | --- | --- |
  | 三槽 | `_demo_train` / `_demo_eval` / `_demo_infer` 都在 |
  | 本轮槽 | 与任务对齐的槽存在（训练 / 验证 / 推理） |
  | 槽内 | `Customer.md`、`todo.md`、`customer/`、`util/`、`logs/`、`0-results/`。YOLOE 不按这行，见 [§3.1] |

  **(3)** 仓里已有 `0-Agent-demo/SKILL.md` 就由运维先 Read（环境、数据格式、脚本对照、训练注意事项、评估和推理、何时停）。还没有时运维按 `standard-project_agentdemo` [§5]：项目指导明确就补上，不明确就交回组长和用户敲定，不要把没核实的流程当固定指导。再 Read 仓库根 `README.md`。

  **(4)** 把检查结果告诉用户，并询问（禁止自行决定）：

  - 不完备：「工作目录不齐，需要我构建，还是跳过？」
  - 已完备：「工作目录已齐，基于现有槽继续？」

  **(5)** 按用户选择写入派工，再派工程师。组长自己不开训、不开评、不开推。

  | 选择 | 派工里写 |
  | --- | --- |
  | 构建 | 组长派运维按 [§3] 与 `standard-project_agentdemo` 补齐三槽和训练票，派工写「已构建」 |
  | 跳过 | 派工写「用户跳过构建」 |
  | 继续 | 派工写「已齐」 |

  **工程师（接到派工）**

  - 派工写明「已齐」或「已构建」：按该结论进入 [§4]，不向用户重问。
  - 派工写明「用户跳过构建」：在本槽 `todo.md` Notes 写明；仍用该槽展开，禁止另起目录。
  - 派工没有上述结论，或盘上和派工对不上：停，问组长。不自己建槽，不改源码。
  - **注意**：跑起来之后的停，是这一跑交回组长。用户已经确认的开训目标仍有效，组长接着派下一棒，不把目标交回用户。

  - **注意**：跳过 ≠ 可以不用工作目录。改变量、开跑、写结果都在对应槽里做。
  - **注意**：禁止没看 `0-Agent-demo` 就直接改 `0-QuickStart` 或开训 / 开评 / 开推。

### 0.2 其余前置

  - **任务槽 `slot`**：`_demo_train` / `_demo_eval` / `_demo_infer`。组长派工前确定并写入派工。工程师照派工；没写就停回组长。本轮只动一个槽。
  - **进度台账**：`<work_root>/<slot>/todo.md`（⭐ 强制维护，见 [§1]）。
  - **用户需求**：`<work_root>/<slot>/Customer.md`（见 [§2]）。未确认项写「待确认」，**确认前不得开跑**。
  - **源码边界**：**禁止**修改训练/推理源码、第三方库、已有 `0-QuickStart/scripts/`。缺能力只在 `<slot>/util/` 加包装脚本。把上游一个功能切进仓库不走本技能，走 `agent-source_adapt`。
  - **入口**：从本仓库自己发现（见 [§5]），写入 Customer。禁止把某一模型栈写成默认入口。
  - **新项目**：合并或整理仓库时，QuickStart 之后按 `standard-project_agentdemo` 建三槽和训练票，再回到本 Skill 填 Customer。

---

## 1 进度台账（todo.md）

  - **路径**：`<work_root>/<slot>/todo.md`
  - **目的**：断点续跑；新会话以文件为准，不依赖对话记忆。

### 1.1 何时读写

  **(1)** **开跑 / 续跑前（强制）**：先 Read 台账；从未完成项继续，禁止无故重做已 `done`。

  **(2)** **每完成一个可恢复节点后（强制）**：立即更新状态、路径、`next`，再继续。

  **(3)** **用户说「继续」「接着跑」「check 进度」**：先读台账，摘要后再执行 `next`。

  **(4)** **文件不存在**：按 [1.2] 新建后再开跑。

### 1.2 模板（可增行，勿删节字段）

  状态：`pending` / `in_progress` / `done` / `blocked` / `skipped`。

    ```markdown
    # Agent-autodemo TODO

    - **updated**: YYYY-MM-DD HH:MM
    - **work_root**: 0-Agent-demo/<slot>
    - **slot**: _demo_train | _demo_eval | _demo_infer
    - **phase**: confirm | run | report | done
    - **current**: …
    - **next**: …
    - **blocked**: 无 | …

    ## Meta
    - conda: …
    - entry: 本仓库启动命令（发现后填写）
    - customer: Customer.md §YYYYMM
    - spec: customer/xxx.md（若有）
    - log_dir: …/logs
    - results_dir: …/0-results

    ## Checklist
    - [ ] §0.1 工作目录门禁（完备 / 构建 / 跳过）
    - [ ] §2 确认 / 填写 Customer.md
    - [ ] §5 发现并冻结本仓库入口
    - [ ] §4 检查环境与产物路径
    - [ ] §4 执行（按单元一行）
    - [ ] §4 写回 0-results
    - [ ] §4 交付摘要

    ## Runs
    | id | status | artifact | note |
    | --- | --- | --- | --- |
    | … | pending | | |

    ## Notes
    - …
    ```

### 1.3 更新规则

  - 保留历史 `done` 行；`current` / `next` 始终非空。
  - 台账写 `done` 但产物不存在 → 改回 `pending` / `blocked`。
  - 对话与文件冲突时，以 **台账 + 磁盘** 为准。

---

## 2 用户需求（Customer.md）

  - **路径**：`<work_root>/<slot>/Customer.md`
  - **谁写**：用户自写，或 Agent **逐项询问**后代填。禁止把对话猜测当成已确认。

### 2.1 引导清单（缺一项就问）

  | 项 | 必须确认 |
  | --- | --- |
  | 目的 | 这一轮要证明或对比什么 |
  | 环境 | conda / 设备 |
  | 任务 | `train` / `eval` / `infer`（与 `slot` 对齐） |
  | 入口 | 本仓库已有启动命令；没有则先发现再写，禁止编造 |
  | 模型 | 权重 / ckpt；文件须存在（训练可写「从哪份预训练起」） |
  | 数据 | 配置文件或数据目录 |
  | 规格 | 可选：`customer/*.md`（问法表、类别表、划分等，形态随任务） |
  | 成功标准 | 怎样算跑完、怎样算达到目的 |
  | 结果 | 文档=`0-results/`；日志=`logs/`；可视化或权重落点 |

### 2.2 批次模板

  按月份追加，旧批次不删：

    ```markdown
    ## YYYYMM

    1. 目的：…
    2. 环境：`conda activate <env>`
    3. 任务：train | eval | infer
    4. 本仓库入口：（发现后填写，例如 `bash 0-QuickStart/1-predict.sh`）
    5. 模型 / ckpt：

        | tag | path |
        | --- | --- |
        | … | … |

    6. 数据：…
    7. 本批规格：`customer/xxx.md`（没有则写「无」）
    8. 成功标准：…
    9. 结果：

        a. 文档写回：`0-results/`
        b. 可视化或权重：（用户指定）
        c. 日志：`logs/`
    ```

  - **注意**：写完后同步 `todo.md` 的 Meta / Runs，勾选 Checklist「§2」。
  - **注意**：阈值、提示词、类别名等任务细节放 `customer/`，不要写进本 Skill。

---

## 3 目录结构

  三个槽结构相同（均相对 `work_root`）：

    ```
    0-Agent-demo/
    ├── _demo_train/
    ├── _demo_eval/
    └── _demo_infer/
        ├── Customer.md       # 用户需求（按月追加）
        ├── todo.md           # 进度台账
        ├── customer/         # 本批规格（形态随任务）
        ├── util/             # 包装脚本；禁止改仓库源码
        ├── logs/             # 机器可读日志
        └── 0-results/        # 给人看的对照文档
    ```

  - **注意**：`customer/` 不是固定「文件名 | 提示词」表。检测开集可以是问法表，闭集可以是类别列表，训练可以是数据配比说明。
  - **注意**：仓库已有入口时，`util/` 只做薄包装（改变量、记日志、转发命令）。不要把训练/推理主逻辑重写进 `util/`。
  - **注意**：上面是通用槽。YOLOE 的一轮写在槽内的票目录，目录见 [§3.1]，不要在 `_demo_train/` 根上补 `customer/`。
  - **注意**：SAM-CD 用上面的通用槽。开做前先 Read 该仓 `0-Agent-demo/SKILL.md`（环境、数据格式、脚本对照、何时停）。土地变化**负样本挖掘**（模型易误报的连通域 → `dsample/`，再送下一轮训练）归**数据工程师**，做法在该仓 SKILL [§5]，不派模型工程师。

### 3.1 YOLOE 票

  只在算法仓是 YOLOE 时用。三槽仍是 `_demo_train` / `_demo_eval` / `_demo_infer`。开做前先 Read 该仓 `0-Agent-demo/SKILL.md`（环境、数据格式、脚本对照、何时停）。一轮训练、验证或推理不写在槽根，写在槽里的票目录。参照：

  `0-Agent-demo/_demo_train/image-261113-smartsecurity-yoloe-v1/`

    ```
    <ticket>/
    ├── Customer.md
    ├── todo.md
    ├── config/
    │   └── default.yaml          # 超参。不改仓库 config/train_open.yaml
    ├── data/
    │   ├── 0-YOLO.yaml           # 索引。train / val 指向子 yaml
    │   ├── 0-Grounding.yaml
    │   ├── train-yolo_dataset/
    │   └── val-dataset/
    ├── util/
    │   └── 0-train.sh            # 薄包装，转发 0-QuickStart/scripts/train_open.py
    ├── logs/
    └── 0-results/
    ```

  - **票名**：`image-YYMMDD-<场景>-yoloe`。新版本另开一张票，不改旧票的工程名和 yaml。
  - **不建** `customer/`。配比写在 `data/`，超参写在 `config/default.yaml`。不要再写 `data/train_colorcar.yaml`。
  - **入口**：`util/0-train.sh` 的 `--config` 指向本票 `config/default.yaml`，`--data` 指向本票 `data/0-YOLO.yaml`，`--grounding-data` 指向本票 `data/0-Grounding.yaml`。仍转发 `0-QuickStart/scripts/train_open.py`。
  - **验证**：以 `data/0-YOLO.yaml` 的 `val` 为准。`train_open.py` 先读这个索引；索引里有 val，就不会用 `config/default.yaml` 的 `val_data`。
  - **台账**：`todo.md` 和 `Customer.md` 放票目录。[§1] 的路径在 YOLOE 上指这张票，不指槽根。
  - **禁止**改 `0-QuickStart/`、仓库 `config/`、仓库 `data/`。缺文件只在本票副本里改。

---

## 4 通用工作流

  三个槽共用顺序：**§0.1 门禁 → 确认需求 → 发现入口 → 检查环境 → 执行 → 写回 → 交付**。槽位差异只在入口和产物，见 [§4.7]–[§4.9]。

  - **注意**：未过 [§0.1] 不得进入本节，不得省略工作目录。

### 4.1 确认 Customer

  **(1)** 确认已过 [§0.1] 门禁，确认 `slot`，Read `Customer.md` + `todo.md`。

  **(2)** 标出「待确认」，用表格问用户，填回 Customer，同步台账。

  **(3)** 入口命令、权重/数据、结果落点任一不存在 → `blocked`，停止这一跑并交回组长。用户已经确认的开训目标仍有效。

### 4.2 发现并冻结入口

  按 [§5] 找到本仓库启动方式，写入 Customer「本仓库入口」和台账 `entry`。只改 `util/` 包装，不改入口源码。

### 4.3 环境

  **(1)** `conda activate` Customer 里的环境。

  **(2)** 设备、额外权重以本仓库文档为准；没有则询问，不假设路径。

### 4.4 执行

  对 Runs 表每个非 `done` 的单元：用 `util/` 包装调用已冻结的入口。每完成一个单元立刻更新 `status` 与产物路径。

  - 长任务可后台跑，但必须把日志路径写入台账后再结束本步。
  - 多卡：用用户指定的设备；不要抢正在跑的任务。

### 4.5 写回 0-results

  把对照结论追加到 `<slot>/0-results/`（markdown）。机器日志留在 `logs/`。历史章节保留。

### 4.6 交付

  向用户摘要：跑了什么、产物路径、是否达到成功标准、未完成项。台账 `phase=done`，`next=等待用户看结果`。

### 4.7 训练槽 `_demo_train`

  - **入口**：优先 `0-QuickStart/0-train.sh` 或 `0-QuickStart/scripts/train.py`。
  - **产物**：权重进本仓库约定的 `runs/`（或用户指定）；日志可软链到本槽 `logs/`。
  - **规格**：`customer/` 可放数据配比、超参对照，不要改仓库 `config/` 源文件除非用户明确要求。YOLOE 的配比和超参放本票 `data/` 与 `config/default.yaml`，见 [§3.1]。
  - **注意**：训后看图走 `_demo_infer`，指标走 `_demo_eval`。训练槽不放推理/验证主脚本。

### 4.8 验证槽 `_demo_eval`

  - **入口**：优先 `0-QuickStart/2-eval.sh` 或 `0-QuickStart/scripts/eval.py`。
  - **Runs**：按「模型 × 验证集」一行。
  - **产物**：机器日志进 `logs/`，对照表追加 `0-results/`。
  - **注意**：没有评估入口的仓库，该槽 `todo` 标 `skipped`，不要编造 eval 命令。

### 4.9 推理槽 `_demo_infer`

  - **入口**：优先 `0-QuickStart/1-predict.sh` / `1-inference.sh` 或 `scripts/inference.py`。
  - **规格**：`customer/` 随任务（问法表、类别表、整目录均可）。
  - **产物**：可视化写到**该数据集根下的 `repro/<模型名>-<yymmdd>[-<后缀>]/`**（`vis/`、`crops/` 等），不要堆在票的 `0-results/`。票 `0-results/` 只放指标、对照表和报告。json / 日志进 `logs/`。
  - **注意**：阈值、提示词不是全局默认，写在 Customer 或 `customer/`。

---

## 5 发现本仓库入口

  按下列顺序查找，找到就停下并与用户确认，**禁止编造命令**：

  **(1)** `0-QuickStart/` 下的 `*train*` / `*predict*` / `*infer*` / `*eval*` 脚本。

  **(2)** 仓库 `README`、`config/` 里写明的启动方式。

  **(3)** 用户在对话或 Customer 里给出的命令。

  写入对应槽：

  | 找到的入口 | 写入槽 |
  | --- | --- |
  | `*train*` | `_demo_train` |
  | `*eval*` | `_demo_eval` |
  | `*predict*` / `*infer*` | `_demo_infer` |

  - **注意**：找不到入口 → 该槽 `blocked` 或 `skipped`，请用户指定。不要默认 `ultralytics` / 某个 `.pt` 名称。
  - **注意**：可只读 import 仓库已有脚本（视为调用，不是改源码）。

---

## 6 工具索引

  - 工具根目录：`<work_root>/<slot>/`

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 台账 | `<slot>/todo.md` | 断点续跑；强制读写 |
  | 需求 | `<slot>/Customer.md` | 用户确认项 |
  | 规格 | `<slot>/customer/*` | 本批任务细节（形态随项目） |
  | 包装 | `<slot>/util/` | 只包装本仓库入口，不改源码 |
  | 日志 | `<slot>/logs/` | 机器可读 |
  | 文档 | `<slot>/0-results/` | 给人看的对照 |
  | 建槽 | `standard-project_agentdemo` | 组长派运维在派工前建三槽、训练票的 config / data，以及工作区指导 [§5]。模型工程师不建槽 |

  - **注意**：具体 py / sh 文件名随仓库变化。本 Skill **不**把某一仓库的脚本名当成通用入口。
  - **注意**：未激活 Customer 指定的 conda 时，不得用系统 Python 硬跑。缺环境交回组长，由组长派运维按 `tool-build_env` 装好再派回。

---

## 7 拍板摘要

  | 项 | 结论 |
  | --- | --- |
  | `work_root` | 默认 `0-Agent-demo`。组长派工前检查完备；工程师按派工里的已齐 / 已构建 / 用户跳过构建执行 |
  | 门禁 | 组长询问构建、跳过或继续，并把结论写入派工。派工没有结论，工程师停回组长，不得开跑 |
  | 三个流程 | 训练 / 验证 / 推理，结构相同，入口不同 |
  | 源码 | 不改；脚本只进对应 `util/` |
  | 需求 | `Customer.md`，Agent 可引导代填 |
  | 台账 | `todo.md`，强制维护 |
  | 入口 | 从本仓库发现，不预设模型族 |
  | 新项目 | 运维按 `standard-project_agentdemo` 建槽、训练票和工作区指导。README 不明确的步骤不写进指导 |
  | 规格细节 | 放 `customer/`，不写进本 Skill。YOLOE 票见 [§3.1] |
