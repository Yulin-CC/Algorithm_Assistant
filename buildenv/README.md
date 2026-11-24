# 🏗️ 施工蓝图

从零把一个算法仓搭到能跑。每份蓝图写清：**源码从哪来、装到哪、装什么环境、怎么验证**。

换新机器时，拉下助手、初始化完，说「帮我搭一下 YOLOE」，照着这里的 `yoloe.md` 走就行。

- [1 这是什么](#1-这是什么)
- [2 怎么用](#2-怎么用)
- [3 蓝图清单](#3-蓝图清单)
- [4 和 workarea 的区别](#4-和-workarea-的区别)
- [5 怎么加一份蓝图](#5-怎么加一份蓝图)

---

## 1 这是什么

一份蓝图 = 一个算法仓的**从零搭建步骤**。

它和别处的分工：

| 位置 | 回答什么 | 换机器 |
| --- | --- | --- |
| **`buildenv/`（本目录）** | 这仓怎么从零搭起来 | 不变 |
| `workarea/` | 这台机器上仓在哪、数据在哪、服务怎么起 | 重写 |
| `.cursor/server/` | vLLM / SAM 这些服务怎么装 | 不变 |
| `.cursor/skills/` | 用户说某句话时按什么流程做 | 不变 |

蓝图只管**顺序和这台仓特有的事实**；具体做法指向已有的 skill，不重复抄。

## 2 怎么用

用户说「帮我搭一下 YOLOE」时：

1. 读 `buildenv/<仓名>.md`
2. **先问用户想装到哪**。用户没指定就用蓝图里「装到」的默认路径
3. 按 §1 把源码拿到位
4. 按 §2 用 `skills/standard-project_merge` 整理
5. 按 §3 装环境（细节在 `skills/tool-build_env`）
6. 按 §4 验证
7. 装好后把**这台机器**的实际路径写进 `workarea/env-<主机>/projects.md`

第 2 步的提问：

```markdown
请确认落盘位置，回复「按此装」：

1. 装到：[蓝图的默认路径 | 你指定的路径]
2. 环境名：[蓝图里的 conda 名 | 你指定的]
```

用户说「都行」「按默认」就直接用蓝图的值，不再追问。

## 3 蓝图清单

状态说明：
- ✅ 有规范化仓库地址，直接 clone
- 📄 用官方 GitHub 源码即可，几乎无改动
- 📦 有改动，需要本地压缩包

| 仓 | 类型 | 源码 | 状态 |
| --- | --- | --- | --- |
| [Qwen3-VL](qwen3-vl.md) | VLM | `github.com/Yulin-CC/Qwen3-VL` | ✅ |
| [YOLO26](yolo26.md) | 检测 | `github.com/Yulin-CC/YOLO26` | ✅ |
| [SAM-CD](samcd.md) | 变化检测 | `github.com/Yulin-CC/SAM-CD` | ✅ |
| [YOLOE](yoloe.md) | 检测 / 开集分割 | `github.com/Yulin-CC/YOLOE` | 📄 |
| [SAM3](sam3.md) | 分割 | `github.com/Yulin-CC/SAM3` | 📄 |
| [SAM3-I](sam3-i.md) | 分割（交互式） | `github.com/debby-0527/SAM3-I` | 📄 |
| [FastSAM](fastsam.md) | 分割 | `github.com/CASIA-IVA-Lab/FastSAM` | 📄 |
| [GroundingDINO](groundingdino.md) | 开放集检测 | `github.com/longzw1997/Open-GroundingDino` | 📄 |
| [LocateAnything](locateanything.md) | 视觉定位 | `huggingface.co/nvidia/LocateAnything-3B` | 📄 |
| [nanochat](nanochat.md) | LLM | `github.com/karpathy/nanochat` | 📄 |
| [vLLM](vllm.md) | 推理框架 | `github.com/vllm-project/vllm` | 📄 |
| [Triton SAM](triton-sam.md) | 分割服务 | 无地址，Docker 自建 | ❓ |

还没写的：`SCM`、`GEOLabeling`、`Agent-DEMO`，这三个需要本地压缩包（📦）。

## 4 和 `workarea/` 的区别

同一个仓在两处都出现，但说的不是一件事：

```markdown
<!-- buildenv/yoloe.md -->
装到：项目根下 0-VLM/16-YOLO-E/YOLOE

<!-- workarea/env-<HOST>/projects.md -->
| 0-VLM/16-YOLO-E/YOLOE | 目录 0-Agent-demo、0-QuickStart、config、data、weights |
```

前者说「装成什么相对位置」，后者说「这台机器上它在哪、里面有什么」。

## 5 怎么加一份蓝图

新建 `buildenv/<仓名>.md`，七节固定顺序：

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
