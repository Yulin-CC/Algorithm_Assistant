"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: YOLO26 预标：sample 叠图；run 写 jsons-det-pre（矩形）或 jsons-seg-pre（多边形）
# @Command: python util/batch_prelabel_json.py sample --dataset /data --weights yolo26s.pt --task detect --n 12
# @Command: python util/batch_prelabel_json.py run --dataset /data --weights yolo26s.pt --task segment
"""

from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

from ultralytics import YOLO

TASKS = ("detect", "segment")
TASK_SLUG = "detseg-yolo26"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
JSON_DIRNAME = {"detect": "jsons-det-pre", "segment": "jsons-seg-pre"}


def parse_classes(raw: str) -> list[str]:
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


def sample_root(dataset: Path) -> Path:
    return dataset / "draft" / TASK_SLUG / "cache" / "sample"


def rel_image_path(json_path: Path, image_path: Path) -> str:
    return os.path.relpath(str(image_path.resolve()), str(json_path.resolve().parent)).replace("\\", "/")


def result_to_shapes(res, task: str, conf_min: float, class_keep: list[str]) -> list[dict]:
    names = {int(k): v for k, v in (res.names or {}).items()}
    keep = {c.lower() for c in class_keep}

    def allowed(cid: int) -> str:
        label = str(names.get(int(cid), str(int(cid))))
        if keep and label.lower() not in keep:
            return ""
        return label

    shapes: list[dict] = []
    if task == "detect":
        if res.boxes is None or len(res.boxes) == 0:
            return shapes
        xyxy = res.boxes.xyxy.cpu().tolist()
        confs = res.boxes.conf.cpu().tolist()
        clss = res.boxes.cls.cpu().tolist()
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
    clss = res.boxes.cls.cpu().tolist() if res.boxes is not None else [0] * len(polys)
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


def save_vis(res, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = res.plot()
    try:
        import cv2
    except ImportError as exc:
        raise SystemExit("需要 opencv-python（ultralytics 依赖）才能写 vis") from exc
    cv2.imwrite(str(out_path), im)


def load_model(weights: str, task: str) -> YOLO:
    path = Path(weights)
    if not path.is_file():
        raise SystemExit(f"权重不存在: {path}")
    if task == "segment" and "seg" not in path.name.lower():
        raise SystemExit(f"--task segment 需要 *-seg.pt 权重，收到: {path.name}")
    return YOLO(str(path))


def run_predict(model: YOLO, sources: list[Path], args) -> None:
    results = model.predict(
        source=[str(p) for p in sources],
        conf=args.conf,
        iou=args.iou,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        stream=True,
        save=False,
        verbose=False,
    )
    for res in results:
        yield res


def cmd_sample(args):
    dataset = Path(args.dataset).resolve()
    images_dir = resolve_images_dir(args.dataset, args.images)
    files = list_images(images_dir)
    if not files:
        raise SystemExit(f"未找到图像: {images_dir}")
    n = min(max(1, int(args.n)), len(files))
    picked = random.Random(int(args.seed)).sample(files, n)
    root = sample_root(dataset)
    vis_dir = root / "vis"
    jsons_dir = root / "jsons"
    vis_dir.mkdir(parents=True, exist_ok=True)
    jsons_dir.mkdir(parents=True, exist_ok=True)

    class_keep = parse_classes(args.classes)
    model = load_model(args.weights, args.task)
    print(
        f"sample n={n}/{len(files)} task={args.task} conf={args.conf} "
        f"device={args.device} vis={vis_dir}"
    )
    adopted = 0
    for i, res in enumerate(run_predict(model, picked, args), 1):
        img_path = Path(res.path)
        h, w = int(res.orig_shape[0]), int(res.orig_shape[1])
        shapes = result_to_shapes(res, args.task, args.conf, class_keep)
        if shapes:
            adopted += 1
        write_labelme(jsons_dir / f"{img_path.stem}.json", img_path, h, w, shapes)
        save_vis(res, vis_dir / f"{img_path.stem}.jpg")
        print(f"  [{i}/{n}] {img_path.name} shapes={len(shapes)}")
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

    out_dir = Path(args.jsons).resolve() if (args.jsons or "").strip() else (dataset / JSON_DIRNAME[args.task])
    out_dir.mkdir(parents=True, exist_ok=True)
    class_keep = parse_classes(args.classes)

    jobs = []
    n_skip = 0
    for path in files:
        jp = out_dir / f"{path.stem}.json"
        if not args.force and json_ok(jp):
            n_skip += 1
            continue
        jobs.append(path)

    print(
        f"run 待标 {len(jobs)}（跳过 {n_skip}）task={args.task} out={out_dir} "
        f"conf={args.conf} device={args.device}"
    )
    if not jobs:
        print("没有待处理图像。")
        return

    model = load_model(args.weights, args.task)
    adopted = empty = n_fail = 0
    for i, res in enumerate(run_predict(model, jobs, args), 1):
        img_path = Path(res.path)
        try:
            h, w = int(res.orig_shape[0]), int(res.orig_shape[1])
            shapes = result_to_shapes(res, args.task, args.conf, class_keep)
            if args.task == "segment" and not shapes and res.masks is None:
                print(f"⚠ {img_path.name}: 无 mask（请确认权重是 *-seg.pt）")
            if shapes:
                adopted += 1
            else:
                empty += 1
            write_labelme(out_dir / f"{img_path.stem}.json", img_path, h, w, shapes)
        except Exception as e:
            n_fail += 1
            print(f"⚠ {img_path.stem}: {e}")
        if i % 200 == 0 or i == len(jobs):
            print(f"  [{i}/{len(jobs)}] adopted={adopted} empty={empty} fail={n_fail}")
    print(f"run 完成 total={len(jobs)} adopted={adopted} empty={empty} fail={n_fail} skip={n_skip} → {out_dir}")


def add_shared(p):
    p.add_argument("--dataset", required=True, help="数据集根目录")
    p.add_argument("--images", default="", help="图像目录；空则 <dataset>/images 或根目录平铺")
    p.add_argument("--weights", required=True)
    p.add_argument("--task", required=True, choices=list(TASKS))
    p.add_argument("--conf", type=float, default=0.35)
    p.add_argument("--iou", type=float, default=0.45)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--device", default="0")
    p.add_argument("--classes", default="", help="只保留这些类名，逗号分隔；空=模型全部类")
    p.add_argument("--force", action="store_true")


def parse_args():
    p = argparse.ArgumentParser(description="YOLO26 预标 sample/run → LabelMe jsons-det-pre | jsons-seg-pre")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="抽样本叠图，给人看 vis")
    add_shared(s)
    s.add_argument("--n", type=int, default=12)
    s.add_argument("--seed", type=int, default=0)
    r = sub.add_parser("run", help="全量写入 jsons-det-pre 或 jsons-seg-pre")
    add_shared(r)
    r.add_argument("--jsons", default="", help="覆盖输出目录；空则 dataset/jsons-det-pre 或 jsons-seg-pre")
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
