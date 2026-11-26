# 🧰 Agent Skills 工作区

给标注 / 数据产线用的 Agent 工作区：组长加五名工程师。人说话 → `skills/` 调度 → `tools/` 叶子干活。叶子不下载权重、不私自写正式 `labels/` / `jsons/`（整理叶除外）。环境默认 **uv**（`tool-build_env`，由运维装）。产线总览在仓库根目录 [README.md](../README.md)。

- [1 怎么分层](#1-怎么分层)
- [2 调度技能（`skills/`）](#2-调度技能skills)
- [3 通用工具（`0-General`）](#3-通用工具0-general)
- [4 数据引擎（`1-DataEngine`）](#4-数据引擎1-dataengine)
- [5 客户票（`customer/`）](#5-客户票customer)
- [6 模型服务（`server/`）](#6-模型服务server)
- [附录 A 真沙箱（暂未接入）](#附录-a-真沙箱暂未接入)
- [附录 B 换机：让 Cursor 看见技能](#附录-b-换机让-cursor-看见技能)

---

## 1 怎么分层

```
.cursor/
├── rules/                        # 常驻规则 algorithm-assistant.mdc
├── skills/                       # 何时唤起、怎么确认、怎么探服务
├── agents/                       # 工程师 .md；TeamLeader/ 是组长房间，不是新工种
├── customer/                     # 某一单：工单 + 进度，不复制引擎
├── server/                       # 服务：端口、模型名、客户端、台账（装法在 buildenv）
├── tools/
│   ├── 0-General/                # 本机手眼：状态、文件、识图
│   └── 1-DataEngine/             # 产线：整理、分类、检测/分割预标
└── README.md                     # 本文件
```

| 层 | 干什么 | 不干什么 |
| --- | --- | --- |
| `skills/` | 路由、闸门、确认话术、台账 | 不写具体转换/推理代码 |
| `tools/` 叶 | `.skill` + `util/` 真跑脚本 | 不拷进 customer；Qwen 叶不下权重 |
| `customer/` | 类名、路径、点位、GoldSet、todo | 不复制 classify/detseg 引擎 |
| `server/` | 服务表 + HTTP/gRPC 客户端 + probe | 不在本仓库起 vLLM/SAM 进程；不写启动脚本路径（那在 `workarea/link.md`）；不写装法（那在 `buildenv/`） |

约定：

- 数据根目录必须用户给，禁止猜盘。
- 预标 / 分类只写 `draft/`、`jsons-det-pre` 等；正式 `jsons/` / `labels/` 要用户另开 **整理** 或合并。
- 有客户票时进度只写该票 `todo.md`，不要在数据集 `draft/todo-*.md` 再写一份。
- 未经同意不要动 `/path/to/PATH`。

---

## 2 调度技能（`skills/`）

| Skill | 功能 |
| --- | --- |
| `agent-data_engine` | 数据引擎总调度。已接线：整理、Qwen 分类、YOLO26、SAM3、GroundingPI。预标没点名后端时默认 GroundingPI；旧说法「Qwen 检测」也改走它。分类与 GroundingPI 先 probe。出框后交回组长，质检与落盘归 `agent-smart_image`。GD 叶未接线则停。 |
| `agent-customer_task` | 在 `customer/<kind>-<yymmdd>-<slug>/` 建票：`.skill` + `require` + `util` + `todo.md`。`kind` 含 `proj`（项目工单，不绑叶子）。 |
| `agent-pyramidlabel` | 金字塔迭代扩标。 |
| `agent-auto_demo` | 各算法仓 `0-Agent-demo` 三槽训练 / 验证 / 推理。三槽由运维在派工前核对或新建，结论写入派工。确认 `Customer.md` 再开跑。 |
| `agent-source_adapt` | 把上游一个功能切进指定仓库。派工写明仓库、commit、功能名。不整包升级，不开训。日常三槽仍不改上游。 |
| `agent-smart_image` | 图像理解、掩膜/框三档质量判断、漏检补标和 adjust 调整。叶子 `0-General/0-SmartImage`。不改原标注。 |
| `tool-build_env` | 给任意叶配 Python：uv 建 venv → 按需 CUDA/torch → 再装 `PKGS`。conda / 裸 pip 仅备选。 |
| `tool-remote_link` | 本机 Windows ↔ 远端 Ubuntu。主机以 `workarea/link.md` 已确认行为准。SSH、上传核对。 |
| `standard-git_repo` | git 仓库规范。建仓库 / `git init` / 上版本控制走分类、`.gitignore` 三分法、首次基线；提交远程 / push / 同步 GitLab 走凭据校验、脱敏、推送。含密钥红线与回滚。 |
| `standard-*` | README / 脚本 / skill 写法、数据集合并等规范。给 git 克隆看的项目首页只用 `standard-create_readme_git`，平时 README 仍用 `standard-create_readme`。 |

图像理解、掩膜/框质量判断、漏检补标和 adjust 调整走 `agent-smart_image` → `tools/0-General/0-SmartImage`（不走 DataEngine）。不改原标注。

工程师（`.cursor/agents/`；项目、数据、模型、测试、运维含单模块都由组长派）：`project-engineer` 先对在岗落盘再拆单，盘上已有的（如 `dsample`）不问不挖，执行决策找组长、不逐步问用户；`data-engineer` 数据处理；`train-engineer` 模型（训练、验证、推理；派工写明时做源码适配）；`test-engineer` 测试（Testdir 指标 + Testdir/Feedback 可视化；新版本对照上一版）；`ops-engineer` 项目整理、装环境（`tool-build_env`）、未归类杂活，以及盯这轮工作有没有卡点。`listen` 的 `READY` 不算活已经在往前走。组长之间按项目等活，用 `agents/TeamLeader/room.py`，不另建组长工程师。工程师不进房间，心跳只用派工里的组长 AgentID。五名工程师不钉模型，跟随组长这条对话当前的模型，派工时也不要另指定模型。

---

## 3 通用工具（`0-General`）

### 3.1 图像理解 · `0-SmartImage`

调度技能 `agent-smart_image`。服务读 `server/config/vllm_server.json` 的 default（当前 Qwen3.8-27B / 8081）；不下 Qwen 权重。DetSeg 的 `--gate` 不是入口。

| # | 能力 | 落点 | 状态 |
| --- | --- | --- | --- |
| 1 | 图像理解 / 描述 | `util/describe.py` | 已实现。单张 stdout；数据集 `draft/describe/result/jsons/{stem}.json`。两期拼图在 `draft/describe/model/` |
| 2 | 图像掩膜 / 框的分析 | `util/analysis.py` | 已实现，归测试工程师。测试可视化：`--pred`、省略 `--gt`。变化检测写 `repro/<版本>/analysis/`。缺结果时问 Qwen。有 `draft/miss/` 时计入漏检。不改写原标注 |
| 3 | 图像掩膜 / 框的三档质量判断 | `util/label_grade.py` | 已实现。`fit` 贴合，`adjust` 过大、不完整或错位，`wrong` 误检。叠图在 `util/overlay.py`，不调用模型。预标过滤写 `draft/overlay/`，`wrong` 和 `adjust` 的裁图另抄到 `draft/to_check/<类别>/`。变化检测 `--masks` 另抄 `fit`。漏检和差检先确认提示词，再走 Qwen 报点加 Triton SAM，不走 GroundingPI。不改写原标注 |
| 4 | 图像掩膜 / 框的调整 | `util/opt_adjust.py` | 已实现。定档 `adjust` 的框中心当报点，再走补标链，写 `draft/adjust/`。漏检 `label_miss.py`，补标 `opt_fill.py`。不改原标注 |

### 3.2 本机工具 · `1-LocalMachine`

任意 Agent 可调的本机原语（CLI / `class Tools` / 函数）。无第三方依赖。

| 模块 | 功能 |
| --- | --- |
| `util/system.py` | CPU/内存、GPU（nvidia-smi）、占用进程、磁盘、开机时长 |
| `util/files.py` | 列目录、搜索、读写追加替换、建删、mv/cp、zip/unzip（防 zip-slip） |
| `util/run.py` | 在允许路径内跑 `.py` / `.sh`，超时并截断输出 |
| `util/paths.py` | **路径白名单**（不是容器沙箱） |

默认允许根：家目录、临时目录、已存在的 `/path/to/data` `/path/to/home/1-project` `/path/to/docs` `/path/to/home` `/path/to/home` `/tmp`。再加 `LOCALMACHINE_ROOTS`。

```bash
python tools/0-General/1-LocalMachine/util/system.py gpu
python tools/0-General/1-LocalMachine/util/files.py ls "/path/to/data"
```

---

## 4 数据引擎（`1-DataEngine`）

由 `agent-data_engine` 调度。预标默认流程：**确认 → sample 给人看 → 全量 run**。权重目录约定：`tools/1-DataEngine/_weights/`（叶 skill 写具体名）。

### 4.1 整理 · `0-Data-Organize`（已接线）

把**已有标签**整理成可训练布局。不预标、不训练。

| 目标规范 | 能做什么 |
| --- | --- |
| YOLO | LabelMe/VOC/COCO ↔ txt、`labels/`、`train.txt`/`val.txt` |
| Grounding | 每图 COCO / caption、可选 ultralytics cache |
| 变化检测 | 配准、切片、json→mask、CD 划分 |
| YOLOE val | 校验用划分 |

可选按 `Train-[project]-[date]-xxxxx` 成对重命名。须用户确认后才覆盖写盘。

### 4.2 图像分类 · `1-Image-Classify/qwen`（已接线）

Qwen 视觉二/多分类。不写正式 `labels/`。

- `sample`：抽图拷到 `draft/classify/cache/sample/<类>/` 给人改文件夹
- `run`：高置信进 `draft/classify/result/<类>/`，低置信进 `_待审/`
- 类名、提示、knowledge 在票 `require` 或运行参数里，不写死在叶 skill

### 4.3 检测 / 分割预标 · `2-Image-DetSeg`（已接线）

调度默认后端是 **GroundingPI**。落盘形态对齐：sample 叠图 + LabelMe；全量 `jsons-det-pre`（框）或 `jsons-seg-pre`（多边形）。**不覆盖**正式 `jsons/` / `labels/`。GroundingPI 出框后默认再走 `0-SmartImage` 叠图校验。

| 后端 | 怎么出框 | 适用 |
| --- | --- | --- |
| `groundingpi` | vLLM GroundingPI 给框；分割再交 Triton SAM | 预标默认。旧说法「Qwen 检测 / 分割」走这里 |
| `yolo26` | 本地 YOLO26 权重 | 闭集、已有权重。用户点名才走 |
| `sam3` | 本地 `sam3.pt` + 文本提示 | 开放词汇概念。用户点名才走 |

旧的 `2-Image-DetSeg/qwen` 叶已删除。检测/分割只剩这三个；门控、识图、误检过滤由 `agent-smart_image` 的 `label_grade.py` 承担。

### 4.4 Grounding 数据集引擎（未接线）

`3-GD-YOLOE` / `4-GD-SAM3` / `5-GD-QWEN` 占位。调度表里未接线则不要用别的叶顶替。

---

## 5 客户票（`customer/`）

一张活一个目录：`<kind>-<yymmdd>-<ascii-slug>/`（`kind` = `image` / `cd` / `gd`）。

```
customer/<票>/
├── .skill/SKILL.md      # 通用流程：读 require → 走哪片叶 → 确认 → 交付
├── require/             # 本单：类、路径、点、GoldSet、yaml
├── todo.md              # 进度
└── util/                # 仅本单胶水，禁止复制叶引擎
```

| 票 | 功能 |
| --- | --- |
| `image-260811-pyramidlabel` | 金字塔扩标（FloatingObject：boat/person）；训练脚手架在 `util/quickstart/` |
| `image-260827-class-complement` | 基类互补流程与脚本；工单模板，`data_root` 空则停 |
| `image-260902-changedetect` | 建筑变化描述，走 `0-SmartImage` |
| `image-260911-classify-field` | 田间变化数据，只分类 **B**：农田 / 非农田，七点 |
| `image-260912-qwen-smartcity` | 智慧城市 testset 检测。旧票，原走已删除的 qwen 叶，仅留档 |
| `image-260922-qwen-testset` | 测试集航线检测。旧票，原走已删除的 qwen 叶，仅留档 |
| `image-260924-agri-box2seg` | 农业农村：框转多边形 |
| `image-260926-roadcrack-fengqing` | 道路裂缝，只出框 |
| `image-260927-classify-firelane-crops` | 消防通道 crop 的 mask 门控分类 |
| `image-260927-rm-customer` | 旧模型推理：截图与预测 json |
| `image-261010-tocleanset-pyramid` | tocleanset（FieldShed，779 张）金字塔扩标，YOLO26；工单在 require，脚本复用 260811 |
| `image-261013-tinroof-pyramid` | TinRoof 铁皮屋顶金字塔扩标；种子 `zzz-TinRoof/gold`，待标 `toclean` |
| `image-261020-smartcity-complement` | SmartCity 类别补全：金标 `Testset`，互补 `Trainvalset` |
| `image-261021-smarttraffic-prelabel` | SmartTraffic testset 按 require 矩阵补框（SAM3 / 旧 Qwen 叶 / YOLO26 权重） |
| `image-261026-smarttraffic-yoloe` | SmartTraffic YOLOE 试标 car / truck，写 `jsons-det-pre`，不改正式 `jsons/` |
| `image-261106-det-vehicle-groundingpi` | GEOAI 样本：GroundingPI 出框，Triton SAM 出多边形。胶水在票 `util/`，不走 Qwen detseg 叶 |

进度在各票 `todo.md`。换类/换路径只改 `require/`，不要改票内 `.skill`。

---

## 6 服务（`server/`）

叶子连**已经在跑**的服务，不在本仓库起服务。服务本身（端口、模型名）与装法分别在 `server/` 和仓库根 `buildenv/0-VLM/`，启动脚本在哪台机器上、叫什么，在 `workarea/link.md`。

| 路径 | 功能 |
| --- | --- |
| `server/README.md` | 服务总表与边界说明 |
| `server/services/*.md` | 一服务一篇：端口、模型名、请求注意点 |
| `buildenv/0-VLM/vllm.md` | vLLM 装法、版本约束、Qwen / GroundingPI 权重来源与启动参数 |
| `buildenv/0-VLM/triton-sam.md` | Triton 镜像、ONNX 权重、起容器 |
| `server/config/vllm_server.json` | 多路 vLLM。地址和模型名以这个文件为准。`default: true` 是分类和识图用的 Qwen。GroundingPI 不是默认。FP8 不是默认 |
| `server/config/sam.json` | Triton SAM。地址以这个文件的 `url` 为准。另一台容器不作为默认 |
| `server/util/vllm_client.py` / `groundingpi_client.py` / `sam_client.py` | OpenAI 兼容 chat、GroundingPI、SAM gRPC |
| `server/util/probe.py` | 调度侧探活（`--skip-sam` 只探 vLLM） |
| `server/util/servers_io.py` | 读配置、解析 default |
| `server/ledger/runs.md` | 起停台账：谁何时起了哪个服务、PID、日志 |

分类、识图、误检过滤探 default vLLM。GroundingPI 检测/分割探 name=`GroundingPI`，不要改用 default Qwen；分割再探 `sam.json` 的 TCP。organize / yolo26 / sam3 不探 vLLM。

---

## 附录 A 真沙箱（暂未接入）

`1-LocalMachine` 的 `safe_path` 是**路径白名单**：路径必须落在允许根下。它**不是**进程/容器隔离——白名单里的脚本仍可能访问环境其余部分。

以后若要「模型生成的代码不能碰宿主机」，不要在本包再造假沙箱，优先接：

| 项目 | 用途 | 链接 |
| --- | --- | --- |
| AgentScope Runtime Sandbox | 代码 / 浏览器 / 文件系统隔离；Docker 或阿里云 AgentRun | https://runtime.agentscope.io/zh/sandbox/sandbox_service.html |
| AIO Sandbox（All-In-One） | 代码解释器 + 无头浏览器；REST / MCP；云上对应阿里云函数计算 | https://github.com/agent-infra/sandbox |

**状态：未接入。** 本机改 `/path/to/data` 的产线继续只用白名单。

---

## 附录 B 换机：让 Cursor 看见技能

Cursor 扫描 **`<工作区>/.cursor/skills/`**。本仓技能已在该目录，打开本工作区即可按 YAML `description` 自动调度。

**不要**把本仓 `skills/` 链进 `~/.cursor/skills/`：各 SKILL 用「本文件上两级」当 `REPO`，链过去会指到用户家目录。

换机：用本仓库当工作区打开。`REPO` = 本 README 所在目录（`.cursor/`）。本机 ↔ 服务器地图在上一级 `README.md`。叶子仍用 `tools/`、`customer/` 下的 `.skill/`，不要改成 `skill/`。开**新对话**后技能列表才会刷新。
