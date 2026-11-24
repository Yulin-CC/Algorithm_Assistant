# 🛰️ 服务

本目录放三样东西：**服务本身**（端口、模型名、请求方式）、**环境搭建**（怎么装起来）、**客户端**（脚本读的配置与调用代码）。

启动脚本不在这里。哪台机器用哪个脚本起、权重放哪个目录，写在工作地图的 `workarea/link.md`。

- [1 服务](#1-服务)
- [2 边界](#2-边界)
- [3 探活](#3-探活)
- [4 目录](#4-目录)

---

## 1 服务

| 服务 | 端口 | 对外模型名 | 客户端配置 | 影响哪一块 |
| --- | --- | --- | --- | --- |
| [Qwen VLM](services/qwen.md) | 8081 | `qwen3.8-27b`（默认）、`qwen3.6-35b-a3b` | `config/vllm_server.json` | 识图、分类、定档后的描述 |
| [GroundingPI](services/groundingpi.md) | 8082 | `groundingpi` | `config/vllm_server.json` | 预标默认后端、补标定位 |
| [Triton SAM](services/triton-sam.md) | 6621 (gRPC) | `sam_vit_h_encoder` / `sam_vit_h_decoder` | `config/sam.json` | 分割补边、变化检测报点加 SAM |

默认识图模型是 Qwen3.8-27B，即 `vllm_server.json` 里 `default: true` 那条。GroundingPI 不是默认。

GroundingPI 有两个入口：`GroundingPI`（`<HOST>:8082`，优先）和 `GroundingPI-106`（`<HOST>:8082`，备用）。同名服务不同主机，详见 [services/groundingpi.md](services/groundingpi.md) §0。

## 2 边界

一句话：**启动归地图，服务本身归这里。**

| 位置 | 写什么 | 不写什么 |
| --- | --- | --- |
| `workarea/link.md` | 主机、目录对应、每个服务的启动脚本绝对路径与权重目录 | 端口、URL、模型名 |
| `services/*.md` | 端口、模型名、GPU 需求、请求注意点、当前状态 | 启动脚本、权重路径、安装步骤 |
| `env_building.md` | 装法、依赖版本、镜像、已知坑 | 端口、在跑状态、启动脚本 |
| `config/*.json` | 程序读的地址，唯一权威 | — |
| `ledger/runs.md` | 谁何时起了哪个服务、PID、日志、何时停 | 搭建方法、端口定义 |

同一套服务换一台机器：`services/` 一个字都不用改，只改 `link.md` 里的脚本路径；如果端口也变了，改 `config/` 里的地址。

## 3 探活

在 `.cursor` 下跑：

```bash
py -3 server/util/probe.py              # vLLM 全表 + SAM
py -3 server/util/probe.py --skip-sam   # 只探 vLLM
py -3 server/util/probe.py --service GroundingPI --skip-sam
```

`PASS` 表示默认服务与 SAM 都通。目标不通时会列出其它可达条目，供你决定要不要换。

## 4 目录

```
server/
├── README.md          # 本文件
├── services/          # 一服务一篇：端口、模型名、注意点、现状
├── env_building.md    # 装法、依赖、镜像、已知坑
├── config/            # vllm_server.json、sam.json（地址唯一权威）
├── util/              # 客户端与探活
│   ├── probe.py
│   ├── servers_io.py
│   ├── vllm_client.py
│   ├── groundingpi_client.py
│   ├── sam_client.py
│   └── common.py
└── ledger/
    └── runs.md        # 起停台账
```

## 5 加一个服务

1. `services/<name>.md` 写清端口、模型名、GPU 需求、请求注意点。
2. `config/vllm_server.json` 加一条（vLLM 系）或改 `sam.json`（Triton 系）。
3. `workarea/link.md` 记这台机器的启动脚本与权重目录。
4. `env_building.md` 补装法。
5. 本文件第 1 节加一行。
