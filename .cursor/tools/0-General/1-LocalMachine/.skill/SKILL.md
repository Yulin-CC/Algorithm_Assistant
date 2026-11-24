---
name: local-machine
description: >-
  Local-machine agent toolkit: CPU/GPU/disk/process status, path-whitelist
  file browse and mutate, run .py/.sh. Use when the user asks 本机状态, 磁盘, GPU,
  列目录, 读写文件, 压缩解压, 跑脚本. Not for 识图 or conda/uv env setup.
disable-model-invocation: true
---

# 本机工具包（`0-General/1-LocalMachine`）

  - **概述**: 任意 Agent 都能用的本机原语：看机器、管文件、跑脚本。不识图、不配环境、不碰训练集合同。
  - **日期**: 2026-09-11

---

## 0 范围

  - **本包根目录 `PKG_ROOT`**：`.skill/` 的上一级。
  - **调用方式**（任选）：
    1. `python util/<module>.py …`（CLI）
    2. `from system / files / run import Tools`（Open-WebUI 等：每个模块一个 `class Tools`）
    3. 直接调同名函数
  - **路径白名单**：`util/paths.py` 的 `safe_path`。默认根：用户主目录、临时目录、已存在的 `D:/0-data` `D:/1-project` `D:/4-docs` `/path/to/home` `/path/to/home` `/tmp`。再加环境变量 `LOCALMACHINE_ROOTS`（`os.pathsep` 分隔）。这不是进程/容器隔离。
  - **环境**：无第三方依赖，系统 Python 即可。不强制 uv。
  - **不做**：
    - 图像理解 / 误检过滤 → `0-SmartImage`（调度 `agent-smart-image`）
    - 建 venv / 装包 → `skills/tool-build_env`
    - 未经用户同意，移动/删除/改写 `Y:\算法样本库\`

---

## 1 工具索引

  | 模块 | 用途 |
  | --- | --- |
  | `util/system.py` | CPU/内存、GPU、进程、磁盘、uptime |
  | `util/files.py` | ls / 搜索 / 读 / 建改删 / mv cp / zip unzip |
  | `util/run.py` | 白名单内跑 `.py` / `.sh`（超时截断输出） |
  | `util/paths.py` | `safe_path`（各模块共用，不要再复制一份） |

  CLI 示例（工作目录 `PKG_ROOT`）：

    ```bash
    python util/system.py
    python util/system.py gpu
    python util/system.py disk --path "D:/0-data"
    python util/files.py ls "D:/0-data"
    python util/run.py /path/to/script.py --timeout 60
    ```

---

## 2 已拿掉（不要加回）

  | 原文件 | 原因 |
  | --- | --- |
  | `image_viewer.py` | 识图归 `0-SmartImage`，且写死了旧 vLLM |
  | `tool_registry.py` | 写 Open-WebUI sqlite，不是本机能力 |
  | `env_manager.py` | 绑死远端 conda；环境归 `tool-build_env` |
  | `_sandbox.py` | 已并入 `paths.py` |
