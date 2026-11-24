# 📂 本地数据

数据根 `/path/to/data`，2026-11-17 已确认。按「到数据集」展开，一共 83 个目录。旧地图里的 `z-cache` 这一层磁盘上没有。服务器同一根是另一套目录，见 [env-<HOST>/datasets.md](../env-<HOST>/datasets.md)。

---

## 1 怎么读

走到一套数据的目录就停。下面这些子目录只记在父级，没有再打开，也不写单个文件名。括号里的数字是该目录里直接躺着的文件数。

| 记号 | 是什么 |
| --- | --- |
| `A` / `B` | 变化检测的两期图像 |
| `images` | 图像目录 |
| `json` / `jsons` / `jsons-*` | 标注 json |
| `label` / `labels` / `labels-*` | 标签图或检测框 |
| `annotations` | 标注原文 |
| `repro` | 某版模型的复现图 |
| `draft` | 过程草稿 |
| `register` | 配准结果 |
| `vis` / `bcd_map` | 可视化或变化图 |

---

## 2 公共数据 `0-Public`

| 路径 | 备注 |
| --- | --- |
| `coco128` | 自带 `yaml` 1。`annotations` 128 xml，`images` 128 jpg，`json` 128，`labels` 128 txt。`draft` 里 json 2、jsonl 1 |
| `grounding/0-COCO2017/ORI` | 自带 txt 3。`annotations` 6 json，`images`、`labels-det`、`labels-seg` 各 2 个 zip |
| `grounding/0-Objects365v1/ORI` | gz 1 |
| `grounding/0-Objects365v1/YOLOE` | zip 5、cache 1、txt 1。其下 `sample`：`images` 6 jpg，`jsons` 6，`jsons-new` 6，两份 vis 各 6 jpg |

---

## 3 变化检测 `1-ChangeDetect`

### 3.1 建筑 `1-BuildingChange`

**反馈** `TestSet/0-Feedback`。有 `repro` 的行表示该次反馈里有复现图，没有往下拆。

| 目录 | 备注 |
| --- | --- |
| `260623` | `A` / `B` 各 13 jpg，`json` 13。有 `repro` |
| `260624` | `A` / `B` 各 154 jpg。下面还有空目录 `half` |
| `260814/网格018_049` | `A` / `B` 各 35 jpg |
| `260814/网格020_051` | `A` / `B` 各 35 jpg |
| `260825/new` | `A` / `B` 各 97 jpeg。有 `repro` |
| `260903` | `A` / `B` 各 52 jpg。有 `repro` |
| `260909` | `A` / `B` 各 25 jpg，`json` 25 |
| `260928` | 压缩包 1 个。解开的 `测试数据—卫星`：`A` / `B` 各 20 png。2026-11-19 这三份只在本机的反馈已补到服务器，文件数分别 220、308、41 |

**测试目录** `TestSet/1-Testdir`。2026-11-19 按服务器整目录对齐，文件名单一致。`label` 是 png。本机原先多出的 `z-dsample`（480）已去掉。

| 目录 | 备注 |
| --- | --- |
| `1-public` | `A` / `B` / `json` / `label` 各 140。`repro` 3764 |
| `2-citytown` | `A` / `B` / `label` 各 900。`json` 982（含 tmp、cache）。`repro` 5676 |
| `3-countryside` | `A` / `B` / `label` 各 3356。`json` 3495（含 tmp、cache）。`repro` 23427。其下 `toclean` 5790 |
| `z-dsample-2611` | `A` / `B` / `label` 各 167。有 `val.txt` |
| `4-ortho` | `A` / `B` / `json` / `label` 各 258，图像和标签是 png。另有 `rename_map.txt`、`test.txt`。2026-11-19 已原样补到服务器，文件数 1034 对得上 |

**训练** `TrainSet`：zip 10。另有解开的 `GEOAI-((ChangeD_dsample))-Selfcollect-2611-(D)(OL)`。

**待清洗** `toclean`。2026-11-19 清过：只留对照 `20261117/sample`（`A` / `B` / `vis` 各 1172）。负样本和八个场景目录已不在。

### 3.2 土地 `2-FieldChange`

| 路径 | 备注 |
| --- | --- |
| `TestSet/1-Testdir/3-countryside` | `A` / `B` / `json` / `label` 各 526。有 `repro`。2026-11-19 与服务器文件名单一致，未重下 |
| `TestSet/1-Testdir/z-dsample-2611` | `A` / `B` / `label` 各 305。2026-11-19 与服务器文件名单一致 |
| `TrainSet` | zip 3。另有解开的 `GEOAI-((ChangeD_frombuilding))-Selfcollect-2611-(D)(OL)`（`A` / `B` 各 1701）和 `GEOAI-((ChangeD_dsample))-Selfcollect-2611-(D)(OL)` |
| `toclean` | 目录旁有 `general.md` 1。2026-11-19 清过：只留对照 `20261117/sample`（`A` / `B` / `vis` 各 1705）。负样本和中科、新切片目录已不在 |

---

## 4 无人机目标 `2-DroneObject`

`BaseSet` 旁有 md 1。`0-script_tools` 有 py 13，`__pycache__` 里 pyc 12。`智慧城市`、`智慧安防`、`智慧水务` 各是 zip 2，没有解开。`Grounding` 是 zip 2。

**智慧交通** `BaseSet/智慧交通/testset` 旁有 md 2。每年都是 `images` 加 `jsons-bbox`。

| 年 | 图像 | 框 json |
| --- | --- | --- |
| `2022` | 4557 jpg | 4557 |
| `2023` | 346 jpg | 346 |
| `2024` | 650 jpg | 650 |
| `2025` | 3727 jpg、2 png | 3729 |
| `2026` | 6529 jpg、379 png | 6908 |

---

## 5 杂项测试 `TestSet`

| 路径 | 备注 |
| --- | --- |
| `CD` | md 1、zip 1。`images` 730 jpg。`draft` 里 md 1 |
| `cache-test/rm-test/260928` | `A` / `B` 各 20 png。`register` 里 json 1。有 `repro` |
| `cache-test/rm-test/261014` | zip 1。`A` / `B` 各 13 jpg。`register` 里 json 1。有 `repro` |
| `cache-test/rm-test/testdir` | `A` / `B` 各 13 jpg。`register` 里 json 1。有 `repro` |
| `fieldtest` | 空目录 |
| `new/test1` | 根上 jpg 9。`jsons-pre` 9。`draft` 里 md 1 |
| `new/test2` | `images` 9 jpg，`json` 8。有 `draft` |
| `new/test3` | `A` / `B` 各 8 jpg，`bcd_map` 8 jpg，`json` 8，`jsons` 8，`label` 8 png。有 `draft` |
| `new/test4` | `images` 4 jpg，`jsons` 4。有 `draft` |
| `new/test5` | `images` 2 jpg，`json` 1 |
