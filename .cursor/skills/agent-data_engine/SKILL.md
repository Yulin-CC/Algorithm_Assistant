---
name: agent-dataengine
description: >-
  Dispatches DataEngine jobs under tools/1-DataEngine. Wired: dataset organize,
  Qwen classify, YOLO26/SAM3/GroundingPI detseg. Use when the user says 数据引擎,
  整理数据集, 预标注, 图像分类, YOLO26, SAM3, GroundingPI 检测, Qwen 检测,
  classify, detseg, jsons-det-pre, or asks to run 1-DataEngine. Qwen
  图像理解与误检过滤走 agent-smart-image（0-General/0-SmartImage）。
  GroundingPI 检测或检测+Triton SAM 分割后默认 Qwen 叠图校验；切服务前须用户确认。定档 adjust 的改形走 SmartImage 补标链，不在本技能里改框。
---

# ⚙️ Agent-DataEngine（调度 `1-DataEngine`）

  - **概述**: 用户说「数据引擎 / 整理数据集 / 预标注 / 图像分类 / YOLO26 / SAM3 / GroundingPI 检测」时触发。本 Skill **只做调度**：确认能力与后端 →（classify / GroundingPI 先探测服务）→ Read 叶包 `.skill` 并执行。GroundingPI 检测或检测+Triton SAM 分割后，默认再走 Qwen 叠图校验（`agent-smart-image` / label_grade）；切 vLLM 前先问用户。当前接线 **organize**、**classify**、**yolo26**、**sam3**、**groundingpi**（DetSeg）。旧说法「Qwen 检测」改走 GroundingPI。
  - **日期**: 2026-11-10

---

## 0 执行前检查

  - **触发**：数据引擎、整理数据集、转 YOLO、Grounding 整理、预标注、图像分类、YOLO26、SAM3、GroundingPI 检测/分割、Qwen 检测（改走 GroundingPI）、classify、detseg、`jsons-det-pre`、指定 `1-DataEngine`。
  - **仓库根 `REPO`**：本 Skill 的上两级（`skills/` 的上一级，即 `.cursor/`）。
  - **工具根 `DE_ROOT`**：`REPO/tools/1-DataEngine`。
  - **模型服务**：`REPO/server/config/vllm_server.json`、`REPO/server/config/sam.json`。classify 与 groundingpi 必须先 [§2.1] 探测通过。GroundingPI 不通时按该节在服务器拉起，不改走别的 vLLM。Agent 自己开关的服务记在 `REPO/server/ledger/runs.md`。organize / yolo26 / sam3 不探测。
  - **数据根目录 `data_root`**：必须由用户给出，**禁止猜测**。
  - **进度台账**：无 customer 票时 `<data_root>/draft/todo-dataengine.md`。有客户票时以该票 `todo.md` 为准，不要在数据集 draft 再写一份。
  - **不做**：不落地 `4-Agent-label/`；不训练、不金字塔、不基类互补（互补 → `customer/image-260827-class-complement/` 流程；实单如 `image-261020-smartcity-complement/`。开单先请用户把矩阵贴进该票 `require/require.md` 的「## 互补矩阵」）。识图、叠图质检转 `agent-smart-image`（GroundingPI 后的默认校验见 [§2.2]）。按理解改掩膜/框暂不做。label_grade 不改原 LabelMe；去掉误检只在本调度写 `jsons-det-pre` / `jsons-seg-pre` 时做。
  - **写回边界**：预标/分类只写叶声明的 draft 与 `jsons-det-pre` 等，**不写回**正式 `jsons/` / `labels/`，除非用户另开整理或合并。`capability=organize` 按叶规范写 `labels/`、`train.txt` 等训练文件。

  当前可调度（未接线的行：**停**，不要用别的叶顶替）：

  | 能力 | 后端 | 叶包 | 状态 |
  | --- | --- | --- | --- |
  | 整理 | — | `DE_ROOT/0-Data-Organize/` | **已接线** |
  | 分类 | `qwen` | `DE_ROOT/1-Image-Classify/qwen/` | **已接线** |
  | 检测/分割 | `yolo26` | `DE_ROOT/2-Image-DetSeg/yolo26/` | **已接线** |
  | 检测/分割 | `sam3` | `DE_ROOT/2-Image-DetSeg/sam3/` | **已接线** |
  | 检测/分割 | `groundingpi` | `DE_ROOT/2-Image-DetSeg/groundingpi/` | **已接线** |
  | 检测/分割 | `qwen` | `DE_ROOT/2-Image-DetSeg/qwen/` | 未接线（改走 groundingpi） |
  | 图像理解 / 误检过滤 | `qwen` | `0-General/0-SmartImage/` | 走 `agent-smart-image`。adjust 由该叶按补标链重出 |
  | GD | YOLOE / SAM3 / QWEN | `3-GD-*` / `4-GD-*` / `5-GD-*` | 未接线 |

