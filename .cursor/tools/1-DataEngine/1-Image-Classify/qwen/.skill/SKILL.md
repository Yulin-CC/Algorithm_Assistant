---
name: image-classify
description: >-
  Qwen vision image classification. sample copies into class folders for
  review; run writes draft/classify/result/<class>/. Does not download
  weights or write labels/. Use when agent-dataengine dispatched
  capability=classify, or the user says 图像分类, 二分类, 多分类, 跑 classify.
disable-model-invocation: true
---

# 图像分类 · Qwen（`1-Image-Classify/qwen`）

  - **概述**: Qwen 视觉二/多分类。`sample` 抽图给人看；校验后再 knowledge / run。不写回正式 `labels/`。不下模型。流程：`confirm → sample（看文件夹）→ review → knowledge → run → hold`。
  - **日期**: 2026-09-11

---

## 0 执行前检查

  - **触发**：分类、图像分类、二分类、多分类、跑 classify；由 `agent-dataengine` 指定 `capability=classify`。
  - **本包根目录 `PKG_ROOT`**：`.skill/` 的上一级。
  - **数据根目录 `data_root`**：必须由用户给出；须有 `images/`（或根下直接放图）。
  - **落盘**（相对 `data_root`）：

    ```text
    <data_root>/
      images/
      draft/classify/
        cache/
          sample/<类>/{stem}.*     # sample 给人看（可把图挪到正确类文件夹）
          jsons/{stem}.json
          knowledge.json
          config.json
        result/
          <类>/{stem}.*            # 全量 high
          _待审/{stem}.*           # confidence=low，须人挪类
    ```

    不写正式 `labels/`，不把 `result/` 挪到数据集根，不删 `draft/`。
  - **服务**：vLLM `model/config/vllm_server.json`。联通检查由 **总调度** 先做（`--skip-sam`）。本叶不再探测、**不下任何权重**。
  - **共享客户端**：`REPO/model/util/`（`vllm_client.py` / `common.py`）。
  - **环境**：Read `skills/tool-build_env/SKILL.md`。本叶：`NEED_TORCH=no`，临时 venv slug=`classify-qwen`，`PKGS=tqdm`。Windows 控制台 `PYTHONUTF8=1`。
  - **不做**：不写 `labels/`、不调 SAM、不训练、不下载 Qwen 权重。不执行 `uv cache clean` / `pip uninstall`。

---

### 0.1 环境初始化（未通过不得跑）

  按 `skills/tool-build_env/SKILL.md`：uv 建 `$ClsVenv`（**不装 torch**），再：

    ```bash
    uv pip install --python "$PY" tqdm
    ```

  验收用 `$PY`：

    ```bash
    "$PY" -c "import tqdm; print('ok')"
    ```

  失败 → 停。本任务命令都用 `$PY`。交付后或失败退出前只删 `$ClsVenv`。

---

## 1 向用户确认（未确认不得 sample）

    ```markdown
    请确认后回复「按此开跑」（改括号即可）：

    1. 数据集目录：[绝对路径；含 images/ 或根下直接放图]
    2. 类别数：[K，≥2]
    3. 类别名：[name1, name2, ...]（必须恰好 K 个）
    4. 试跑样本数：[12]
    5. workers：[4]
    ```

  路径或类别未给 → 只问缺的项。类别数与类别名不一致则停下重问。

---

## 2 执行

  工作目录：`PKG_ROOT`。解释器 = [§0.1] 的 `$PY`。空 `--base_url` / `--model` 读 `vllm_server.json` 的 default。

### 2.1 sample 试分类

    ```bash
    "$PY" util/classify.py sample --dataset "<data_root>" --classes "类A,类B" --n 12 --seed 0 --workers 4
    ```

  完成后把 **`draft/classify/cache/sample/`** 发给用户。分错的图可挪到正确类别文件夹。

  - **注意**：**此处必须停止**。禁止直接 knowledge / run。

### 2.2 用户校验

    ```bash
    "$PY" util/classify.py review --dataset "<data_root>" --accept-all
    # 若改了若干张：再加 --fix "stemA=类B,stemC=类A"
    ```

### 2.3 提炼临时知识

    ```bash
    "$PY" util/classify.py knowledge --dataset "<data_root>"
    ```

  Read `draft/classify/cache/knowledge.json` 给用户过目。用户说「按此全量」后再 2.4。

### 2.4 全量分类

    ```bash
    "$PY" util/classify.py run --dataset "<data_root>" --workers 4 --timeout 600
    ```

  已校验 sample 链到 `result/<类>/`，不再问模型。`confidence=low` 进 `result/_待审/`。`_待审` 非空 → **停**，把文件夹给用户。

### 2.5 不确定桶

    ```bash
    "$PY" util/classify.py hold --dataset "<data_root>"
    # 剩下按模型收下：加 --accept-all
    ```

  桶空后自动 deliver。不挪到数据集根、不删 `draft/`。

---

## 3 工具索引

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 入口 | `util/classify.py` | sample / review / knowledge / run / hold / deliver |
  | 共享 | `model/util/` | vLLM / 扫图 |
  | 服务 | `model/config/vllm_server.json` | vLLM；`default: true` |
  | 探测 | `model/util/probe.py --skip-sam` | 总调度用；本叶不重复 |

---
