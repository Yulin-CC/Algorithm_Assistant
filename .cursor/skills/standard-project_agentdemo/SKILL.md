---
name: standard-project-agentdemo
description: >-
  Builds 0-Agent-demo three slots, the train ticket config/ and data/, and
  0-Agent-demo/SKILL.md when the repo README is clear. Use when 建立 Agent-demo,
  三槽, 工作区指导, 操作卡, or after standard-project-merge when the user says
  整理项目, 合并项目, 整理一下项目. Leave unclear steps out of the card. Does
  not start training.
---

# 🧩 建立 Agent-demo

  - **概述**: QuickStart 就绪后，或用户要整理 / 合并项目时，建立 `0-Agent-demo` 三槽，把训练票的 `config/`、`data/` 写成入口能读的文件，并在项目指导已经明确时写 `0-Agent-demo/SKILL.md`。不明确的流程不写进指导。不替用户开训。
  - **日期**: 2026-11-13

---

## 0 何时读

  - **触发**：建立 Agent-demo、补三槽、写算法仓 `0-Agent-demo/SKILL.md`，或 `standard-project_merge` 做到 QuickStart 之后。用户说「整理一下项目」「合并项目」「整理项目结构」时，合并技能必须先来读本技能。
  - **不在这里**：开训、验证、推理走 `skills/agent-auto_demo/SKILL.md`。YOLOE 开集的数据文件名走该技能 [§3.1]，不在本技能展开。工作区指导的写法在 [§5]。
  - **前置：先确认仓库有 git 基线**。建槽要往仓里写 `0-Agent-demo/`、`config/`、`data/`，没有基线这些改动不可回滚。动手前先按 `skills/standard-git_repo/SKILL.md` §0 核一遍：`git rev-parse --is-inside-work-tree` 返回 `true`，且 `git log --oneline` 至少一条。
    - 没有基线：先按该技能 §1 → §3 建基线，再回来建槽。
    - 有仓但 `0-Agent-demo/` 已被跟踪：先按 §1.1 把它写进 `.gitignore` 再动手，不要接着往里写文件。
    - 仓在服务器上、本机够不着：把这一条写进该票 `todo.md` 交回组长，不跳过。
  - **原则**：三个槽都建，即使本仓库暂时只有推理。本步只建票、写文件、映射入口。

---

## 1 三槽与训练票

  `_demo_train` 的一轮不写在槽根，写在槽内票目录。下面这张票只说明角色：一轮一个目录，超参在 `config/`，本轮数据在 `data/`，入口在 `util/`。它的数据文件名是 YOLOE 开集的，别的仓库不要套。

  `/path/to/home/1-project/0-VLM/16-YOLO-E/YOLOE/0-Agent-demo/_demo_train/image-261113-smartsecurity-yoloe-v1`

    ```text
    0-Agent-demo/
    ├── _demo_train/
    │   └── image-YYMMDD-<场景>-<模型>/
    │       ├── Customer.md
    │       ├── todo.md
    │       ├── config/
    │       │   └── default.yaml          # 本票超参副本。不改仓库 config/
    │       ├── data/                     # 本轮数据入口。格式跟本仓库训练脚本
    │       ├── util/
    │       │   └── 0-train.sh
    │       ├── logs/
    │       └── 0-results/
    ├── _demo_eval/
    └── _demo_infer/
    ```

  **(1)** 把 `standard-project_merge` [§2.3] 的 QuickStart 映射写进对应票 `todo.md` 的 `entry`：

  | QuickStart | 写入 |
  | --- | --- |
  | `0-train.sh` | `_demo_train/<票>/todo.md` |
  | `1-predict.sh` / `1-inference.sh` | `_demo_infer` |
  | `2-eval.sh` | `_demo_eval` |

  本仓库没有的入口：该槽 Customer 写「本仓库暂无」，`todo` 标 `skipped`，**禁止编造命令**。验证、推理没有数据票时，在槽根放 `Customer.md` 和 `todo.md` 即可，不要为了对称造一份假的 `data/`。

  **(2)** 训练票写入 `Customer.md`（`agent-auto_demo` §2.2 批次模板，字段「待确认」）和 `todo.md`（`phase=confirm`）。不要在 `_demo_train/` 根上再放一套。

---

## 2 写 config

  `config/default.yaml` 必须写成文件，禁止空目录。

  - 不改仓库里的训练配置。票内这份是副本。
  - 文件头写本票版本、日期，以及本票 `data/` 实际用了哪些集。写明 `util/0-train.sh` 的 `devices` 为空时直接退出，不使用配置里的 `device`。
  - 字段分组跟本仓库现有训练配置，不另起一套。数值从那份配置原样抄入，文件头写明抄自哪份。仓库没有训练配置时用上游默认，Customer 标「待确认」。禁止把别的票的学习率、损失权重、增强当成新项目默认。
  - 配置里指向数据的字段，写本票 `data/` 下的相对路径。shell 传入的数据参数会覆盖它们。
  - 验证以训练入口实际读取的那份数据为准。配置里若还有一份验证后备字段，写成同一份，禁止留上一张票的路径。
  - `project` 是本票工程名；shell 的 `--project` 会覆盖。新票用新工程名，不覆盖旧 `runs/`。

---

