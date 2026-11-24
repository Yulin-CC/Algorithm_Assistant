# GroundingPI

视觉 grounding 服务，给框和点。预标的默认后端，漏检补标也用它定位。

| 项 | 值 |
| --- | --- |
| 端口 | `8082` |
| 对外模型名 | `groundingpi` |
| 配置 | `config/vllm_server.json` |
| 默认 | 否，不是识图后端 |
| GPU | 单卡。4B BF16 约 10GB，一张 4090 或 3090 足够 |
| 后端 | vLLM Transformers backend（`--model-impl transformers`） |

## 0 两个入口

同一套服务在两台机器上各有一份，配置里是两个条目，优先用第一台：

| 配置 id | name | 地址 | 说明 |
| --- | --- | --- | --- |
| `3` | `GroundingPI` | `<HOST>:8082` | 内网 4×3090，默认走这台 |
| `4` | `GroundingPI-106` | `<HOST>:8082` | 公网，那台平时不常开，需要时再起 |

两台权重和 venv 各自独立，同端口不影响。客户端用 `find_service("GroundingPI")` 拿默认那台；要 106 就显式传 `--base_url` 或用 `GroundingPI-106` 这个名字。

## 1 请求必须带两个开关

GroundingPI 把坐标输出成 `<0>`…`<999>` 这种量化 token。请求里如果让服务端丢掉特殊 token，坐标就没了，只会返回一段文字。

```json
{
  "skip_special_tokens": false,
  "spaces_between_special_tokens": false
}
```

用 OpenAI SDK 时这两个字段不在标准参数里，得放进 `extra_body`。仓里 `util/groundingpi_client.py` 已经带上了，直接用它就不会漏。

## 2 参数口径

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `dtype` | `bfloat16` | 官方 recipe |
| `enforce-eager` | 开 | 关 CUDA Graph，稳 |
| `max_model_len` | `16384` | 含图像 + 提示 + 输出 |
| `gpu_memory_utilization` | `0.70` | 官方默认 |
| `max_num_seqs` | `1` | 同时只跑一条请求 |
| 多模态限制 | 图 1 张、视频 0 | — |
| `allowed_local_media_path` | `/home` | 允许读本地图的目录 |

`max_num_seqs=1` 是官方的设定，并发高了会排队，不要误以为服务卡住。

## 3 两种用法

**出框**：提示词里写要检的目标，服务返回量化坐标，客户端换算回像素。仓里 `util/groundingpi_client.py` 的 `parse_boxes()` 做这件事。

**定位单点**：补标链要一个点而不是框时，`locate_prompt()` 把类名转成定位提示。

分割不在这里做。GroundingPI 出框后，多边形交给 [Triton SAM](triton-sam.md)。

## 4 注意

- 不要拿它当识图后端，那是 Qwen 的活。
- 与 Qwen 抢同一张卡时，通常要错开。出框跑完停掉再切 Qwen，这条链在 `skills/agent-data_engine` §2.2 里写死了。
- 权重目录约 9.2GB。换机器前先确认在盘上。

## 5 现状

在哪台机器跑、PID、日志，看 `ledger/runs.md`。装法看 [env_building](../env_building.md)。
