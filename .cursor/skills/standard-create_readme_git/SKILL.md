---
name: standard-create-readme-git
description: >-
  Writes a git-repo README with a centered title, one subtitle, and a
  three-column count table. Use only when the user is preparing a README for
  git clone, GitHub, or GitLab. Everyday docs stay on standard-create-readme.
  要做 git、给克隆用户看的项目首页时才用。
---

# 🧭 Git 项目首页

  - **概述**: 只在做 git 时用。给别人 `git clone` 之后打开的仓库根 `README.md` 写页头。仓内产线文档、叶子说明、客户票仍用 `standard-create-readme`。
  - **日期**: 2026-11-17

## 1 什么时候用

  - 用户要提交 git、做 GitHub / GitLab 项目首页，或点名本技能。
  - 平时新建或改写 README，走 `standard-create-readme`，不要套这版居中页头。
  - 工作副本和干净快照若各有一份 README，三列表按各自事实写，不要互相抄。

## 2 页头

  - 整段放进 `<div align="center">`，标题居中。
  - 一级标题是一个 emoji 加项目名。下面只留一句加粗副标题，不再加第二句、第三句口号。
  - 三列表：表头是 emoji 加名称，下一行才是数字或短状态。保持 3 列。数字加粗。
  - 表下最多两行补充，用 ` · ` 分开。目录收成居中的一行链接，用 ` · ` 连接，不要竖排长目录。
  - 不要写 `[!TIP]`、`[!IMPORTANT]`、`[!NOTE]`。当前预览会把它们原样打出来。要紧的话写成普通句子。
  - 不编徽章、星标、许可证、CI。没有的数字不要写进三列表。

  ```markdown
  <div align="center">

  # 🧭 项目名

  **一句话说明这个仓库是做什么的**

  | 🎯 技能 | 🔌 数据引擎 | 🎫 客户票 |
  | :---: | :---: | :---: |
  | **19** | **5** 已接线 | 开票后才有 |

  调度 6 · 规范 8 · 工具 5

  [🚀 怎么开始](#start) · [📁 仓库](#layout)

  </div>
  ```

  - 列名和数字按这个仓库改。上面只是版式。

## 3 正文

  - 页头结束后恢复左对齐。主章节用 `##`，带一个 emoji 和数字编号，节与节之间用 `---`。
  - 目录链接要稳时，标题前加 `<a id="短名"></a>`，链接写 `#短名`。
  - 目录树不加语言标记，`#` 注释对齐到同一列。命令和代码块要写语言，如 `bash`、`python`。
  - 怎么开始写具体的第一句该说什么、确认什么，不写空泛介绍。