## 3 写 data

  `data/` 必须写成训练入口真能读的文件，禁止只建空文件夹。路径必须用户给，禁止猜盘。

  - 格式跟本仓库训练脚本已经在读的那种：单个配置、索引加子文件、json 或清单都可以。不要为了整齐改成另一种。
  - 只放本轮真正训练和验证用到的集。入口没点到的文件不要放进票。
  - 有索引时，索引只列这些集，子文件和索引互相一致。每个文件头写清是什么、日期；有清单文件时写核对过的行数。
  - 类别名和标注 id 按盘上这份数据写，不从别的票抄。
  - 本轮用不到的数据种类不要建空文件凑数，也不要套用别的票的数据路径。
  - 算法仓是 YOLOE 时，文件名按 `agent-auto_demo` [§3.1]。别的仓库不要用那套开集索引名。

---

## 4 写入口

  `util/0-train.sh` 只做薄包装，转发本仓库已冻结的训练入口。

  - `PROJECT_ROOT` 从 `util/` 向上四级到仓库根。`--config` 指向本票 `config/default.yaml`。数据参数只传本仓库入口真正有的那些，指向本票 `data/`。入口没有的参数不要加。
  - 整理时 `devices` 留空。为空，或起点权重不存在，打印 `blocked` 后退出，不起进程。
  - conda 用 `standard-quickstart` 的 `CONDA_BASE`，不写死 `/path/to/home/miniconda3`。
  - 禁止改上游源码。禁止把参照票的 `0-train.sh` 原样拷进来。
  - 不建 `customer/`。配比写在 `data/`，超参写在 `config/default.yaml`。不要再写一份入口不读的数据文件。
  - 禁止改 `0-QuickStart/`、仓库 `config/`、仓库 `data/`。缺文件只在本票副本里补。
  - 没有训练入口则票内写「本仓库暂无」，`todo` 标 `skipped`，禁止编造配置和数据文件。

  - **注意**：根目录 README 的项目结构图必须画出 `0-Agent-demo/`。真正开跑再读 `agent-auto_demo`。

---

## 5 工作区指导

  写在算法仓 `0-Agent-demo/SKILL.md`。这份文件不在 Cursor 扫描目录里。写完后在 `agent-auto_demo` 加一句：该仓开做前先 Read 它。票或槽的目录树仍以 [§1] 和 `agent-auto_demo` 为准，指导文件不重复贴整棵树。

### 5.1 什么时候写

  - 项目指导或根目录 `README.md` 已经把环境、数据目录、处理脚本、训练入口、评估和推理说清楚：直接生成。先对照盘上的脚本和已经跑通的一轮。README 点了名、盘上没有的入口不要写进去。
  - 某一步文档没写清、脚本对不上、或这台机器上还没核实：这一步先不写，留给后续和用户一起敲定。不能把没核实的流程写成固定指导。
  - 可以只写已经明确的几节。缺的节不要用猜测补满。整份都不明确时，先不建这个文件。

### 5.2 正文

  体例同本仓 skill：YAML 头、emoji 标题、概述、日期、二级标题、两空格列表。一次能读完，不把 README 抄进去。下面几节只写核实过的；没核实的整节不写。

  - **0 已冻结**：主机、仓根、conda 与解释器、torch 与驱动 CUDA、当前卡。卡被别的进程占着就停，不杀进程。新数据路径仍要用户给。这些必须是这台机器上核对过的。
  - **1 环境**：写成这台机器已经走通的命令。权重只认仓内约定目录，缺了先停，不默认下载。
  - **2 数据**：本仓库训练脚本真实读取的目录。点明和产线工具的目录名不要混用。同一份数据只用一套。
  - **3 脚本对照**：服务器仓内脚本对仓内格式，产线工具对产线目录。每条一行，不写长参数。改路径，不改转换逻辑。
  - **4 训练**：不改 `0-QuickStart/`、仓库 `config/`、仓库 `data/`。新仓库的一轮按 [§1] 写在票目录。仓库里已经是槽根的，指导文件照现状写，不要改成另一种结构。
  - **5 评估和推理**：入口、看图和指标各走哪个槽。权重、验证集、卡号写在对应槽，不改上游 sh。
  - **6 停**：缺权重、数据对不上、卡被占、会覆盖已有 run、用户没给数据根。这些写进 `todo.md` 再问。其余按上面做。

### 5.3 不能写死的

  - README 和脚本不一致时，以盘上能跑的为准，并写明旧入口不要跑。不要把两边都写成正确做法。
  - 别的仓库的票结构、数据文件名、conda 环境名不要抄进来。占位路径（`path/to`、`/path/to/miniconda3`）不是已冻结项。
  - 详略参照，不要把里面的主机和数据抄到别的仓：YOLOE 的 `0-Agent-demo/SKILL.md`，SAM-CD 的 `0-Agent-demo/SKILL.md`。

---

## 6 自检

  - [ ] 三槽已建。`_demo_train` 的一轮在票目录里，不在槽根
  - [ ] `config/default.yaml` 与 `data/` 已写成入口能读的文件，且只含本轮用到的集
  - [ ] `todo.entry` 与 QuickStart 映射一致；没有的入口标 `skipped`
  - [ ] `devices` 为空时包装脚本会退出；未改仓库 `config/`、`data/`、`0-QuickStart/`
  - [ ] README 已写清的部分已写入 `0-Agent-demo/SKILL.md`。没核实的步骤没有写成固定指导；整份都不明确时，文件先不建
  - [ ] 动手前已确认仓库有 git 基线（`git log --oneline` 非空），`0-Agent-demo/` 在 `.gitignore` 里；本轮新增文件可回滚
