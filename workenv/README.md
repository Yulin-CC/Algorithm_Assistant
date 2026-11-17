# 🗺️ 工作地图

给人改、给助手读的工作环境。连接说明只在 `link.md`。助手真正调用的地址在 `.cursor/model/config/vllm_server.json` 和 `sam.json`。

- [ ] 主机、数据根、项目根、服务 URL 都待确认

- [1 目录](#1-目录)
- [2 怎么改](#2-怎么改)
- [3 确认状态](#3-确认状态)

---

## 1 目录

```
workenv/
├── README.md            # 本文件
├── require.md           # 初始化脚本，与 .cursor/agents/require.md 相同
├── env-local/           # 本机
│   ├── datasets.md      # 数据根，到数据集
│   ├── projects.md      # 项目根，仓库一层
│   └── docs.md          # 本机工作方式
├── API-server.md        # 探活、自搭建说明、付费 API、按次脚本
└── link.md              # 主机、目录对应、启动脚本、URL、按次脚本
```

没填服务器就不建 `env-<主机>/`。

---

## 2 怎么改

- 数据根：改 `datasets.md`，按「到数据集」展开。走到一套数据的目录就停，内容层和产物层不进去。
- 项目根：改 `projects.md`，只到仓库一层，不进源码、权重、`.git`。
- 主机、目录对应、启动脚本、服务 URL：改 `link.md`，然后写回两个 json。
- 服务通不通、自搭建、付费 API、按次脚本：改 `API-server.md`。改了 URL 同样写回两个 json。没有 URL 的按次脚本不写回 json。
- 初始化步骤：`require.md` 与 `.cursor/agents/require.md` 是同一份，改一处时两处一起改。

---

## 3 确认状态

这是一张空白地图。数据根、项目根、文档路径、主机和服务 URL 都待确认。两个 json 还是空的。看过本文件并点头之前，不把确认列改成已确认。
