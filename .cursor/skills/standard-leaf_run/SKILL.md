---
name: standard-leaf-run
description: >-
  Shared gates for tools/ leaves: paths, uv env, probe, write-back, sample-before-run.
  Read this before a leaf SKILL.md. Leaves only add layout, PKGS, CLI, and exceptions.
---

# 📜 叶执行闸门（共用）

  - **概述**: `tools/` 叶子的默认纪律。调度和叶 skill **先 Read 本文**；叶文件只写本叶落盘、确认项、命令、环境包名。
  - **日期**: 2026-09-11

---

## 1 默认（不要在叶里再抄一遍）

  - **`PKG_ROOT`**：该叶 `.skill/` 的上一级。命令的工作目录就是它。
  - **路径**：`data_root` / 单张图必须用户给（或客户票 `require/`），**禁止猜盘**。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。Windows `PYTHONUTF8=1`。命令只用 `$PY`。不执行 `uv cache clean` / `pip uninstall`。临时 venv 交付后或失败退出前删除。
  - **Qwen 分类 / 图像理解 / 误检过滤**（classify / describe / overlay）：vLLM 联通由**调度**用 `server/util/probe.py`（加 `--skip-sam`）。空 `--base_url` / `--model` 读 default。预标过滤写 `draft/overlay/`（`model/` 给模型，`vis/` 给人，`result/` 是 json）。`wrong` 和 `adjust` 的裁图另抄到 `draft/to_check/<类别>/`，不改原标注。变化检测 `--masks` 另抄 `fit`。结果分析：变化检测写 `repro/<版本>/analysis/`，目标框写 `draft/analysis/`。GroundingPI 后默认链式 overlay（切服务不问）在 `agent-data_engine` §2.2。定档 `adjust` 由 `opt_adjust.py` 按补标链重出，只写 `draft/adjust/`。
  - **GroundingPI 检测叶**（detseg-groundingpi）：调度用 `probe.py --service GroundingPI`（detect 加 `--skip-sam`；segment 测 SAM）。空 `--base_url` / `--model` 读 name=`GroundingPI`，**不是** default Qwen。客户端 `groundingpi_client.py`（`skip_special_tokens=false`）。不下权重。
  - **写回**：预标 / 分类 / 识图只写叶声明的 `draft/`、`jsons-det-pre`、`jsons-seg-pre` 等，**不写**正式 `jsons/`、`labels/`。整理叶（organize）按规范可以写 `labels/`、`train.txt` 等。
  - **先小后全**：预标 / 分类未看 sample（或 vis）不得 `run`。organize 不走 sample。已有非空结果默认跳过；覆盖须用户说 force / `--force`。失败占位续跑不加 `--force`。
  - **台账**：有客户票 → 该票 `todo.md`；无票的数据引擎任务 → `<data_root>/draft/todo-dataengine.md`。数据集 `draft/` 不另写第二份 todo。
  - **禁止**：未经同意动 `Y:\算法样本库\`。不落地过时的 `4-Agent-label/`。

  叶 skill 用一行引用即可：`闸门：skills/standard-leaf_run`。只写**例外**（例如 organize 允许写 labels）。

---

## 2 环境怎么填（叶只保留这一小段）

  叶 skill 只给出：`NEED_TORCH`、`PKGS`、venv slug、验收 import。安装步骤不要复制 `tool-build_env` 全文。

---

## 3 DetSeg 落盘（三后端同形）

  相对 `data_root`。`<slug>` = `yolo26` | `sam3` | `groundingpi`。

    ```text
    images/
    draft/detseg-<slug>/cache/sample/
      vis/…/{stem}.jpg
      jsons/{stem}.json
    jsons-det-pre/{stem}.json        # run + detect：rectangle
    jsons-seg-pre/{stem}.json    # run + segment：polygon
    ```

  sample 不写全量目录。`imagePath` 由脚本按 json 位置相对到原图。detect → `jsons-det-pre/`；segment → `jsons-seg-pre/`。
