# 📂 本地项目

项目根 `/path/to/project`，2026-11-17 已确认。展开到每个仓库的根：列出直接子目录和散落的压缩包，不进源码，不进 `.git`。

本机和服务器不是同一套目录。服务器见 [env-<HOST>/projects.md](../env-<HOST>/projects.md)。

---

## 1 怎么读

一行是一个仓库或一个还没解开的压缩包。备注里的目录名是仓库根上能看见的，里面没有再打开。

---

## 2 视觉语言 `0-VLM`

| 路径 | 备注 |
| --- | --- |
| `0-VLLM` | 只有 `vllm-main.zip` |
| `10-MMDetection` | `MMDetection-main.zip`、`nltk_data.zip` |
| `12-Qwen3-VL/Qwen3-VL-main` | 根上文件名是 `READNE.md`（少一个 M）。目录有 `.cursor`、`0-QuickStart`、`1-annotation-tool`、`2-vllm`、`Qwen`、`config`、`data`、`z-others` |
| `13-ComfyUI` | 只有 `0-QuickStart.zip` |
| `14-workflow` | 只有 `14-workflow.zip` |
| `15-LocateAbything` | 只有 `LocateAnything.zip`。文件夹名是 Abything |
| `16-YOLOE/yoloe-main` | 根上是一组 pt 权重，没有子目录 |
| `16-YOLOE/runs` | 只有 `YOLOE-demo-260826-v6` |
| `6-GroundingDINO` | `GroundingDINO-main.zip`、`Open-GroundingDINO-main.zip` |
| `7-SAM/SAM3` | `Sam3-ultralytics.zip`、`sam3.zip`、`weights.zip`，另有 `1-data-process` |
| `z-OpenAI/2-vllm` | `0-start_server.sh`、`1-api_test.sh`，目录 `util` |
| `z-OpenAI/webui` | `0-open_webui.sh`，目录 `tools` |

---

## 3 处理工具 `1-PROCESS`

`1-tool` 根上有 18 个脚本（裁框、切图、模糊等）。子目录：`.vscode`、`changedata_merge`、`convert`、`utils`。

---

## 4 检测 `2-YOLO`

| 路径 | 备注 |
| --- | --- |
| `yolo26` | 三个 zip：`weights.zip`、`yolo26-det.zip`、`yolo26-seg.zip`。没有解开，也没有 `0-Agent-demo` |
| `yolov5-6` | `1-val-multi_models.sh`、`2-test-multi_models.sh`、`BoxCrop_cls.py`，目录 `utils` |

---

## 5 任务 `3-TASK`

`1-ChangeDetect` 根上是 `SAMCD.zip`、`SCM.zip`。

| 路径 | 备注 |
| --- | --- |
| `1-ChangeDetect/others` | `BIT_CD.zip`、`DynamicEarth.zip`、`PeftCD.zip`、`SAM2-CD.zip` |
| `1-ChangeDetect/weights` | `FastSAM-x.onnx`、`FastSAM-x.pt`，另有目录 `Levir_CD`，未展开 |

---

## 6 其它 `z-OTHERS`

| 路径 | 备注 |
| --- | --- |
| `Agent-DEMO` | `README.md`、`pyproject.toml`。目录 `data`、`serve`、`src`、`z-other` |
| `Algorithm_Assistant` | 就是这份助手。目录 `.cursor`、`workenv`、`_tmp` |
| `Space_solar` | 空目录 |
