"""
# @Author: 算法组
# @Date: 2026-05-14
# @Description: 双时相配准：遍历 ROOT_DIR 下所有含 A/B 的子文件夹，分别做金字塔 ECC 配准。
# @Command: python util/cd_register.py
# @Compat: Windows 含中文路径用 fromfile + imdecode 读写，避免 cv2.imread 失败。
# @Config: ROOT_DIR / LOG_JSON / CROP_BORDER / CROP_INSIDE_B_MARGIN / MOTION / SCALES /
#   USE_ORB_INIT / MIN_ECC_CC / MIN_NCC（见文件顶部接口配置）
# @Output: B_registered/ + warp_meta/（CROP_BORDER=True 时额外生成 A_cropped/ + B_cropped/）
"""

import json
import os

import cv2
import numpy as np
from tqdm import tqdm

#==============================#
# 接口配置
#==============================#
# /path/to/data\1-ChangeDetect\cache\数据中心文件-中科青云
ROOT_DIR = r"/path/to/data\1-ChangeDetect\toclean\testset-01"   # 遍历其下所有含 A/B 的子文件夹
Mutil_DIR = False                                                     # True: 遍历 DATA_DIR 下所有子文件夹；False: 只处理 DATA_DIR 自身

LOG_JSON = None                                                    # 可选，如 os.path.join(ROOT_DIR, "register_log.jsonl")
CROP_BORDER = True                                                 # True=裁剪镜像边，保留纯重叠区域；False=保留原尺寸
# 双边线性采样建议 ≥0.5；略大更稳，裁剪会略收紧
CROP_INSIDE_B_MARGIN = 1.0

MOTION = "AFFINE"  # EUCLIDEAN 或 AFFINE
SCALES = "0.125,0.25,0.5,1.0"
USE_ORB_INIT = True
MIN_ECC_CC = None  # 可选：低于则回退原 B
MIN_NCC = None
#==============================#


