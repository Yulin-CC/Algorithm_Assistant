"""
# @Author: Yullin
# @Date: 2026-08-31
# @Description: 无界面 Triton SAM 客户端（标准 ViT-H；框/点提示 → mask）
"""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from typing import List, Optional, Sequence, Tuple

SAM_RETRIES = 3
SAM_RETRY_SLEEP = 0.8


def _transient_rpc(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    keys = (
        "unavailable", "connection reset", "statuscode.unavailable",
        "deadline exceeded", "timeout", "timed out", "reset by peer",
        "broken pipe", "failed to connect", "wsasend", "wsarecv", "10054",
    )
    return any(k in text for k in keys)

import cv2
import numpy as np

MODEL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAM_CONFIG_PATH = os.path.join(MODEL_ROOT, "config", "sam.json")


def sam_config_path() -> str:
    return SAM_CONFIG_PATH


def load_sam_config() -> dict:
    path = SAM_CONFIG_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_default_sam() -> dict:
    cfg = load_sam_config()
    size = cfg.get("input_size") or [684, 1024]
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        input_size = (int(size[0]), int(size[1]))
    else:
        input_size = (684, 1024)
    return {
        "name": str(cfg.get("name") or "Triton SAM").strip(),
        "url": str(cfg.get("url") or "<HOST>:6621").strip(),
        "protocol": str(cfg.get("protocol") or "grpc").strip().lower(),
        "encoder": str(cfg.get("encoder") or "sam_vit_h_encoder").strip(),
        "decoder": str(cfg.get("decoder") or "sam_vit_h_decoder").strip(),
        "input_size": input_size,
    }


class TritonSAM:
    """标准 SAM：每图 encode 一次；框和/或点 decode 成 mask。"""

    def __init__(self, url="", encoder="", decoder="", input_size=None, timeout=60):
        try:
            import tritonclient.grpc as grpcclient
        except ImportError as e:
            raise RuntimeError(
                "缺少 tritonclient。按 tool-build_env 安装: uv pip install --python \"$PY\" 'tritonclient[grpc]'"
            ) from e

        cfg = get_default_sam()
        self.url = (url or "").strip() or cfg["url"]
        self.encoder = (encoder or "").strip() or cfg["encoder"]
        self.decoder = (decoder or "").strip() or cfg["decoder"]
        self.input_size = tuple(input_size or cfg["input_size"])
        self.timeout = timeout
        self._grpc = grpcclient
        self.client = grpcclient.InferenceServerClient(url=self.url, verbose=False)
        self._cache = {}

    def _reconnect(self):
        self.client = self._grpc.InferenceServerClient(url=self.url, verbose=False)

    def _infer(self, model_name, inputs, outputs):
        last = None
        for attempt in range(SAM_RETRIES):
            try:
                return self.client.infer(
                    model_name=model_name, inputs=inputs, outputs=outputs,
                )
            except Exception as e:
                last = e
                if not _transient_rpc(e) or attempt >= SAM_RETRIES - 1:
                    raise
                time.sleep(SAM_RETRY_SLEEP * (attempt + 1))
                try:
                    self._reconnect()
                except Exception:
                    pass
        raise last

    def health_check(self) -> bool:
        try:
            if not self.client.is_server_live():
                return False
            return bool(self.client.is_model_ready(self.encoder)) and bool(
                self.client.is_model_ready(self.decoder)
            )
        except Exception:
            return False

    def encode(self, rgb: np.ndarray) -> dict:
        if rgb is None or rgb.ndim != 3:
            raise ValueError("encode 需要 HxWx3 RGB 图像")
        original_size = rgb.shape[:2]
        target_h, target_w = self.input_size
        scale = min(target_w / rgb.shape[1], target_h / rgb.shape[0])
        transform = np.array(
            [[scale, 0, 0], [0, scale, 0], [0, 0, 1]], dtype=np.float32,
        )
        warped = cv2.warpAffine(
            rgb, transform[:2], (target_w, target_h), flags=cv2.INTER_LINEAR,
        ).astype(np.float32)

        InferInput = self._grpc.InferInput
        InferRequestedOutput = self._grpc.InferRequestedOutput
        inputs = [InferInput("input_image", warped.shape, "FP32")]
        inputs[0].set_data_from_numpy(warped)
        outputs = [InferRequestedOutput("image_embeddings")]
        result = self._infer(self.encoder, inputs, outputs)
        embedding = result.as_numpy("image_embeddings")
        return {
            "image_embedding": embedding,
            "original_size": original_size,
            "transform_matrix": transform,
        }

    def encode_file(self, path: str) -> dict:
        rgb = _read_rgb(path)
        return self.encode(rgb)

    def decode_prompt(self, encoded: dict, box=None, extra_points=None) -> Optional[np.ndarray]:
        """框（xyxy 像素）和/或点（前景 1 / 背景 0）→ 原图尺寸 float mask。"""
        pts, labs, has_box = [], [], False
        if box is not None and len(box) >= 4:
            x1, y1, x2, y2 = [float(v) for v in box[:4]]
            if x2 < x1:
                x1, x2 = x2, x1
            if y2 < y1:
                y1, y2 = y2, y1
            pts.append([x1, y1])
            pts.append([x2, y2])
            labs.extend([2.0, 3.0])
            has_box = True
        for item in extra_points or []:
            if isinstance(item, (list, tuple)) and len(item) == 2 and not isinstance(item[0], (int, float)):
                xy, lab = item
            else:
                xy, lab = item, 1
            pts.append([float(xy[0]), float(xy[1])])
            labs.append(float(lab))
        if not pts:
            return None
        points = np.array(pts, dtype=np.float32)
        labels = np.array(labs, dtype=np.float32)
        if has_box:
            onnx_coord = points[None, :, :]
            onnx_label = labels[None, :].astype(np.float32)
        else:
            onnx_coord = np.concatenate(
                [points, np.array([[0.0, 0.0]], dtype=np.float32)], axis=0,
            )[None, :, :]
            onnx_label = np.concatenate(
                [labels, np.array([-1], dtype=np.float32)], axis=0,
            )[None, :].astype(np.float32)

        transform = encoded["transform_matrix"]
        ones = np.ones((1, onnx_coord.shape[1], 1), dtype=np.float32)
        onnx_coord = np.concatenate([onnx_coord, ones], axis=2)
        onnx_coord = np.matmul(onnx_coord, transform.T)[:, :, :2].astype(np.float32)

        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask = np.zeros(1, dtype=np.float32)
        orig_im_size = np.array(self.input_size, dtype=np.float32)
        embedding = encoded["image_embedding"]

        InferInput = self._grpc.InferInput
        InferRequestedOutput = self._grpc.InferRequestedOutput
        inputs = [
            InferInput("image_embeddings", embedding.shape, "FP32"),
            InferInput("point_coords", onnx_coord.shape, "FP32"),
            InferInput("point_labels", onnx_label.shape, "FP32"),
            InferInput("mask_input", mask_input.shape, "FP32"),
            InferInput("has_mask_input", has_mask.shape, "FP32"),
            InferInput("orig_im_size", orig_im_size.shape, "FP32"),
        ]
        inputs[0].set_data_from_numpy(embedding.astype(np.float32))
        inputs[1].set_data_from_numpy(onnx_coord)
        inputs[2].set_data_from_numpy(onnx_label)
        inputs[3].set_data_from_numpy(mask_input)
        inputs[4].set_data_from_numpy(has_mask)
        inputs[5].set_data_from_numpy(orig_im_size)
        outputs = [
            InferRequestedOutput("masks"),
            InferRequestedOutput("iou_predictions"),
            InferRequestedOutput("low_res_masks"),
        ]
        result = self._infer(self.decoder, inputs, outputs)
        masks = result.as_numpy("masks")
        if masks is None:
            return None
        inv = np.linalg.inv(transform)
        oh, ow = encoded["original_size"]
        restored = _transform_masks(masks, (oh, ow), inv)
        if restored.ndim == 4:
            mask = restored[0, 0]
        elif restored.ndim == 3:
            mask = restored[0]
        else:
            mask = restored
        return mask

    def decode_point(self, encoded: dict, xy: Sequence[float]) -> Optional[np.ndarray]:
        return self.decode_prompt(encoded, extra_points=[(xy, 1)])

    def decode_box(self, encoded: dict, xyxy: Sequence[float]) -> Optional[np.ndarray]:
        return self.decode_prompt(encoded, box=xyxy)

    def segment_points(self, rgb: np.ndarray, points: Sequence[Sequence[float]]) -> List[Optional[np.ndarray]]:
        if not points:
            return []
        encoded = self.encode(rgb)
        return [self.decode_point(encoded, pt) for pt in points]


def _read_rgb(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"无法读取图像: {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _transform_masks(masks: np.ndarray, original_size, transform_matrix) -> np.ndarray:
    out = []
    for batch in range(masks.shape[0]):
        batch_masks = []
        for mask_id in range(masks.shape[1]):
            mask = masks[batch, mask_id]
            warped = cv2.warpAffine(
                mask,
                transform_matrix[:2],
                (original_size[1], original_size[0]),
                flags=cv2.INTER_LINEAR,
            )
            batch_masks.append(warped)
        out.append(batch_masks)
    return np.array(out)


def mask_to_polygon(
    mask: np.ndarray,
    min_area: float = 32.0,
    max_points: int = 0,
    simplify: float = 0.5,
) -> Optional[List[List[float]]]:
    """mask → 多边形。max_points<=0 表示不截断点数。"""
    if mask is None:
        return None
    binary = (mask > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < min_area:
        return None
    pts = contour.reshape(-1, 2)
    if len(pts) < 3:
        return None
    coords = _simplify_pts(pts, max_points=max_points, simplify=simplify)
    if len(coords) < 3:
        return None
    return coords


def polygon_to_bbox_pts(poly: Sequence[Sequence[float]]) -> List[List[float]]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    return [
        [xmin, ymin],
        [xmax, ymin],
        [xmax, ymax],
        [xmin, ymax],
    ]


def _simplify_pts(pts: np.ndarray, max_points: int = 0, simplify: float = 0.5) -> List[List[float]]:
    try:
        from shapely.geometry import Polygon
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            raise ValueError("empty")
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        if simplify and simplify > 0:
            poly = poly.simplify(float(simplify), preserve_topology=True)
        coords = list(poly.exterior.coords)
        if len(coords) >= 2 and coords[0] == coords[-1]:
            coords = coords[:-1]
        if len(coords) >= 3:
            if max_points and len(coords) > max_points:
                step = len(coords) / float(max_points)
                coords = [coords[int(i * step)] for i in range(max_points)]
            return [[float(x), float(y)] for x, y in coords]
    except Exception:
        pass
    n = len(pts)
    if max_points and n > max(8, max_points):
        idx = np.linspace(0, n - 1, max(8, max_points), dtype=int)
        pts = pts[idx]
    return [[float(x), float(y)] for x, y in pts]


def make_client(url="", **kwargs) -> TritonSAM:
    client = TritonSAM(url=url, **kwargs)
    if not client.health_check():
        raise RuntimeError(f"SAM 不可用: {client.url} ({client.encoder}/{client.decoder})")
    return client
