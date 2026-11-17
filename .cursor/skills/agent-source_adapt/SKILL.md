---
name: agent-source-adapt
description: >-
  Ports one named upstream feature into a named algorithm repo without
  upgrading the whole package. Use when the user says 源码适配, 改进上游,
  优化源码, OCR, or asks to add an upstream function into a server repo.
  Train, eval, and infer still follow agent-auto_demo and do not edit upstream.
---

# 🔧 源码适配

  - **概述**: 派工写明要切的一个功能时，读上游该功能的源码，只把这一刀补进指定仓库。对不上的调用改适配，不整包升级，不开训。日常三槽仍走 `agent-auto_demo`，禁止改上游。
  - **日期**: 2026-11-17

---

## 1 何时走

  - 用户或组长说源码适配、改进上游、优化源码，或点名把某个上游功能补进某个仓库。
  - 训练、验证、推理不走这里。缺能力又没派「源码适配」时，仍只在槽 `util/` 包装，停回组长。

  - **注意**：派工必须写明仓库绝对路径、上游仓库、上游 commit、功能名、成功标准。缺一项就停，问组长。禁止猜仓库。

---

## 2 怎么切

  **(1)** 先读上游该功能的文件和它的 import。再对本地同名符号的签名。列出三列：照搬、改调用、不带。

  **(2)** 只改这一刀真正碰到的文件：

  - 该功能的新文件
  - 它的导出，例如 `solutions/__init__.py`
  - 本仓库已有的 CLI 注册，例如 `cfg/__init__.py` 里的方案任务名
  - 一条 QuickStart 入口，照本仓库已有 sh 的写法
  - 一份移植说明，放在该仓库已有的 `z-others/` 或 `z_others/`，文件名 `<功能>-port.md`

  **(3)** 移植说明写清：上游 commit、本地原版本、改了哪些文件、哪些调用是适配的、识别或额外依赖的包名。缺的包不自己装，交回组长派运维。

  **(4)** 保留上游许可证文件头。权重放该仓库 `weights/`，不把家目录缓存当交付。

  - **注意**：签名对不上就改这一处调用。不改检测、分割、训练配置，不改三槽，不用新版本整目录替换本地包。

---

## 3 冒烟

  - 代码接上之后只跑一张图，确认功能读得通，原入口仍能 import。
  - 要操作服务器时先 Read `workenv/link.md`。同一台机器已有人占 GPU 时，冒烟用 CPU，或等对方 `done`。改仓库树之前先在组长房间 `say`。
  - 不开训，不占别人的端口。

---

## 4 交回

  - 移植说明路径、改过的文件、依赖包名、冒烟结果或卡在哪一步。
  - 缺环境：包名写入移植说明，交回组长派运维。装好再派回，不执行 `tool-build_env`。
