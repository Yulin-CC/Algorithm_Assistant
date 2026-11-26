# 🏗️ 施工蓝图

从零把一个算法仓搭到能跑。每份蓝图写清：**源码从哪来、装到哪、装什么环境、怎么验证**。服务类的（vLLM、Triton SAM）另加权重来源、启动参数和已知坑。

换新机器时，拉下助手、初始化完，说「帮我搭一下 YOLOE」，照着这里的 `yoloe.md` 走就行。

- [1 这是什么](#1-这是什么)
- [2 怎么用](#2-怎么用)
- [3 蓝图清单](#3-蓝图清单)
- [4 和 workarea 的区别](#4-和-workarea-的区别)
- [5 怎么加一份蓝图](#5-怎么加一份蓝图)
- [6 装完要做的三件事](#6-装完要做的三件事)
- [7 服务类蓝图的分工](#7-服务类蓝图的分工)

---

## 1 这是什么

一份蓝图 = 一个算法仓（或一种服务）的**从零搭建步骤**。

它和别处的分工：

| 位置 | 回答什么 | 换机器 |
| --- | --- | --- |
| **`buildenv/`（本目录）** | 这仓怎么从零搭起来，包括 vLLM / Triton 这类服务的装法和权重来源 | 不变 |
| `workarea/` | 这台机器上仓在哪、数据在哪、服务怎么起 | 重写 |
| `.cursor/server/` | 服务端口、模型名、请求方式、客户端、台账 | 不变 |
| `.cursor/skills/` | 用户说某句话时按什么流程做 | 不变 |

蓝图只管**顺序和这台仓特有的事实**；具体做法指向已有的 skill，不重复抄。

## 2 怎么用

用户说「帮我搭一下 YOLOE」时：

1. 读 `buildenv/<目录>/<仓名>.md`（如 `buildenv/0-VLM/yoloe.md`）
2. **先问用户想装到哪**。用户没指定就用蓝图里「装到」的默认路径
3. 按 §1 把源码拿到位
4. 按 §2 用 `skills/standard-project_merge` 整理
5. 按 §3 装环境（细节在 `skills/tool-build_env`）
6. 按 §4 验证
7. 装好后把**这台机器**的实际路径写进 `workarea/env-<主机>/projects.md`
8. 收尾三件事见 [§6](#6-装完要做的三件事)

第 2 步的提问：

```markdown
请确认落盘位置，回复「按此装」：

1. 装到：[蓝图的默认路径 | 你指定的路径]
2. 环境名：[蓝图里的 conda 名 | 你指定的]
```

用户说「都行」「按默认」就直接用蓝图的值，不再追问。

## 3 蓝图清单

目录按服务器的 `1-project` 分，和 `workarea/env-*/projects.md` 的读法一致。

状态说明：
- ✅ 有规范化仓库地址，直接 clone
- 📄 用官方 GitHub 源码即可，几乎无改动
- 📦 有改动，需要本地压缩包

### 视觉语言 `0-VLM`

| 仓 | 类型 | 源码 | 状态 |
| --- | --- | --- | --- |
| [vLLM](0-VLM/vllm.md) | 推理框架；**Qwen 与 GroundingPI 的服务后端**，含两家的权重来源与启动配方 | `github.com/vllm-project/vllm` | 📄 |
| [Qwen3-VL](0-VLM/qwen3-vl.md) | VLM，训练与微调 | `github.com/Yulin-CC/Qwen3-VL` | ✅ |
| [LocateAnything](0-VLM/locateanything.md) | 视觉定位 | `huggingface.co/nvidia/LocateAnything-3B` | 📄 |
| [YOLOE](0-VLM/yoloe.md) | 检测 / 开集分割 | `github.com/Yulin-CC/YOLOE` | 📄 |
| [nanochat](0-VLM/nanochat.md) | LLM | `github.com/karpathy/nanochat` | 📄 |
| [GroundingDINO](0-VLM/groundingdino.md) | 开放集检测 | `github.com/longzw1997/Open-GroundingDino` | 📄 |
| [Triton SAM](0-VLM/triton-sam.md) | 分割服务（不走 vLLM） | 无地址，Docker 自建 | ❓ |
| [SAM3](0-VLM/sam3.md) | 分割 | `github.com/Yulin-CC/SAM3` | 📄 |
| [SAM3-I](0-VLM/sam3-i.md) | 分割（交互式） | `github.com/debby-0527/SAM3-I` | 📄 |
| [FastSAM](0-VLM/fastsam.md) | 分割 | `github.com/CASIA-IVA-Lab/FastSAM` | 📄 |

### 检测 `2-YOLO`

| 仓 | 类型 | 源码 | 状态 |
| --- | --- | --- | --- |
| [YOLO26](2-YOLO/yolo26.md) | 检测 | `github.com/Yulin-CC/YOLO26` | ✅ |

### 任务 `3-TASK`

| 仓 | 类型 | 源码 | 状态 |
| --- | --- | --- | --- |
| [SAM-CD](3-TASK/samcd.md) | 变化检测 | `github.com/Yulin-CC/SAM-CD` | ✅ |

还没写的：`SCM`、`GEOLabeling`、`Agent-DEMO`，这三个需要本地压缩包（📦）。见 [todo.md](todo.md)。

## 3.1 目录怎么分

```
buildenv/
├── README.md          # 本文件
├── todo.md            # 还没写的蓝图
├── 0-VLM/             # 视觉语言
├── 2-YOLO/            # 检测
└── 3-TASK/            # 任务（变化检测等）
```

目录名与服务器 `1-project` 的顶层一致。新仓按它所属的目录放进去。

## 4 和 `workarea/` 的区别

同一个仓在两处都出现，但说的不是一件事：

```markdown
<!-- buildenv/yoloe.md -->
装到：项目根下 0-VLM/16-YOLO-E/YOLOE

<!-- workarea/env-<主机>/projects.md -->
| 0-VLM/16-YOLO-E/YOLOE | 目录 0-Agent-demo、0-QuickStart、config、data、weights |
```

前者说「装成什么相对位置」，后者说「这台机器上它在哪、里面有什么」。

## 5 怎么加一份蓝图

新建 `buildenv/<目录>/<仓名>.md`（目录按服务器 `1-project` 的顶层分），七节固定顺序：

```markdown
# <仓名>

| 项 | 值 |
| --- | --- |
| 来源 | <git url 或 团队拷贝> |
| 装到 | 项目根下 <相对路径> |
| 环境 | conda <名> / Python <版本> |
| 依赖 skill | standard-project_merge、tool-build_env |

## 1 拉源码
## 2 整理项目
## 3 装环境
## 4 验证
## 5 已知问题
## 6 后续
## 7 参考
```

第 2 节不重抄整理步骤，一句话指向 skill。第 3 节同理。蓝图的价值在**这个仓特有的路径、权重、版本约束**。

环境段摘自该仓自己的 `README.md`。仓里没写就留「待补」，不要编。

服务类蓝图（`vllm.md`、`triton-sam.md`）不受七节限制：它们多出「权重从哪拉」「启动配方」「多跳验证」这几节，因为服务本身没有 QuickStart 可看。算法仓的蓝图仍按七节写。

## 6 装完要做的三件事

不管搭的是哪个仓，服务能起来之后收这三件：

1. 把服务地址写进 `.cursor/server/config/vllm_server.json`（vLLM 系）或 `sam.json`（Triton 系）。这是程序真正读的地方。
2. 把这台机器的启动脚本绝对路径和权重目录写进 `workarea/link.md`。
3. 跑探活，确认通了：

```bash
py -3 server/util/probe.py
```

探完把结果和 PID 记进 `.cursor/server/ledger/runs.md`。

## 7 服务类蓝图的分工

`vllm.md` 和 `triton-sam.md` 写的不是算法仓，是**服务怎么从零装起来**，所以比其它蓝图多几节：权重从哪拉、启动参数口径、多跳验证。

| 想知道 | 看哪 |
| --- | --- |
| vLLM 装哪个版本、怎么装、权重地址、Qwen / GroundingPI 的启动参数 | [0-VLM/vllm.md](0-VLM/vllm.md) |
| Triton 镜像、ONNX 权重、起容器 | [0-VLM/triton-sam.md](0-VLM/triton-sam.md) |
| 这台机器的启动脚本绝对路径、权重目录 | `workarea/link.md` |
| 端口、模型名、请求怎么带参数 | `.cursor/server/services/` |
| 现在谁在跑 | `.cursor/server/ledger/runs.md` |

服务换机器只改 `workarea/link.md`；蓝图和 `server/services/` 都不用动。
