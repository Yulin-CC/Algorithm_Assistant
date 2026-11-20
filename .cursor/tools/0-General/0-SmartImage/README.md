# 🖼️ SmartImage

看图、给已有框和掩膜定档、找漏检再补标。不改已有标注的形状，也不写正式 `labels/`。

- [x] 2026-11-11 1. 写入识图、定档、漏检、补标和分析的用法。
- [x] 2026-11-11 2. 补标前确认落掩膜还是落框。
- [x] 2026-11-11 3. 定档 adjust 走同一条补标链。
- [x] 2026-11-11 4. 变化检测定档并入 `label_grade.py --masks`。
- [x] 2026-11-11 5. 变化检测漏检和差检走 Qwen 报点加 Triton SAM。提示词开工前确认。

---

## 1 能做什么

工作目录是本包根目录。数据集路径由调用方给出。

- **识图**：`util/describe.py` 用 Qwen 写可见内容。有对齐的 `A/`、`B/` 时，左前右后拼在一起描述两期变化。
- **叠图**：`util/overlay.py` 只画框和掩膜，不调用模型。
- **定档**：`util/label_grade.py` 逐个框或掩膜打 `fit`、`adjust`、`wrong`。`wrong` 和 `adjust` 的裁图抄到 `draft/to_check/<类别>/`。变化检测 `--masks` 另抄 `fit`，给人核对误判。
- **变化检测**：`util/label_grade.py --masks` 核对两期变化掩膜。整图在 `util/overlay.py`。漏检和差检先确认提示词，再走 Qwen 报点加 Triton SAM，不走 GroundingPI。
- **漏检**：`util/label_miss.py` 把已标目标盖成灰色，再让 Qwen 报漏检中心并裁图。变化检测加 `--masks`，提示词先确认。
- **补标**：`util/opt_fill.py` 在裁图上定位。先问落掩膜还是落框，再用 Triton SAM 出结果。变化检测的 `pair` 记录只用 Qwen 的点加 Triton SAM。
- **调整**：`util/opt_adjust.py` 把定档 `adjust` 的框中心当成报点，再走补标。变化检测 `--masks` 由 Qwen 对当前块重新报点。
- **汇总**：`util/analysis.py` 汇总误检、不贴合和已经写出的漏检，不再问模型。

```
0-SmartImage/
├── README.md
├── .skill/SKILL.md          # 给调度看的叶说明
└── util/
    ├── describe.py          # 识图
    ├── overlay.py           # 只叠图
    ├── label_grade.py       # 框 / 掩膜定档，--masks 为变化检测
    ├── label_miss.py        # 漏检报点。--masks 为变化检测
    ├── opt_fill.py          # 补标。变化检测 pair 记录只用 Qwen 点加 SAM
    ├── opt_adjust.py        # 调整定档 adjust。--masks 为变化检测
    ├── analysis.py          # 汇总
    └── cd_pair.py           # 两期图对齐
```

空的 `--base_url` / `--model` 读 `model/config/vllm_server.json` 的 default。Windows 控制台加 `PYTHONUTF8=1`。本包不启动 vLLM、GroundingPI 或 SAM。

---

## 2 识图

单张或一个数据集。结果在 `draft/describe/result/jsons/{stem}.json`。两期拼图另存 `draft/describe/model/{stem}.jpg`。

```bash
python util/describe.py --image "<path.jpg>"
python util/describe.py --dataset "<data_root>" --workers 4 --timeout 600
```

`--prompt` 可换描述用语。已有结果默认跳过，`--force` 才重问。`source=failed` 的续跑不要加 `--force`。

---

## 3 定档

已有 LabelMe 框或多边形。`--mode instance` 时一个框或一块掩膜问一次 Qwen。不删框，也不改形状。

档位：

- `fit`：贴合
- `adjust`：目标在，但区域过大、不完整或错位（`issue=oversize|incomplete|shifted`）
- `wrong`：区域内没有该类别，算误检

先判断有没有该类别。`present=true` 却给了 `wrong` 时，改成 `adjust`。`adjust` 不算误检。

```bash
python util/label_grade.py --dataset "<data_root>" --jsons jsons --mode instance --workers 2
```

```
<data_root>/draft/overlay/
├── model/                   # 发给模型的裁图
├── vis/                     # 整图：绿贴合，橙要改，红误检
│   └── summary.md           # 逐条档位和理由
├── result/jsons/            # 判定 json
├── result/summary.json
└── progress.json
```

`wrong` 与 `adjust` 抄到 `draft/to_check/<类别>/`。检测分割抄 `overlay/model/` 裁图，`fit` 不抄。变化检测 `--masks` 的 `to_check` 是全景整图、只画当前这一块连通域（文件名 `图__000.jpg`），同图多块就多张；并另抄 `fit`。叠图和发给 Qwen 的裁图都不写字（无编号、无 T1/T2），只留彩色轮廓。发给 Qwen 的 `overlay/model/` 按连通域裁窗 `CROP_SCALE=4.5`，轮廓是 1 像素细线，不描黑边。

