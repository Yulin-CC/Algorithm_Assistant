# 🗺️ 工作地图

给人改、给助手读的工作环境。连接说明只在 `link.md`。

服务本身（端口、模型名、请求方式、装法）不在本目录，在 `.cursor/server/`。本目录只管**这台机器上东西在哪、怎么起**。

- [x] 2026-11-17 数据根和项目根已确认并展开。主机和 Agent 路径仍待确认。YOLO26 场景文字 OCR 已跑通

- [1 目录](#1-目录)
- [2 怎么改](#2-怎么改)
- [3 确认状态](#3-确认状态)

---

## 1 目录

```
workenv/
├── README.md            # 本文件
├── env-local/           # 本机
│   ├── datasets.md      # 数据根，到数据集
│   ├── projects.md      # 项目根，仓库一层
│   └── docs.md          # 本机工作方式
├── env-<HOST>/   # 当前这台服务器，待确认
│   ├── datasets.md
│   ├── projects.md      # 含 SAM-CD、YOLO26
│   └── docs.md
├── link.md              # 主机、目录对应、启动脚本、权重目录
└── habits.md            # 个人习惯画像：已确认的长期偏好
```

初始化脚本 `.cursor/agents/require.md` 只有一份，不放在这里。

---

## 2 怎么改

- 数据根：改 `datasets.md`，按「到数据集」展开。走到一套数据的目录就停，内容层和产物层不进去。
- 项目根：改 `projects.md`，只到仓库一层，不进源码、权重、`.git`。
- 主机、目录对应、启动脚本、权重目录：改 `link.md`。
- 服务端口、模型名、请求方式、装法：改 `.cursor/server/` 下的文件，不在这里写。
- 程序读的地址：改 `.cursor/server/config/vllm_server.json` 和 `sam.json`。
- 初始化步骤：只改 `.cursor/agents/require.md`，这里不放副本。
- 个人习惯：改 `habits.md`。只由组长改。用户改口标已确认；观察中不当依据。不写某张票的路径和张数。路径仍写 `link.md` 和 `env-*`。
- 当日便签路径：改 `env-local/docs.md`。

---

## 3 确认状态

数据根和项目根已于 2026-11-17 确认。本机和服务器的数据地图已按「到数据集」展开，项目地图到仓库一层。文档路径仍空着。主机和 Agent 路径仍待确认。YOLO26 场景文字 OCR 是按次脚本，2026-11-17 已跑通，记在服务器 `projects.md` 和 `link.md` 第 3 节。
