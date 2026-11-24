# Qwen VLM

OpenAI 兼容的视觉语言服务，给识图、分类、定档后的描述用。

| 项 | 值 |
| --- | --- |
| 端口 | `8081` |
| 对外模型名 | `qwen3.8-27b`（默认）、`qwen3.6-35b-a3b` |
| 配置 | `config/vllm_server.json` |
| 默认 | `qwen3.8-27b` 那条 `default: true` |
| GPU | 双卡，`0,1` |

**两条模型共用 8081，同一时间只能起一个。**换模型等于停一个再起一个，端口和地址都不变，所以 `config/` 里的 `base_url` 不用改，变的是 `/v1/models` 返回的 model id。

## 1 请求

```bash
curl -s http://<host>:8081/v1/models
```

```bash
curl -s http://<host>:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":[
        {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,<...>"}},
        {"type":"text","text":"请描述一下图像"}]}]}'
```

本地图片也可以走 `--allowed-local-media-path` 允许的目录传路径，但默认客户端用 base64，不依赖服务端磁盘。

## 2 参数口径

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `max_model_len` | `131072` | KV 较大，双卡 4090 实际建议 16k–32k |
| `gpu_memory_utilization` | `0.85` | dense 全量激活，可按需下调 |
| 图像像素 | `max_pixels 200704` / `min_pixels 784` | 调大更清晰但更吃显存 |
| attention backend | `FLASHINFER` | — |
| 多模态编码器 | `TORCH_SDPA` | — |
| 思考解析 | `reasoning-parser qwen3` | 带 thinking 的请求才有意义 |

纯文本任务可以起成 `language_model_only`，省显存，代价是不能识图。

## 3 注意

- 两个模型都占满双卡时，同机的 GroundingPI 和 Triton SAM 会没有余量。三者需要错开。
- `qwen3.6-35b-a3b` 的权重目录在 106 上不存在，那条现在起不来。换机器前先确认权重在盘上。
- FP8 版在另一台机器上（`config/vllm_server.json` 里 `4004` 那条），不是分类和识图的默认，也没有本仓的搭建说明。

## 4 现状

在哪台机器跑、PID、日志，看 `ledger/runs.md`。装法看 [env_building](../env_building.md)。
