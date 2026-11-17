---
name: image-detseg-groundingpi
description: >-
  GroundingPI boxes; detect writes jsons-det-pre rectangles; segment then Triton
  SAM polygons to jsons-seg-pre. sample writes vis. Does not download weights.
  Use when agent-dataengine dispatched backend=groundingpi, or the user says
  GroundingPI 检测, GroundingPI 分割, Qwen 检测（已改走本叶）.
disable-model-invocation: true
---

# 检测/分割 · GroundingPI（`2-Image-DetSeg/groundingpi`）

  - **概述**: GroundingPI 给框。`detect` 直出矩形；`segment` 再走标准 Triton SAM。`sample` 写叠图给人看；`run` 按任务写盘。不写回正式 `jsons/` / `labels/`。不下模型。流程：`confirm → sample（看 vis）→ run`。
  - **日期**: 2026-11-06

---

## 0 执行前检查

  - **触发**：GroundingPI 检测/分割、给框预标；旧说法「Qwen 检测」也走本叶；由 `agent-dataengine` 指定 `backend=groundingpi`。
  - **本包根目录 `PKG_ROOT`**：`.skill/` 的上一级。
  - **数据根目录 `data_root`**：必须由用户给出；须有 `images/`（或根下直接放图）。
  - **落盘**（相对 `data_root`）：

    ```text
    <data_root>/
      images/
      draft/detseg-groundingpi/cache/sample/
        vis/<类>/{stem}.jpg     # sample 叠图（给人看）
        jsons/{stem}.json       # sample LabelMe；imagePath 相对该 json
      jsons-det-pre/{stem}.json     # run + detect：rectangle 两点
      jsons-seg-pre/{stem}.json # run + segment：polygon
    ```

    不写正式 `jsons/`、`labels/`。sample 不写全量目录。`imagePath` 由脚本按 json 位置相对到原图。
  - **服务**：GroundingPI 在 `model/config/vllm_server.json`（name=`GroundingPI`，**不是** default Qwen）。SAM `model/config/sam.json`（仅 segment）。联通检查由 **总调度** 先做。本叶不再探测、**不下任何权重**。请求必须 `skip_special_tokens=false`。
  - **共享客户端**：`REPO/model/util/groundingpi_client.py`（及 segment 时 `sam_client.py`）。
  - **任务**：`detect`（矩形，不调 SAM）或 `segment`（多边形）。门控仅 segment 且非 detect，且只给旧流程。图像理解与误检过滤走 `0-General/0-SmartImage`（`agent-smart-image`），不在本叶改框。
    - **环境**：Read `skills/tool-build_env/SKILL.md`。本叶：`NEED_TORCH=no`，临时 venv slug=`detseg-groundingpi`，`PKGS=tqdm opencv-python shapely numpy pillow "tritonclient[grpc]"`。Windows 控制台 `PYTHONUTF8=1`。
  - **不做**：不用 HQ-SAM、不训练、不跑金字塔/基类互补、不下载权重。不执行 `uv cache clean` / `pip uninstall`。不要把本叶拷进客户票。

---

### 0.1 环境初始化（未通过不得跑）

  按 `skills/tool-build_env/SKILL.md`：uv 建 `$GpiDetVenv`（**不装 torch**），再：

    ```bash
    uv pip install --python "$PY" tqdm opencv-python shapely numpy pillow "tritonclient[grpc]"
    ```

  验收用 `$PY`：

    ```bash
    "$PY" -c "import cv2, shapely, tritonclient.grpc, tqdm, PIL; print('ok')"
    ```

  失败 → 停。本任务命令都用 `$PY`。交付后或失败退出前只删 `$GpiDetVenv`。

---

## 1 向用户确认（未确认不得 sample）

    ```markdown
    请确认后回复「按此开跑」（改括号即可）：

    1. 数据集目录：[绝对路径；含 images/]
    2. 任务：[detect | segment]
    3. 类别名：[name1, name2, ...]（给模型，可中文）
    4. 英文标签（写入 jsons，必须英文）：
       - name1：[LampPost]
       - name2：[Person]
    5. 每类 hint（Agent 已起草；请改括号，尽量不要留空）：
       - name1：[一句形态/尺度/易混物]
       - name2：[…]
    6. 写出：随 task（detect→jsons-det-pre | segment→jsons-seg-pre）
    7. 试跑样本数：[12]
    8. 门控 / 思考：[关（默认）]
    ```

  英文标签未起草或仍是中文、hint 括号仍空 → **不得 sample**。类名已是英文则第 4 项填相同字符串。

---

## 2 执行

  工作目录：`PKG_ROOT`。解释器 = [§0.1] 的 `$PY`。空 `--base_url` / `--model` 读 `vllm_server.json` 的 **GroundingPI** 条目。

### 2.1 sample 叠图检阅

    ```bash
    "$PY" util/detect_segment.py sample --dataset "<data_root>" --task detect --classes "类A,类B" --en-label "类A=ClassA" --en-label "类B=ClassB" --hint "类A=……" --hint "类B=……" --n 12 --seed 0 --workers 2
    ```

  完成后把 **`draft/detseg-groundingpi/cache/sample/vis/`** 给用户看。细彩框 + 框顶色条 = 终态（detect 同类同色）；segment 半透明彩膜；黄虚线仅未出掩膜的提示框；红叉 = 未出掩膜。

  - **注意**：**此处必须停止**。用户说「直接全量」→ §2.2。vis 不像样 → 说明后停，不要硬 run。

### 2.2 全量写盘

    ```bash
    "$PY" util/detect_segment.py run --dataset "<data_root>" --task detect --classes "类A,类B" --workers 2 --timeout 600
    "$PY" util/detect_segment.py run --dataset "<data_root>" --task segment --classes "类A,类B" --workers 2 --timeout 600
    ```

  可带确认清单里的 `--en-label` / `--hint`。detect → `jsons-det-pre/`；segment → `jsons-seg-pre/`。已有非空 json 默认跳过；覆盖须 `--force`。

---

## 3 工具索引

  | 分类 | 工具路径 | 用途 |
  | --- | --- | --- |
  | 入口 | `util/detect_segment.py` | `sample` / `run` |
  | 共享 | `model/util/groundingpi_client.py` | GroundingPI 请求与特殊 token 解析 |
  | 服务 | `model/config/vllm_server.json` | name=`GroundingPI` |
  | 服务 | `model/config/sam.json` | 标准 SAM gRPC（仅 segment） |
  | 探测 | `model/util/probe.py --service GroundingPI` | 总调度用；detect 加 `--skip-sam` |

---
