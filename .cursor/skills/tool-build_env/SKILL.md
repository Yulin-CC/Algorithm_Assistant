---
name: tool-build-env
description: >-
  Builds a Python env with uv first: probe NVIDIA CUDA, install GPU or CPU
  torch, then extra packages. conda and pip are fallbacks only. Use when a
  task needs venv, CUDA check, torch, uv pip install, 装环境, or when a leaf
  skill says follow tool-build_env. Does not download model weights.
---

# 🔧 Tool-BuildEnv（Python 环境）

  - **概述**: 给任意任务配 Python。默认 **uv 临时/项目 venv** → 看卡 → 装 torch（若需要）→ 再装调用方点名的包。conda / 裸 pip 仅备选。不下载权重、不绑死环境名。
  - **日期**: 2026-09-11

---

## 0 执行前检查

  - **触发**：装环境、uv、venv、CUDA、装 torch、配 Python；其它 Skill 写「按 `tool-build_env`」。
  - **调用方须给出**（未给则问，禁止猜）：
    - `VENV`：venv 路径（临时如 `%TEMP%/<slug>-uv-<pid>` / `$TMPDIR/<slug>-uv-<pid>`，或项目 `.venv`）
    - `NEED_TORCH`：`yes` | `no`
    - `PKGS`：torch 之外的包（可空；可给 `requirements.txt`）
    - 可选：`PYTHON`（如 `3.12`）、是否交付后删 venv
  - **解释器 `$PY`**：Windows `$VENV/Scripts/python.exe`；Linux/macOS `$VENV/bin/python`。之后命令只用 `$PY`。
  - **Windows**：控制台 `PYTHONUTF8=1`。
  - **不做**：不 `uv cache clean`、不 `pip uninstall`、不用系统 Python 硬跑、不扫盘下权重、不擅自改装 CPU torch（有卡失败须停；无卡须用户同意）。

  优先级：**uv → conda → pip**。上一级可用就不要用下一级。

---

## 1 探测 CUDA

    ```bash
    nvidia-smi -L
    nvidia-smi
    ```

  | 结果 | 含义 |
  | --- | --- |
  | 有 GPU 名 | 有卡 → [§2] GPU 路线 |
  | 命令失败 / 无设备 | **无卡** → 若 `NEED_TORCH=yes`，先说明将装 CPU 版（更慢），**用户明确同意后再装**；未确认不得装 |

  `nvidia-smi` 里的 **CUDA Version** 只表示驱动上限，用来选 PyTorch wheel：

  | 驱动 CUDA Version | wheel index 后缀（吃不准用 **cu124**） |
  | --- | --- |
  | 12.8+ | `cu128` |
  | 12.4 / 12.6 | `cu124` |
  | 12.1 | `cu121` |
  | 11.8 | `cu118` |

  记 `CU=cu124`（或上表命中值）。`https://download.pytorch.org/whl/$CU`

---

## 2 主路径：uv

  `uv` 不在 PATH → 告诉用户先装 uv（https://docs.astral.sh/uv/），**不要**立刻改 conda/pip，除非用户说用备选。

### 2.1 建 venv

    ```bash
    uv venv "$VENV"                    # 指定版本：uv venv --python 3.12 "$VENV"
    PY="$VENV/Scripts/python.exe"      # Linux/macOS: $VENV/bin/python
    ```

  已有 venv 且用户要沿用 → 跳过 create，仍用该 `$PY`。

### 2.2 装 torch（仅 `NEED_TORCH=yes`）

  **有卡**（先 GPU torch，再装其它包，避免 PyPI 把 torch 盖成 CPU）：

    ```bash
    uv pip install --python "$PY" torch torchvision --index-url "https://download.pytorch.org/whl/$CU"
    # 调用方要 torchaudio 再追加 torchaudio
    ```

  **无卡（须已确认）**：

    ```bash
    uv pip install --python "$PY" torch torchvision --index-url https://download.pytorch.org/whl/cpu
    ```

  调用方若说「无卡也先别装 torch、只装 $PKGS」→ 跳过本节。

### 2.3 其它包

    ```bash
    uv pip install --python "$PY" <pkg1> <pkg2>
    # 或
    uv pip install --python "$PY" -r requirements.txt
    ```

  - **注意**：有卡时 **torch 已用 CUDA index 装完后再装** `$PKGS`。不要一条命令把 `torch` 和业务包混在默认 PyPI 里装。

### 2.4 验收（必须用 `$PY`）

    ```bash
    "$PY" -c "import sys; print(sys.executable)"
    # NEED_TORCH=yes：
    "$PY" -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"
    # 再 import 调用方点名的包
    ```

  - 有卡但 `cuda` 为 `False` → **停**，核对 `$CU` 与驱动；不要擅自改 CPU 轮，除非用户再次确认。
  - 无卡且已同意 → 后续设备参数用 `cpu`。
  - `$PKGS` import 失败 → **停**，不要用系统 `python` 顶上。

  本任务命令都用 `$PY`。调用方要求交付后清理 → **只删 `$VENV`**。禁止 `uv cache clean`。

---

## 3 备选：conda（仅 uv 不可用，或用户点名已有 conda env）

  先向用户确认 env 名；**禁止**默认 `yulin` / 任何仓库里的旧名。

    ```bash
    conda create -n "<env>" python=3.12 -y    # 沿用已有则跳过
    conda run -n "<env>" python -c "import sys; print(sys.executable)"
    PY="$(conda run -n "<env>" python -c "import sys; print(sys.executable)")"
    ```

  torch（有卡，吃不准 `12.4`）：

    ```bash
    conda install -n "<env>" pytorch torchvision pytorch-cuda=12.4 -c pytorch -c nvidia
    ```

  其它包优先：`conda run -n "<env>" python -m pip install <pkgs>`（仍属备选链里的 pip）。验收同 [§2.4]。

---

## 4 备选：pip（仅 uv、conda 都不可用，且用户同意）

  必须先有**专用** venv（`python -m venv "$VENV"`），禁止往系统/用户 site-packages 装 torch。

    ```bash
    "$PY" -m pip install torch torchvision --index-url "https://download.pytorch.org/whl/$CU"
    "$PY" -m pip install <pkgs>
    ```

  无卡须已确认后改用 `.../whl/cpu`。验收同 [§2.4]。

---

## 5 交给调用方

  回写（口头或调用方台账均可）：`$PY`、有卡与否、`$CU` 或 `cpu`、已装包。之后 CLI 的 `--device`：有卡且验收 `True` → `0`（或多卡由调用方指定）；否则 `cpu`。
