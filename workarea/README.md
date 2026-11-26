# 🗺️ 工作地图

给人改、给助手读的工作环境。连接说明只在 `link.md`。

本目录只管**这台机器上东西在哪、怎么起**。另两处不在这里：

| 要知道 | 去哪 |
| --- | --- |
| 一个算法仓或一种服务怎么从零搭起来（源码、环境、权重、验证） | 仓库根 `buildenv/` |
| 服务端口、模型名、请求方式 | `.cursor/server/` |

所以换新机器时，`workarea/` 重写，`buildenv/` 和 `server/` 不动。

- [x] 2026-11-17 数据根和项目根已确认并展开。主机和 Agent 路径仍待确认。YOLO26 场景文字 OCR 已跑通

- [1 目录](#1-目录)
- [2 怎么改](#2-怎么改)
- [3 确认状态](#3-确认状态)

---

## 1 目录

```
workarea/
├── README.md            # 本文件
├── env-local/           # 本机（Windows）
│   ├── datasets.md      # 数据根，到数据集
│   ├── projects.md      # 项目根，仓库一层
│   └── docs.md          # 本机工作方式
├── env-<HOST>/   # 公网服务器（ubuntu@<HOST>）
│   ├── datasets.md
│   ├── projects.md      # 含 SAM-CD、YOLO26
│   └── docs.md
├── env-<HOST>/     # 内网服务器（caiyulin@<HOST>，4×3090）
│   ├── datasets.md      # 车辆负样本挖掘的 7 个场景
│   ├── projects.md      # SAM-CD、YOLO26、Qwen/GroundingPI
│   └── docs.md          # uv venv、长活怎么跑、不要动的东西
├── link.md              # 主机、目录对应、启动脚本、权重目录
└── habits.md            # 个人习惯画像：已确认的长期偏好
```

初始化脚本 `.cursor/agents/require.md` 只有一份，不放在这里。

---

## 2 怎么改

- 数据根：改 `datasets.md`，按「到数据集」展开。走到一套数据的目录就停，内容层和产物层不进去。
- 项目根：改 `projects.md`，只到仓库一层，不进源码、权重、`.git`。
- 主机、目录对应、启动脚本、权重目录：改 `link.md`。
- 仓或服务怎么从零搭：改仓库根 `buildenv/<仓名>.md`，不写这里。vLLM 系与 Triton 系各一份。
- 服务端口、模型名、请求方式：改 `.cursor/server/` 下的文件，不在这里写。
- 程序读的地址：改 `.cursor/server/config/vllm_server.json` 和 `sam.json`。
- 初始化步骤：只改 `.cursor/agents/require.md`，这里不放副本。
- 个人习惯：改 `habits.md`。只由组长改。用户改口标已确认；观察中不当依据。不写某张票的路径和张数。路径仍写 `link.md` 和 `env-*`。
- 当日便签路径：改 `env-local/docs.md`。

---

## 3 确认状态

数据根和项目根已于 2026-11-17 确认。本机和服务器的数据地图已按「到数据集」展开，项目地图到仓库一层。文档路径仍空着。主机和 Agent 路径仍待确认。YOLO26 场景文字 OCR 是按次脚本，2026-11-17 已跑通，记在服务器 `projects.md` 和 `link.md` 第 3 节。

`<HOST>`（内网 4×3090）2026-11-25 补进地图：数据根与项目根按一层展开，见 `env-<HOST>/`。这台是车辆负样本挖掘的主战场，`link.md` §1 早已列为已确认，但 `workarea/` 一直没建目录，这次补齐。
