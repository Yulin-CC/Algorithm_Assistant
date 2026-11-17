"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: SAM3 文本提示预标：sample 叠图；run 写 jsons-det-pre（矩形）或 jsons-seg-pre（多边形）
# @Command: python util/batch_prelabel_json.py sample --dataset /data --weights sam3.pt --task detect --prompt person --n 12
# @Command: python util/batch_prelabel_json.py run --dataset /data --weights sam3.pt --task segment --prompt person,boat
"""

from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

from ultralytics.models.sam import SAM3SemanticPredictor

TASKS = ("detect", "segment")
TASK_SLUG = "detseg-sam3"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
JSON_DIRNAME = {"detect": "jsons-det-pre", "segment": "jsons-seg-pre"}


def parse_prompts(raw: str) -> list[str]:
    if not (raw or "").strip():
        return []
    out, seen = [], set()
    for part in raw.replace("，", ",").split(","):
        name = part.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def resolve_images_dir(dataset: str, images: str) -> Path:
    if (images or "").strip():
        path = Path(images)
        if not path.is_dir():
            raise SystemExit(f"图像目录不存在: {path}")
        return path.resolve()
    root = Path(dataset).resolve()
    cand = root / "images"
    if cand.is_dir():
        return cand
    if root.is_dir():
        return root
    raise SystemExit(f"找不到图像目录: {root}")


def list_images(images_dir: Path) -> list[Path]:
    return sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMG_EXTS)


def json_ok(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 8


def resolve_jsons_dir(dataset: Path, jsons: str, task: str) -> Path:
    raw = (jsons or "").strip()
    if not raw:
        return dataset / JSON_DIRNAME[task]
    path = Path(raw)
    if not path.is_absolute():
        path = dataset / path
    return path.resolve()


def default_progress_path(dataset: Path) -> Path:
    return dataset / "draft" / TASK_SLUG / "progress.json"


def write_progress(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_root(dataset: Path) -> Path:
    return dataset / "draft" / TASK_SLUG / "cache" / "sample"


def rel_image_path(json_path: Path, image_path: Path) -> str:
    return os.path.relpath(str(image_path.resolve()), str(json_path.resolve().parent)).replace("\\", "/")


def flatten_results(raw) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            out.extend(flatten_results(item))
        return out
    return [raw]


def _names_map(res, prompts: list[str]) -> dict[int, str]:
    raw = getattr(res, "names", None)
    if isinstance(raw, dict):
        return {int(k): str(v) for k, v in raw.items()}
    if isinstance(raw, (list, tuple)):
        return {i: str(v) for i, v in enumerate(raw)}
    return {i: p for i, p in enumerate(prompts)}


def result_to_shapes(res, task: str, conf_min: float, prompts: list[str]) -> list[dict]:
    names = _names_map(res, prompts)
    keep = {c.lower() for c in prompts}

    def allowed(cid: int) -> str:
        label = str(names.get(int(cid), prompts[int(cid)] if 0 <= int(cid) < len(prompts) else str(int(cid))))
        if keep and label.lower() not in keep:
            return ""
        return label

    shapes: list[dict] = []
    if task == "detect":
        if res.boxes is None or len(res.boxes) == 0:
            return shapes
        xyxy = res.boxes.xyxy.cpu().tolist()
        confs = res.boxes.conf.cpu().tolist()
        clss = res.boxes.cls.cpu().tolist() if res.boxes.cls is not None else [0] * len(xyxy)
        for (x1, y1, x2, y2), conf, cid in zip(xyxy, confs, clss):
            if conf < conf_min:
                continue
            label = allowed(int(cid))
            if not label:
                continue
            shapes.append(
                {
                    "label": label,
                    "points": [[float(x1), float(y1)], [float(x2), float(y2)]],
                    "group_id": None,
                    "description": f"conf={conf:.4f}",
                    "difficult": False,
                    "shape_type": "rectangle",
                    "flags": {},
                }
            )
        return shapes

    if res.masks is None or len(res.masks) == 0:
        return shapes
    polys = res.masks.xy
    confs = res.boxes.conf.cpu().tolist() if res.boxes is not None else [1.0] * len(polys)
    clss = res.boxes.cls.cpu().tolist() if res.boxes is not None and res.boxes.cls is not None else [0] * len(polys)
    for i, poly in enumerate(polys):
        conf = float(confs[i]) if i < len(confs) else 1.0
        if conf < conf_min:
            continue
        cid = int(clss[i]) if i < len(clss) else 0
        label = allowed(cid)
        if not label:
            continue
        pts = [[float(x), float(y)] for x, y in poly.tolist()]
        if len(pts) < 3:
            continue
        shapes.append(
            {
                "label": label,
                "points": pts,
                "group_id": None,
                "description": f"conf={conf:.4f}",
                "difficult": False,
                "shape_type": "polygon",
                "flags": {},
            }
        )
    return shapes


def write_labelme(json_path: Path, image_path: Path, h: int, w: int, shapes: list) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "version": "5.0.1",
        "flags": {},
        "shapes": shapes,
        "imagePath": rel_image_path(json_path, image_path),
        "imageData": None,
        "imageHeight": int(h),
        "imageWidth": int(w),
    }
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def save_vis(results: list, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import cv2
    except ImportError as exc:
        raise SystemExit("需要 opencv-python（ultralytics 依赖）才能写 vis") from exc
    for res in results:
        if res is None:
            continue
        im = res.plot()
        cv2.imwrite(str(out_path), im)
        return


def image_hw(image_path: Path, results: list) -> tuple[int, int]:
    for res in results:
        shape = getattr(res, "orig_shape", None)
        if shape is not None:
            return int(shape[0]), int(shape[1])
    try:
        import cv2
    except ImportError as exc:
        raise SystemExit("无法读取图像尺寸") from exc
    im = cv2.imread(str(image_path))
    if im is None:
        raise SystemExit(f"无法读取图像: {image_path}")
    return int(im.shape[0]), int(im.shape[1])


def load_predictor(args) -> SAM3SemanticPredictor:
    path = Path(args.weights)
    if not path.is_file():
        raise SystemExit(f"权重不存在: {path}")
    device = str(args.device)
    half = bool(args.half) and device.lower() != "cpu"
    overrides = dict(
        conf=args.conf,
        iou=args.iou,
        task="segment",
        mode="predict",
        model=str(path),
        device=device,
        half=half,
        save=False,
        verbose=False,
    )
    return SAM3SemanticPredictor(overrides=overrides)


def predict_one(predictor: SAM3SemanticPredictor, image_path: Path, prompts: list[str]) -> list:
    predictor.set_image(str(image_path))
    return flatten_results(predictor(text=prompts))


def maybe_empty_cache(device: str) -> None:
    if str(device).lower() == "cpu":
        return
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def cmd_sample(args):
    dataset = Path(args.dataset).resolve()
    images_dir = resolve_images_dir(args.dataset, args.images)
    files = list_images(images_dir)
    if not files:
        raise SystemExit(f"未找到图像: {images_dir}")
    prompts = parse_prompts(args.prompt)
    if not prompts:
        raise SystemExit("SAM3 必须提供 --prompt（逗号分隔文本概念）")
    n = min(max(1, int(args.n)), len(files))
    picked = random.Random(int(args.seed)).sample(files, n)
    root = sample_root(dataset)
    vis_dir = root / "vis"
    jsons_dir = root / "jsons"
    vis_dir.mkdir(parents=True, exist_ok=True)
    jsons_dir.mkdir(parents=True, exist_ok=True)

    predictor = load_predictor(args)
    print(
        f"sample n={n}/{len(files)} task={args.task} prompt={prompts} conf={args.conf} "
        f"device={args.device} vis={vis_dir}"
    )
    adopted = 0
    for i, img_path in enumerate(picked, 1):
        results = predict_one(predictor, img_path, prompts)
        h, w = image_hw(img_path, results)
        shapes = []
        for res in results:
            shapes.extend(result_to_shapes(res, args.task, args.conf, prompts))
        if shapes:
            adopted += 1
        write_labelme(jsons_dir / f"{img_path.stem}.json", img_path, h, w, shapes)
        save_vis(results, vis_dir / f"{img_path.stem}.jpg")
        print(f"  [{i}/{n}] {img_path.name} shapes={len(shapes)}")
        maybe_empty_cache(args.device)
    print(f"sample 完成 adopted={adopted}/{n} → 叠图 {vis_dir}")
    print("看 vis 后回复「直接全量」再 run。")


def cmd_run(args):
    dataset = Path(args.dataset).resolve()
    images_dir = resolve_images_dir(args.dataset, args.images)
    files = list_images(images_dir)
    if args.limit:
        files = files[: int(args.limit)]
    if not files:
        raise SystemExit(f"未找到图像: {images_dir}")
    prompts = parse_prompts(args.prompt)
    if not prompts:
        raise SystemExit("SAM3 必须提供 --prompt（逗号分隔文本概念）")

    out_dir = resolve_jsons_dir(dataset, args.jsons, args.task)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_raw = (getattr(args, "progress", "") or "").strip()
    progress_path = Path(progress_raw).resolve() if progress_raw else default_progress_path(dataset)

    jobs = []
    n_skip = 0
    for path in files:
        jp = out_dir / f"{path.stem}.json"
        if not args.force and json_ok(jp):
            n_skip += 1
            continue
        jobs.append(path)

    def dump_progress(**extra):
        payload = {
            "cmd": "run",
            "dataset": str(dataset),
            "out": str(out_dir),
            "images": len(files),
            "pending": len(jobs),
            "skip": n_skip,
            "task": args.task,
            "prompt": prompts,
            "device": str(args.device),
        }
        payload.update(extra)
        write_progress(progress_path, payload)

    print(
        f"run 待标 {len(jobs)}（跳过 {n_skip}）task={args.task} prompt={prompts} out={out_dir} "
        f"conf={args.conf} device={args.device} progress={progress_path}"
    )
    dump_progress(status="start", done=0, adopted=0, empty=0, fail=0)
    if not jobs:
        dump_progress(status="done", done=0, adopted=0, empty=0, fail=0)
        print("没有待处理图像。")
        return

    predictor = load_predictor(args)
    adopted = empty = n_fail = 0
    for i, img_path in enumerate(jobs, 1):
        try:
            results = predict_one(predictor, img_path, prompts)
            h, w = image_hw(img_path, results)
            shapes = []
            for res in results:
                shapes.extend(result_to_shapes(res, args.task, args.conf, prompts))
            if args.task == "segment" and not shapes and not any(getattr(r, "masks", None) is not None for r in results):
                print(f"⚠ {img_path.name}: 无 mask")
            if shapes:
                adopted += 1
            else:
                empty += 1
            write_labelme(out_dir / f"{img_path.stem}.json", img_path, h, w, shapes)
        except Exception as e:
            n_fail += 1
            print(f"⚠ {img_path.stem}: {e}")
        if i % 50 == 0:
            maybe_empty_cache(args.device)
        if i % 20 == 0 or i == len(jobs):
            dump_progress(status="running", done=i, adopted=adopted, empty=empty, fail=n_fail)
        if i % 200 == 0 or i == len(jobs):
            print(f"  [{i}/{len(jobs)}] adopted={adopted} empty={empty} fail={n_fail}")
    dump_progress(status="done", done=len(jobs), adopted=adopted, empty=empty, fail=n_fail)
    print(f"run 完成 total={len(jobs)} adopted={adopted} empty={empty} fail={n_fail} skip={n_skip} → {out_dir}")


def add_shared(p):
    p.add_argument("--dataset", required=True, help="数据集根目录")
    p.add_argument("--images", default="", help="图像目录；空则 <dataset>/images 或根目录平铺")
    p.add_argument("--weights", required=True)
    p.add_argument("--task", required=True, choices=list(TASKS))
    p.add_argument("--prompt", required=True, help="文本概念，逗号分隔")
    p.add_argument("--conf", type=float, default=0.45)
    p.add_argument("--iou", type=float, default=0.45)
    p.add_argument("--device", default="0")
    p.add_argument("--half", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--force", action="store_true")


def parse_args():
    p = argparse.ArgumentParser(description="SAM3 预标 sample/run → LabelMe jsons-det-pre | jsons-seg-pre")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="抽样本叠图，给人看 vis")
    add_shared(s)
    s.add_argument("--n", type=int, default=12)
    s.add_argument("--seed", type=int, default=0)
    r = sub.add_parser("run", help="全量写入 jsons-det-pre 或 jsons-seg-pre")
    add_shared(r)
    r.add_argument("--jsons", default="", help="覆盖输出目录；相对 dataset（如 jsons-det-pre-car）；空则 jsons-det-pre / jsons-seg-pre")
    r.add_argument("--progress", default="", help="进度 JSON；空则 dataset/draft/detseg-sam3/progress.json")
    r.add_argument("--limit", type=int, default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.cmd == "sample":
        cmd_sample(args)
    elif args.cmd == "run":
        cmd_run(args)
    else:
        raise SystemExit("未知子命令")