---

## 1 进度台账（todo-dataengine.md）

  - **路径**：`<data_root>/draft/todo-dataengine.md`
  - **目的**：跨会话续跑；对话与文件冲突时以 **台账 + 磁盘产物** 为准。

### 1.1 何时读写

  **(1)** 开跑 / 续跑前先 Read；禁止无故重做已 `done`。
  **(2)** 每完成一个可恢复节点立即更新。
  **(3)** 用户说「继续 / check 进度」：读台账 → 摘要 → 执行 `next`。
  **(4)** 文件不存在：按 [1.2] 新建后再开跑。

### 1.2 模板（可增行，勿删节字段）

  状态：`pending` / `in_progress` / `done` / `blocked` / `skipped`。  
  `leaf`：`organize` | `yolo26` | `sam3` | `groundingpi` | `classify`。

    ```markdown
    # Agent-dataengine TODO

    - **updated**: YYYY-MM-DD HH:MM
    - **capability**: organize | detseg | classify
    - **backend**: yolo26 | sam3 | groundingpi | qwen | —
    - **leaf**: organize | yolo26 | sam3 | groundingpi | classify
    - **data_root**: /path/to/data
    - **work_dir**: tools/1-DataEngine/...
    - **task**: detect | segment | classify
    - **phase**: route | probe | confirm | sample | run | overlay | deliver
    - **current**: ...
    - **next**: ...
    - **blocked**: 无

    ## Meta
    - weights: ...
    - prompt: （仅 sam3）
    - classes: （classify / detseg-groundingpi）
    - conf: 0.35 | 0.45
    - n_sample: 12
    - device: 0 | cpu
    - service: （classify / groundingpi）name / base_url / model
    - sam: （仅 detseg-groundingpi 且 segment）url

    ## Checklist
    - [ ] §2 路由后端
    - [ ] §2.1 探测服务（classify / groundingpi；organize 跳过）
    - [ ] §3 确认后 Read 叶 Skill
    - [ ] 叶步骤
    - [ ] §2.2 GroundingPI 后 Qwen 校验（默认链式，中途不问）
    - [ ] §5 交付

    ## Notes
    - ...
    ```

---

## 2 路由后端

  **(1)** 整理数据集 / 转 YOLO / Grounding 整理 / CD 划分 / YOLOE val 整理 → `capability=organize`，`leaf=organize`，`work_dir=DE_ROOT/0-Data-Organize`。
  **(2)** 图像分类 / 二分类 / 多分类 / classify → `capability=classify`，`backend=qwen`，`leaf=classify`，`work_dir=DE_ROOT/1-Image-Classify/qwen`。
  **(3)** YOLO26 / yolo 出框 / 权重推理打框 → `capability=detseg`，`backend=yolo26`。
  **(4)** SAM3 / sam3 出框 / 文本提示分割 → `capability=detseg`，`backend=sam3`。
  **(5)** GroundingPI 检测/分割、给框预标、以及旧说法「Qwen 检测/分割」→ `capability=detseg`，`backend=groundingpi`，`work_dir=DE_ROOT/2-Image-DetSeg/groundingpi`。不要再调度 `2-Image-DetSeg/qwen`。
  **(6)** 只说「预标注 / 标一下」且没点名后端 → 默认 `capability=detseg`，`backend=groundingpi`，`task=detect`。用户点名 yolo26、sam3 或 segment 时按点名走。只说「数据引擎」且没指定能力 → 列出 **organize / classify / detseg**，未选则停。
  **(7)** 识图、描述、图像理解、误检过滤、叠图质检 → 转 `agent-smart-image`（`tools/0-General/0-SmartImage`）。改掩膜、改框 → 停。GD 引擎 → 未接线，停。
  **(8)** 「autolabel / 4-Agent-label」→ 过时，改走本调度；不要落地 `4-Agent-label/`。

  classify 与 groundingpi → [§2.1]；organize / yolo26 / sam3 → `phase=confirm`。GroundingPI 出框后默认链式走 [§2.2]，中途不要为切 Qwen 再停下来问。