def imread_unicode(path: str | os.PathLike) -> np.ndarray | None:
    """Windows 下含中文路径时 cv2.imread 易失败，改用 fromfile + imdecode。"""
    path = os.fspath(path)
    try:
        buf = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def imwrite_unicode(path: str | os.PathLike, img: np.ndarray) -> bool:
    path = os.fspath(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    elif ext == ".png":
        ok, enc = cv2.imencode(".png", img)
    else:
        ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok or enc is None:
        return False
    try:
        enc.tofile(path)
    except OSError:
        return False
    return True


def _motion_type(name: str) -> int:
    n = name.upper().replace("-", "_")
    if n in ("EUCLIDEAN", "Euclidean"):
        return cv2.MOTION_EUCLIDEAN
    if n in ("AFFINE", "Affine"):
        return cv2.MOTION_AFFINE
    raise ValueError(f"未知 motion: {name}，使用 EUCLIDEAN 或 AFFINE")


def _affine_b_to_a_inverse_warp(M_fwd: np.ndarray) -> np.ndarray:
    """
    M_fwd: 2x3，满足 p_a = M_fwd @ hom(p_b)（齐次下标为 [x,y,1]）。
    findTransformECC + warpAffine(WARP_INVERSE_MAP) 需要 W，使 dst 像素 (x_a,y_a) 处采样自 B 的 W@[x_a,y_a,1]。
    """
    R = M_fwd[:, :2].astype(np.float64)
    t = M_fwd[:, 2:3].astype(np.float64)
    det = np.linalg.det(R)
    if abs(det) < 1e-9:
        return None
    Rinv = np.linalg.inv(R)
    W = np.zeros((2, 3), dtype=np.float32)
    W[:, :2] = Rinv.astype(np.float32)
    W[:, 2] = (-Rinv @ t).flatten().astype(np.float32)
    return W


def orb_initial_inverse_warp(
    gray_a: np.ndarray,
    gray_b: np.ndarray,
    max_features: int = 4000,
    ransac_thresh: float = 3.0,
) -> np.ndarray | None:
    """ORB 匹配估计 B->A 的仿射，转为 ECC 所需的 inverse warp 2x3；失败返回 None。"""
    orb = cv2.ORB_create(nfeatures=max_features)
    kpa, da = orb.detectAndCompute(gray_a, None)
    kpb, db = orb.detectAndCompute(gray_b, None)
    if da is None or db is None or len(kpa) < 4 or len(kpb) < 4:
        return None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(db, da)
    if len(matches) < 12:
        return None
    matches = sorted(matches, key=lambda m: m.distance)[:500]
    src_pts = np.float32([kpb[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kpa[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    M_fwd, inliers = cv2.estimateAffinePartial2D(
        src_pts,
        dst_pts,
        method=cv2.RANSAC,
        ransacReprojThreshold=ransac_thresh,
        confidence=0.99,
    )
    if M_fwd is None:
        return None
    inl = inliers.ravel() if inliers is not None else None
    if inl is None or inl.sum() < 6:
        return None
    return _affine_b_to_a_inverse_warp(M_fwd)


def _upscale_inverse_warp(W: np.ndarray, scale_ratio: float) -> np.ndarray:
    """相邻金字塔层尺度比 scale_ratio = scales[i] / scales[i-1] > 1：平移分量按比例放大，线性部分不变。"""
    out = W.astype(np.float64).copy()
    out[0, 2] *= scale_ratio
    out[1, 2] *= scale_ratio
    return out.astype(np.float32)


def pyramid_find_transform_ecc(
    template: np.ndarray,
    image: np.ndarray,
    motion: int,
    criteria: tuple,
    warp_init: np.ndarray | None,
    scales: list[float],
    gauss_ksize: int = 0,
) -> tuple[np.ndarray, float]:
    """
    由粗到细在缩放后的 template/image 上跑 findTransformECC，返回 (warp_matrix, last_correlation)。
    warp_matrix 与全分辨率 template 像素坐标一致（最后一级 scale=1）。
    """
    h, w = template.shape[:2]
    W = warp_init
    if W is None:
        W = np.eye(2, 3, dtype=np.float32)

    last_cc = -1.0
    for si, s in enumerate(scales):
        tw = max(32, int(round(w * s)))
        th = max(32, int(round(h * s)))
        t_s = cv2.resize(template, (tw, th), interpolation=cv2.INTER_AREA)
        i_s = cv2.resize(image, (tw, th), interpolation=cv2.INTER_AREA)
        if gauss_ksize and gauss_ksize >= 3:
            t_s = cv2.GaussianBlur(t_s, (gauss_ksize, gauss_ksize), 0)
            i_s = cv2.GaussianBlur(i_s, (gauss_ksize, gauss_ksize), 0)

        if si > 0:
            ratio = scales[si] / scales[si - 1]
            W = _upscale_inverse_warp(W, ratio)
        try:
            cc, W = cv2.findTransformECC(
                t_s,
                i_s,
                W,
                motion,
                criteria,
                inputMask=None,
                gaussFiltSize=5,
            )
            last_cc = float(cc)
        except cv2.error:
            raise

    return W, last_cc


def ncc_after_warp(
    gray_a: np.ndarray,
    gray_b: np.ndarray,
    warp_matrix: np.ndarray,
    h: int,
    w: int,
) -> float:
    """对齐后两幅灰度图的归一化互相关系数（全图），用于质量门控。"""
    b_w = cv2.warpAffine(
        gray_b,
        warp_matrix,
        (w, h),
        flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REFLECT,
    )
    a = gray_a.astype(np.float64)
    b = b_w.astype(np.float64)
    a = (a - a.mean()) / (a.std() + 1e-8)
    b = (b - b.mean()) / (b.std() + 1e-8)
    return float((a * b).mean())


def _compute_forward_warp(W: np.ndarray) -> np.ndarray:
    """从 inverse warp W(输出→源) 恢复 forward warp M_fwd(源→输出)，2x3。"""
    R = W[:, :2].astype(np.float64)
    t = W[:, 2:3].astype(np.float64)
    R_inv = np.linalg.inv(R)
    M = np.zeros((2, 3), dtype=np.float64)
    M[:, :2] = R_inv
    M[:, 2] = (-R_inv @ t).flatten()
    return M.astype(np.float32)


def _loose_footprint_aabb_in_a(
    W: np.ndarray, h_a: int, w_a: int, h_b: int, w_b: int
) -> tuple[int, int, int, int] | None:
    """B 四角经 B→A 变换后在 A 画布上的轴对齐外接框（可能大于真实四边形，四角易有 BORDER_REFLECT 伪影）。"""
    M_fwd = _compute_forward_warp(W)
    corners_b = np.array(
        [
            [0, 0, 1],
            [w_b - 1, 0, 1],
            [w_b - 1, h_b - 1, 1],
            [0, h_b - 1, 1],
        ],
        dtype=np.float32,
    ).T
    pts_a = (M_fwd @ corners_b).T

    x_min = max(0, int(np.floor(pts_a[:, 0].min())))
    x_max = min(w_a - 1, int(np.ceil(pts_a[:, 0].max())))
    y_min = max(0, int(np.floor(pts_a[:, 1].min())))
    y_max = min(h_a - 1, int(np.ceil(pts_a[:, 1].max())))

    if x_max <= x_min or y_max <= y_min:
        return None
    return (x_min, y_min, x_max - x_min + 1, y_max - y_min + 1)


def _crop_rect_samples_only_inside_b(
    W: np.ndarray,
    x: int,
    y: int,
    cw: int,
    ch: int,
    w_b: int,
    h_b: int,
    margin: float,
) -> bool:
    """
    裁剪矩形 (x,y,cw,ch) 在 A 上时，warpAffine(WARP_INVERSE_MAP) 四角采样是否均落在 B 的有效幅面内。
    仿射下 x_b、y_b 对 (x_a,y_a) 线性，矩形上极值在顶点，故四角成立则整块矩形无越界采样、无反射填边。
    """
    if cw < 1 or ch < 1:
        return False
    Wd = W.astype(np.float64)
    corners = np.array(
        [
            [x, y, 1.0],
            [x + cw - 1, y, 1.0],
            [x + cw - 1, y + ch - 1, 1.0],
            [x, y + ch - 1, 1.0],
        ],
        dtype=np.float64,
    )
    pb = (Wd @ corners.T).T
    lo = float(margin)
    x_hi = float(w_b) - 1.0 - margin
    y_hi = float(h_b) - 1.0 - margin
    if x_hi < lo or y_hi < lo:
        return False
    return bool(
        np.all(pb[:, 0] >= lo)
        and np.all(pb[:, 0] <= x_hi)
        and np.all(pb[:, 1] >= lo)
        and np.all(pb[:, 1] <= y_hi)
    )


def _shrink_aabb_symmetric_until_inside_b(
    loose: tuple[int, int, int, int],
    W: np.ndarray,
    w_a: int,
    h_a: int,
    w_b: int,
    h_b: int,
    margin: float,
) -> tuple[int, int, int, int] | None:
    """在松外接框内对称内收，直至四角逆映射均落在 B 内；无解放回 None。"""
    x0, y0, w0, h0 = loose
    max_k = min(w0, h0) // 2
    for k in range(0, max_k + 1):
        cw, ch = w0 - 2 * k, h0 - 2 * k
        if cw < 1 or ch < 1:
            break
        x, y = x0 + k, y0 + k
        if x < 0 or y < 0 or x + cw > w_a or y + ch > h_a:
            continue
        if _crop_rect_samples_only_inside_b(W, x, y, cw, ch, w_b, h_b, margin):
            return (x, y, cw, ch)
    return None


def _compute_crop_roi(
    W: np.ndarray,
    h_a: int,
    w_a: int,
    h_b: int,
    w_b: int,
    inside_b_margin: float,
) -> tuple[int, int, int, int] | None:
    """
    计算 A 上裁剪矩形 (x, y, w, h)：先 B 在 A 上 footprint 的轴对齐外接框，再对称内收，
    使整块矩形在 warpAffine(WARP_INVERSE_MAP) 下仅从 B 内插值，避免外接框四角反射伪影。
    """
    loose = _loose_footprint_aabb_in_a(W, h_a, w_a, h_b, w_b)
    if loose is None:
        return None
    return _shrink_aabb_symmetric_until_inside_b(loose, W, w_a, h_a, w_b, h_b, inside_b_margin)


def register_pair(
    img_a: np.ndarray,
    img_b: np.ndarray,
    motion: int,
    use_orb_init: bool,
    scales: list[float],
    min_ecc_cc: float | None,
    min_ncc: float | None,
) -> tuple[np.ndarray | None, dict]:
    """
    返回 (warp_matrix 或 None 表示失败应回退原图, 指标字典)。
    warp_matrix 用于 warpAffine(..., WARP_INVERSE_MAP) 将 B 对齐到 A。
    """
    h, w = img_a.shape[:2]
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)

    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 2000, 1e-6)
    s0 = scales[0]
    tw0 = max(32, int(round(w * s0)))
    th0 = max(32, int(round(h * s0)))
    ga0 = cv2.resize(gray_a, (tw0, th0), interpolation=cv2.INTER_AREA)
    gb0 = cv2.resize(gray_b, (tw0, th0), interpolation=cv2.INTER_AREA)
    warp_init = None
    if use_orb_init:
        warp_init = orb_initial_inverse_warp(ga0, gb0)

    info: dict = {"orb_init": warp_init is not None}
    try:
        W, ecc_cc = pyramid_find_transform_ecc(
            gray_a,
            gray_b,
            motion,
            criteria,
            warp_init,
            scales,
            gauss_ksize=0,
        )
    except cv2.error as e:
        info["error"] = str(e)
        return None, info

    info["ecc_correlation"] = ecc_cc
    ncc = ncc_after_warp(gray_a, gray_b, W, h, w)
    info["ncc"] = ncc

    if min_ecc_cc is not None and ecc_cc < min_ecc_cc:
        info["reject"] = "ecc_cc_below_threshold"
        return None, info
    if min_ncc is not None and ncc < min_ncc:
        info["reject"] = "ncc_below_threshold"
        return None, info

    return W, info


def parse_scales(s: str) -> list[float]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    scales = [float(p) for p in parts]
    if not scales or scales[-1] != 1.0:
        raise ValueError("scales 须为非空列表且最后一级须为 1.0，例如 0.25,0.5,1.0")
    return scales


def register_batch(
    a_dir: str,
    b_dir: str,
    out_b_dir: str,
    warp_dir: str,
    motion_name: str,
    scales_str: str,
    use_orb_init: bool,
    min_ecc_cc: float | None,
    min_ncc: float | None,
    crop_border: bool = True,
    log_json: str | None = None,
) -> list[dict]:
    """按目录批处理配准；参数通常来自文件顶部接口常量。"""
    os.makedirs(warp_dir, exist_ok=True)

    if crop_border:
        out_a_crop = os.path.join(os.path.dirname(out_b_dir), "A_cropped")
        out_b_crop = os.path.join(os.path.dirname(out_b_dir), "B_cropped")
        os.makedirs(out_a_crop, exist_ok=True)
        os.makedirs(out_b_crop, exist_ok=True)
        os.makedirs(out_b_dir, exist_ok=True)
    else:
        out_a_crop = out_b_crop = None
        os.makedirs(out_b_dir, exist_ok=True)

    motion = _motion_type(motion_name)
    scales = parse_scales(scales_str)

    files = sorted(os.listdir(a_dir))
    print(
        f"共 {len(files)} 个文件（过滤后成对处理），motion={motion_name}, scales={scales}, ORB初值={use_orb_init}\n"
    )

    log_lines: list[dict] = []

    for fname in tqdm(files):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path_a = os.path.join(a_dir, fname)
        path_b = os.path.join(b_dir, fname)
        if not os.path.isfile(path_b):
            tqdm.write(f"[Skip] B 中无对应文件: {fname}")
            continue

        img_a = imread_unicode(path_a)
        img_b = imread_unicode(path_b)
        if img_a is None or img_b is None:
            tqdm.write(f"[Skip] 读取失败: {fname}")
            continue

        stem = os.path.splitext(fname)[0]
        warp_path = os.path.join(warp_dir, stem + ".npy")
        meta_path = os.path.join(warp_dir, stem + ".json")

        W, info = register_pair(
            img_a,
            img_b,
            motion,
            use_orb_init,
            scales,
            min_ecc_cc,
            min_ncc,
        )

        rec = {"file": fname, **{k: v for k, v in info.items() if k != "error"}}
        if W is None:
            tqdm.write(f"[Warn] 配准未采用变换 {fname}: {info}")
            fallback_dir = out_b_crop if crop_border else out_b_dir
            imwrite_unicode(os.path.join(fallback_dir, fname), img_b)
            rec["used_fallback"] = True
            rec["warp_saved"] = False
        else:
            h, w = img_a.shape[:2]
            h_b, w_b = img_b.shape[:2]

            border_mode = cv2.BORDER_CONSTANT if crop_border else cv2.BORDER_REFLECT
            border_val = (0, 0, 0) if crop_border else None
            warp_kw: dict = {
                "flags": cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                "borderMode": border_mode,
            }
            if border_val is not None:
                warp_kw["borderValue"] = border_val
            img_b_aligned = cv2.warpAffine(img_b, W, (w, h), **warp_kw)
            np.save(warp_path, W.astype(np.float32))

            meta = {
                "file": fname,
                "motion": motion_name,
                "scales": scales,
                "ecc_correlation": info.get("ecc_correlation"),
                "ncc": info.get("ncc"),
                "orb_init": info.get("orb_init"),
            }

            if crop_border:
                roi = _compute_crop_roi(W, h, w, h_b, w_b, CROP_INSIDE_B_MARGIN)
                if roi is not None:
                    x, y, cw, ch = roi
                    imwrite_unicode(os.path.join(out_a_crop, fname), img_a[y:y + ch, x:x + cw])
                    imwrite_unicode(os.path.join(out_b_crop, fname), img_b_aligned[y:y + ch, x:x + cw])
                    meta["crop_roi"] = {"x": int(x), "y": int(y), "w": int(cw), "h": int(ch)}
                else:
                    tqdm.write(
                        f"[Warn] {fname} 无满足「无反射」的裁剪框（可调 CROP_INSIDE_B_MARGIN 或检查几何），已写入整幅 B_registered"
                    )
                    imwrite_unicode(os.path.join(out_b_dir, fname), img_b_aligned)
                    meta["crop_roi"] = None
                    meta["crop_note"] = "no_mirror_safe_roi_fallback_full"
            else:
                imwrite_unicode(os.path.join(out_b_dir, fname), img_b_aligned)

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            rec["used_fallback"] = False
            rec["warp_saved"] = True

        log_lines.append(rec)

    if log_json:
        with open(log_json, "w", encoding="utf-8") as f:
            for row in log_lines:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n完成。对齐 B: {out_b_dir}\nwarp 与 meta: {warp_dir}")
    if log_json:
        print(f"日志: {log_json}")
    return log_lines


def find_ab_folders(root_dir: str) -> list[tuple[str, str, str, str, str]]:
    """扫描 root_dir 下所有含 A/ 和 B/ 的子文件夹，返回 (子文件夹名, A_DIR, B_DIR, OUT_B_DIR, WARP_DIR)。"""
    pairs = []
    for entry in sorted(os.listdir(root_dir)):
        sub = os.path.join(root_dir, entry)
        if not os.path.isdir(sub):
            continue
        a_dir = os.path.join(sub, "A")
        b_dir = os.path.join(sub, "B")
        if os.path.isdir(a_dir) and os.path.isdir(b_dir):
            out_b = os.path.join(sub, "B_registered")
            warp = os.path.join(sub, "warp_meta")
            pairs.append((entry, a_dir, b_dir, out_b, warp))
    return pairs


def process_ab_pair(name: str, a_dir: str, b_dir: str, out_b: str, warp: str) -> list[dict]:
    """处理单个 A/B 配准对。"""
    print(f"\n  >>> {name}")
    print(f"    A → {a_dir}")
    print(f"    B → {b_dir}")
    return register_batch(
        a_dir, b_dir, out_b, warp,
        MOTION, SCALES, USE_ORB_INIT, MIN_ECC_CC, MIN_NCC,
        crop_border=CROP_BORDER, log_json=None,
    )


def main():
    print(f"根目录：{ROOT_DIR}")
    print(f"多文件夹模式：{'开启' if Mutil_DIR else '关闭'}")
    print("-" * 50)

    step, total = 1, 3
    total_log = []

    if Mutil_DIR:
        # --- 遍历所有含 A/B 的子文件夹 ---
        print(f"[{step}/{total}] 扫描含 A/B 的子文件夹...")
        step += 1
        pairs = find_ab_folders(ROOT_DIR)
        if not pairs:
            print("  未找到含 A/B 的子文件夹，退出。")
            return
        print(f"  共 {len(pairs)} 个：")
        for name, *_ in pairs:
            print(f"    {name}")

        print(f"[{step}/{total}] 批量 ECC 配准...")
        step += 1
        for idx, (name, a_dir, b_dir, out_b, warp) in enumerate(pairs, 1):
            print(f"\n  [{idx}/{len(pairs)}]")
            log_lines = process_ab_pair(name, a_dir, b_dir, out_b, warp)
            total_log.extend(log_lines)
    else:
        # --- 只处理 ROOT_DIR 自身（直接含 A/B） ---
        print(f"[{step}/{total}] 检查 A/B 目录...")
        step += 1
        a_dir = os.path.join(ROOT_DIR, "A")
        b_dir = os.path.join(ROOT_DIR, "B")
        if not os.path.isdir(a_dir) or not os.path.isdir(b_dir):
            print("  [错误] ROOT_DIR 下缺少 A/ 或 B/，退出。")
            return
        print(f"    A → {a_dir}")
        print(f"    B → {b_dir}")

        print(f"[{step}/{total}] ECC 配准...")
        step += 1
        name = os.path.basename(ROOT_DIR)
        out_b = os.path.join(ROOT_DIR, "B_registered")
        warp = os.path.join(ROOT_DIR, "warp_meta")
        log_lines = process_ab_pair(name, a_dir, b_dir, out_b, warp)
        total_log.extend(log_lines)

    print(f"\n[{step}/{total}] 保存日志...")
    if LOG_JSON:
        with open(LOG_JSON, "w", encoding="utf-8") as f:
            for row in total_log:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  总日志已保存：{LOG_JSON}")
    else:
        print("  未配置 LOG_JSON，跳过")

    print("-" * 50)
    print("完成！")


if __name__ == "__main__":
    main()
