# vLLM

上游推理框架源码，服务和训练都用。

| 项 | 值 |
| --- | --- |
| 来源 | `github.com/vllm-project/vllm` |
| 装到 | 项目根下 `0-VLM/0-vllm/vllm` |
| 环境 | 见 `.cursor/server/env_building.md` §1 |
| 依赖 skill | `tool-build_env` |

**这个是上游源码，不是独立算法仓**，没有 `0-Agent-demo`、没有 QuickStart。装法和版本约束统一写在 `.cursor/server/env_building.md`，这里只讲拉源码这一步。

## 1 拉源码

```bash
cd <项目根>/0-VLM/0-vllm
git clone https://github.com/vllm-project/vllm.git
```

## 2 整理项目

不做。这是上游源码，保持原样，不套团队目录规范。

## 3 装环境

见 `.cursor/server/env_building.md` §1.2（从源码装 vLLM）。

**版本要挑**，不是最新就好：

| 版本 | 能不能用 |
| --- | --- |
| 0.22+ | PyPI 上是 CUDA 13 构建，驱动只到 CUDA 12 的机器装不了 |
| 0.21.0 | 元数据写 CUDA 12，实际仍链 `libcudart.so.13` |
| 0.20.x | 要 glibc 2.35，glibc 2.31 的机器不行 |
| **0.19.1** | manylinux_2_31，只链 `libcudart.so.12`，可用 |

## 4 验证

```bash
python -c "import vllm; print(vllm.__version__)"
ldd $(python -c "import vllm,os;print(os.path.dirname(vllm.__file__))")/_C*.so | grep libcudart
```

第二句必须只出现 `libcudart.so.12`。出现 `.so.13` 就是装错了。

## 5 已知问题

- **版本选型**：见 §3 的表。这是最容易踩的坑。
- **不要当算法仓整理**：它是上游源码，套 `standard-project_merge` 会把结构搞乱。

## 6 后续

| 要做的事 | 走哪个 |
| --- | --- |
| 起 vLLM 服务（Qwen / GroundingPI） | `.cursor/server/env_building.md` §1 |
| 服务端口与模型名 | `.cursor/server/services/` |

## 7 参考

- 上游：https://github.com/vllm-project/vllm
- 版本坑：`.cursor/server/env_building.md` §3.1