### 2.1 探测模型服务（classify / groundingpi，未通过不得进叶）

  系统 Python（stdlib），不要为探测装 torch / 下权重。

    ```bash
    # classify：只测 default vLLM
    python "REPO/server/util/probe.py" --skip-sam
    # detseg-groundingpi detect：GroundingPI，不测 SAM
    python "REPO/server/util/probe.py" --service GroundingPI --skip-sam
    # detseg-groundingpi segment：GroundingPI + SAM TCP
    python "REPO/server/util/probe.py" --service GroundingPI
    ```

  **(1)** classify：default vLLM `GET {base_url}/models` 须 2xx。groundingpi：name=`GroundingPI` 须 2xx（不要改用 default Qwen）。segment 另须 SAM `url` TCP 通。同端口多条配置只算实际 `/v1/models` 返回的那一个 model id。
  **(2)** groundingpi 目标不通：不要换别的 vLLM，不要下模型。先看 `workenv/link.md` 里填写的那台服务器上还有没有别的 vLLM 进程。没填主机就问，不要沿用别的机器。另一台机器上的服务不算这台在用。
    - 没有其它 vLLM → 按 `workenv/link.md` 的 GroundingPI 启动脚本拉起，复探通过再进叶。
    - 有其它 vLLM → 读 `REPO/server/ledger/runs.md`。正在跑的每一条都是 `by=agent` 且 `user_requested=no` → 不询问，停掉再开 GroundingPI。用户本轮已经在跑这条 GroundingPI 任务（含「连起来 / 标完校验」）→ 占用的 Qwen 也可直接停，不必再问。其它对不上（没记录，或用户点名开着且本轮没授权换掉）→ 暂停，列占用；未确认不得停、不得开。
    - Agent 自己拉起或停掉 vLLM 后立刻改这份台账：`name`、`base_url`、`model`、`script`、时间、`by=agent`、`user_requested`。文件不存在就先建。
  **(3)** classify 目标不通：不自动开服务。其它条目 ok → 列给用户选，未选不得跑。全部不通 → `blocked=服务不可用`，停止。
  **(4)** 通过后写入台账 `service`（及 segment 的 `sam`），`phase=confirm`。用户本轮已说继续，且类别与 hint 已齐 → 按叶开 sample，不要把同一张确认单再问一遍。

  organize / yolo26 / sam3 **跳过**本节。

### 2.2 GroundingPI 后默认 Qwen 校验

  GroundingPI **detect**（矩形）或 **detect + Triton SAM segment**（多边形）完成后，默认立刻切 Qwen 做叠图质检，再按 `grade` 落盘。这是一条链，**中途不要为切服务、看 vis、是否全量再问一遍**。yolo26 / sam3 不默认跟。用户开跑时说「跳过校验 / 不要 Qwen」才跳过。

  **(1)** 切服务不必再问。默认机 GroundingPI（8082）与 Qwen（8081）通常不能同时占满 GPU：出框结束 → 停 GroundingPI → 按 README 开 default Qwen（当前 Qwen3.8-27B / 8081）→ 改 `server/ledger/runs.md`（`by=agent`，本链上的 Qwen 记 `user_requested=no`）→ `probe.py --skip-sam` 通过。不要用 GroundingPI 当识图后端。label_grade 不测 SAM。
  **(2)** 执行：Read `skills/agent-smart_image/SKILL.md` 与 `0-General/0-SmartImage/.skill/SKILL.md`。`label_grade.py --mode instance`。变化检测加 `--masks`。产物在 `draft/overlay/`：`model/` 发给模型的裁图，`vis/` 给人看的整图和 `summary.md`，`result/` 是判定 json。`wrong` 和 `adjust` 的裁图同时抄到 `draft/to_check/<类别>/wrong` 与 `adjust`。变化检测另抄 `fit`。叶包不删框。图很少（sample 已覆盖全量）或用户已说连起来 → sample 之后直接校验并写 `jsons-det-pre` / `jsons-seg-pre`，不要等「直接全量」。已有其它类框则合并，只替换本轮类别，禁止无故 `--force` 整文件冲掉。
  **(3)** 过滤：框和掩膜都只去掉 `grade=wrong`。`fit` 和 `adjust` 都保留。`adjust` 表示目标在但区域过大、不完整或错位，本步不改形状。旧结果没有 `grade` 时，`fit=miss` 或 `verdict=wrong` 当误检去掉。Qwen 写「起重机」却判 fit 这类自相矛盾按误检去掉。
  **(4)** 一次汇报 vis 路径、`draft/to_check/`、fit/adjust/wrong 和落盘计数。台账 `phase=overlay` 再 `deliver`。

