# Triton SAM

标准 SAM ViT-H（量化 ONNX）的 Triton 远程服务。给分割补边、变化检测报点加 SAM、框转多边形用。

| 项 | 值 |
| --- | --- |
| 协议 | gRPC |
| 端口 | `6621`（容器内 `8001`）；HTTP 健康检查 `8000`；metrics `8002` |
| 模型名 | `sam_vit_h_encoder` / `sam_vit_h_decoder` |
| 配置 | `config/sam.json` |
| GPU | 单卡。ViT-H 量化仍占几个 GB |
| 输入尺寸 | `684×1024`（H×W），固定 |
| 容器名 | `sam-triton` |

## 1 客户端怎么填

`config/sam.json` 的 `url` 填 `host:6621`，**不要加 `http://` 或 `grpc://`**。`encoder` / `decoder` 两个名字不要改，它们和 Triton 仓库目录名绑定。

```json
{
  "name": "Triton SAM ViT-H",
  "url": "<HOST>:9001",
  "protocol": "grpc",
  "encoder": "sam_vit_h_encoder",
  "decoder": "sam_vit_h_decoder",
  "input_size": [684, 1024]
}
```

`input_size` 是编码器的固定输入，不是原图尺寸。客户端要自己缩放并把变换矩阵记下来，解码后再映射回原图坐标系。仓里 `util/sam_client.py` 处理了这套。

## 2 两段式推理

不是一次调用出结果，分两步：

1. **encoder** 吃整图，输出 `image_embeddings`。每张图只跑一次，结果可以缓存复用。
2. **decoder** 吃 embedding + 提示（框或点），输出 mask。

同一个 embedding 可以反复喂不同的框，这是它比单次推理快的地方。

## 3 健康检查

```bash
curl -s http://<host>:8000/v2/health/ready
docker logs -f sam-triton          # 出现 READY 即成功
```

日志里 READY 之后，gRPC 才真正能收请求。只看端口开着不算就绪。

## 4 注意

- 客户端填 `host:6621` 时不要带协议前缀，带了会解析失败。
- ViT-H 量化仍占几个 GB 显存，不要和占满同一张卡的训练硬叠。
- 改 GPU 或端口要先改启动脚本顶部，再 `docker rm -f sam-triton` 重新起。直接 `restart` 不会应用新参数。
- HQ 版（`sam_hq_pv_*`，端口 `9002`）暂不提供。
- 有多个地址时（长期服务在一台、容器在另一台），以 `config/sam.json` 的 `url` 为准。台账里出现过的每个地址都是实际存在过的，别把旧的当默认。

## 5 现状

在哪台机器跑、容器状态、日志，看 `ledger/runs.md`。镜像与拉取、ONNX 权重下载看 [buildenv/0-VLM/triton-sam.md](../../../buildenv/0-VLM/triton-sam.md) §3。