发给模型的矩形内部铺淡色，给人看的仍是亮框。类别名里带颜色时，框和掩膜只描边，内部不铺色。

变化检测用同一个脚本，加上 `--masks`：

```bash
python util/label_grade.py --dataset "<cd_root>" --masks label --workers 2
```

`<cd_root>/A` 与 `B` 同名且已对齐。`--masks` 是 png 变化图。

---

## 4 漏检

从已经打好的预标开始。GroundingPI 或 SAM3 的框都可以。

1. 已有框默认交给 Triton SAM 收成掩膜。本来就是多边形的，直接用。`--sam off` 时矩形不调 SAM，直接把整框涂灰。
2. 掩膜涂成灰色 `(144,144,144)`，盖住已经标过的目标。不描边。
3. Qwen 看这张灰图，只报完全没被灰色罩住的目标中心。落在灰色上的点丢掉。
4. 按这些点裁图。挨在一起的点合成一张。不在图像边上、640 会切到车身时放大，最大 1280。放不下就拆开。贴着图像边缘才允许切到边上。裁图仍带着灰色。

```bash
python util/label_miss.py --dataset "<data_root>" --jsons jsons --labels car --workers 2
```

图上没有任何框时，用 `--labels` 给出要找的类别，否则这张图不会问 Qwen。

变化检测先确认要定位的变化，再跑。已有变化涂灰后左右拼接。点的横坐标落在左图用 T1 原图裁块，落在右图用 T2。灰上的点和中间白缝丢掉。

```bash
python util/label_miss.py --dataset "<cd_root>" --masks label --prompt "新建或拆除的建筑" --workers 2
```

`--prompt` 或 `--prompt-file` 为空就退出。不走 GroundingPI。

```
<data_root>/draft/miss/
├── model/                   # 发给 Qwen 的灰色整图
├── vis/                     # 给人看的灰色整图
├── crop/                    # 漏检裁图
└── result/jsons/            # 点、窗口和裁图路径
```

---

## 5 补标

读 `draft/miss/` 里的裁图。脚本不切服务，定位服务要事先开好。跑之前先问用户落掩膜还是落框。

掩膜用 `--shape mask`。GroundingPI 先定位，Triton SAM 的多边形就是结果。`--locate sam3` 把定位换成 SAM3。`--locate off` 时不再定位，Triton SAM 按 Qwen 的点直接出掩膜。

框用 `--shape box`。默认仍是 GroundingPI 加 Triton SAM，再取掩膜的水平最小外接矩形。只有用户明确说定位模型直出框时，才加 `--refine off`。两段不能同时关。

同一张图里新框彼此重叠过大时只留一个。已经标过的目标靠灰色掩膜挡住。

```bash
python util/opt_fill.py --dataset "<data_root>" --shape mask
python util/opt_fill.py --dataset "<data_root>" --shape box
python util/opt_fill.py --dataset "<data_root>" --shape box --refine off
python util/opt_fill.py --dataset "<data_root>" --shape mask --locate off --refine sam
```

变化检测的漏检记录带 `pair: true`。这时只允许 `--shape mask --locate off --refine sam`，不走 GroundingPI。新掩膜和原变化图重叠过大就丢掉，png 写到 `draft/fill/masks/`。

结果在 `draft/fill/`。不写回原来的 LabelMe，也不覆盖原来的 png。

---

## 6 调整

读 `draft/overlay/` 里 `grade=adjust` 的框。框的中心就是报点，不再问 Qwen。这个目标保持原图，其余已有目标涂成灰色掩膜，然后按漏检的规则裁图。

后面和补标一样：先问落掩膜还是落框。默认 GroundingPI 定位，再 Triton SAM。新形状要罩住原来的中心，才算替换这一条。罩不住的不新加框。

```bash
python util/opt_adjust.py --dataset "<data_root>" --shape mask
python util/opt_adjust.py --dataset "<data_root>" --shape box
```

变化检测先确认要定位的变化。Qwen 在当前这块上重新报一个点，Triton SAM 出掩膜。新掩膜要罩住这个新点。不走 GroundingPI，也不要求罩住旧掩膜中心。

```bash
python util/opt_adjust.py --dataset "<cd_root>" --masks label --prompt "耕地占用"
```

结果在 `draft/adjust/`。变化检测另写 `draft/adjust/masks/`。不写回原来的 LabelMe，也不覆盖原来的 png。

---

## 7 汇总

在已有定档上汇总。有 `draft/miss/` 时计入漏检，没有就写未做。不另开模型。

```bash
python util/analysis.py --dataset "<data_root>" --pred jsons-seg-pre --gt jsons --workers 2
python util/analysis.py --dataset "<cd_root>" --pred "<bcd_map>" --gt label --workers 2
```

`--gt` 可省略。`grade=wrong` 算误检，`grade=adjust` 单列。变化检测测试分析写 `repro/<版本>/analysis/`（`jsons/` + `analysis.json`），Qwen 用 `crop/analysis_crop/`。漏检/补标/调整拢在 `repro/<版本>/draft/` 下的 `miss/`、`fill/`、`adjust/`。目标框仍写数据集根 `draft/`。