---

## 3 确认后移交叶包

  **只 Read 并遵循** `work_dir/.skill/SKILL.md`。配环境先 Read `skills/tool-build_env/SKILL.md`。

  | leaf | 叶 Skill |
  | --- | --- |
  | organize | `DE_ROOT/0-Data-Organize/.skill/SKILL.md` |
  | classify | `DE_ROOT/1-Image-Classify/qwen/.skill/SKILL.md` |
  | yolo26 | `DE_ROOT/2-Image-DetSeg/yolo26/.skill/SKILL.md` |
  | sam3 | `DE_ROOT/2-Image-DetSeg/sam3/.skill/SKILL.md` |
  | groundingpi | `DE_ROOT/2-Image-DetSeg/groundingpi/.skill/SKILL.md` |

  调度层只盯：

  - `data_root` 须由用户给出。
  - organize：无 sample/run 叠图；按叶规范转换/划分；**可以**写 `labels/`、`train.txt`。
  - 预标/分类 **先小后全**：sample 给人看完再 run。
  - detseg：detect → `jsons-det-pre/`；segment → `jsons-seg-pre/`。
  - classify：产物在 `draft/classify/`。
  - sam3 必须 `--prompt`；缺 `sam3.pt` 把百度云链接给用户。
  - classify / groundingpi **不下模型**；叶只 check 环境。GroundingPI 请求须 `skip_special_tokens=false`（叶客户端已带）。
  - 预标不写正式 `jsons/` / `labels/`（整理叶除外）。
  - GroundingPI 出框后走 [§2.2] 链式校验，中途不问切服务。label_grade 不改原 json，过滤由本调度落盘。

---

## 4 通用执行约定

  - 预标/分类：未看 sample 不得 `run`。organize 不走 sample。
  - 已有非空结果默认跳过；覆盖须用户说 force。
  - 长任务后台跑，阶段结束再汇报。
  - 只改已确认叶包。禁止顺手改未确认叶。

---

## 5 交付

  **(1)** 摘要：`capability`、`backend`、路径与计数。
  **(2)** 预标/分类：声明未写正式 `jsons/` / `labels/`。GroundingPI 若做了 §2.2，写出校验计数与过滤后的 `jsons-det-pre` / `jsons-seg-pre`。organize：列出已写的 `labels/`、`train.txt`、`val.txt`、`train_segm.json` 等。
  **(3)** 台账：`phase=deliver`。

---

## 6 工具索引

  - 工具根目录：`tools/1-DataEngine/`（相对 `REPO`）

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 环境 | `skills/tool-build_env/SKILL.md` | uv 配环境 |
  | 探测 | `server/util/probe.py` | vLLM；可选 SAM TCP |
  | 叶 | `0-Data-Organize/.skill/SKILL.md` | 整理步骤 |
  | 入口 | `0-Data-Organize/util/` | 转换 / `split.py` / CD |
  | 叶 | `1-Image-Classify/qwen/.skill/SKILL.md` | 分类步骤 |
  | 入口 | `1-Image-Classify/qwen/util/classify.py` | sample / review / knowledge / run / hold |
  | 叶 | `2-Image-DetSeg/yolo26/.skill/SKILL.md` | yolo26 |
  | 入口 | `2-Image-DetSeg/yolo26/util/batch_prelabel_json.py` | sample / run |
  | 叶 | `2-Image-DetSeg/sam3/.skill/SKILL.md` | sam3 |
  | 入口 | `2-Image-DetSeg/sam3/util/batch_prelabel_json.py` | sample / run |
  | 叶 | `2-Image-DetSeg/groundingpi/.skill/SKILL.md` | GroundingPI detseg |
  | 入口 | `2-Image-DetSeg/groundingpi/util/detect_segment.py` | sample / run |
  | 校验 | `skills/agent-smart_image/SKILL.md` | GroundingPI 后默认 Qwen 叠图质检 |
  | 入口 | `0-General/0-SmartImage/util/label_grade.py` | grade=fit|adjust|wrong；不改原标注 |
  | 权重 | `_weights/` | yolo26 / sam3（classify 与 groundingpi 不用） |
  | 台账 | `<data_root>/draft/todo-dataengine.md` | 断点续跑 |
  | 台账 | `server/ledger/runs.md` | Agent 自己开关的 vLLM |

  调用方式：进入已确认叶包根目录，用该叶 `$PY` 跑该叶 CLI。

---
