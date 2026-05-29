#!/usr/bin/env python3
"""S 模块:样式抽取(颜色/修饰/字重/字号)。规则 + opencv,不训练。

口径(spec §4,§11 修了颜色极性 bug):
  - 字形区 = 离背景色(四角中位)远的像素(fill+stroke 一起),不依赖明暗极性。
  - 距离变换 dt:字形**内部(高 dt)= 填充**,**外缘薄带(低 dt)= 描边/抗锯齿**。
  - fill: 内部主色(中位)—— 绕开「白字粗黑描边亮底」时锁到黑描边的极性 bug。
  - stroke: 从外向内数「像描边」的层(离 fill 远 & 离 bg 远),≥2 层才算,给色+宽。
  - shadow: glyph 右下偏移的暗带(排除描边)。
  - weight: dt 脊 ≈ 笔画半宽 → 笔宽/字高(extract 用 intrinsic_weight 覆盖,这里是兜底)。
  - size_rel: box 高 / 画面高。
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.filters import threshold_otsu


def _hex(bgr) -> str:
    b, g, r = [int(round(v)) for v in bgr]
    return f"#{r:02X}{g:02X}{b:02X}"


def extract_style(crop_bgr: np.ndarray, box, frame_h: int) -> dict:
    size_rel = round(box[3] / frame_h, 4)
    H_, W_ = crop_bgr.shape[:2]
    # 背景色 = 四角中位;字形区 = 离背景远的像素(极性无关)
    corners = np.concatenate([crop_bgr[:8, :8].reshape(-1, 3), crop_bgr[:8, -8:].reshape(-1, 3),
                              crop_bgr[-8:, :8].reshape(-1, 3), crop_bgr[-8:, -8:].reshape(-1, 3)])
    bg_color = np.median(corners, axis=0)
    diff = np.linalg.norm(crop_bgr.astype(np.float64) - bg_color, axis=2)
    try:
        gthr = max(40.0, float(threshold_otsu(diff))) if diff.std() > 1e-6 else 40.0
    except Exception:
        gthr = 40.0
    glyph = diff > gthr
    if glyph.sum() < 20:
        return {"fill": None, "gradient": None, "stroke": None, "shadow": None,
                "weight": None, "size_rel": size_rel, "_lowconf": True}

    out = {}
    ker = np.ones((3, 3), np.uint8)
    gu8 = glyph.astype(np.uint8)
    dt = distance_transform_edt(glyph)

    # --- 填充色:字形内部(高 dt)主色。修了极性 bug:不再取「少数派墨」(那会是黑描边) ---
    thr_in = max(2.0, float(np.percentile(dt[glyph], 60)))
    interior = glyph & (dt >= thr_in)
    fillreg = interior if interior.sum() >= 15 else glyph
    fill_bgr = np.median(crop_bgr[fillreg], axis=0)
    out["fill"] = _hex(fill_bgr)

    # --- 渐变:interior 上下三分之一亮度差 ---
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    ys = np.where(fillreg.any(axis=1))[0]
    if len(ys) > 8:
        top = gray[ys[:len(ys)//3]][fillreg[ys[:len(ys)//3]]]
        bot = gray[ys[-len(ys)//3:]][fillreg[ys[-len(ys)//3:]]]
        out["gradient"] = bool(top.size and bot.size and abs(float(top.mean()) - float(bot.mean())) > 35)
    else:
        out["gradient"] = False

    # --- 描边:从外向内逐层,数「离 fill 远 & 离 bg 远」的层(描边色既非字也非底) ---
    width, scol = 0, None
    for k in range(1, 7):
        prev = glyph if k == 1 else cv2.erode(gu8, ker, iterations=k - 1).astype(bool)
        layer = prev & ~cv2.erode(gu8, ker, iterations=k).astype(bool)   # 第 k 层(外起)
        if layer.sum() < 5:
            break
        c = np.median(crop_bgr[layer], axis=0)
        if np.linalg.norm(c - fill_bgr) > 45 and np.linalg.norm(c - bg_color) > 20:
            width = k
            scol = c if scol is None else (scol + c) / 2
        else:
            break
    out["stroke"] = {"color": _hex(scol), "width_px": width} if width >= 2 else None

    # --- 阴影:glyph 右下偏移暗带,排除描边环 ---
    off = max(2, H_ // 25)
    shifted = np.zeros_like(glyph)
    shifted[off:, off:] = glyph[:-off, :-off]
    halo = shifted & ~glyph
    if out["stroke"]:
        halo = halo & ~cv2.dilate(gu8, ker, iterations=out["stroke"]["width_px"] + 1).astype(bool)
    out["shadow"] = bool(halo.sum() > glyph.sum() * 0.04 and
                         np.linalg.norm(np.median(crop_bgr[halo], axis=0) - bg_color) > 25) if halo.sum() > 10 else False

    # --- 字重兜底(extract 用 intrinsic_weight 覆盖):dt 脊 ≈ 笔画半宽 ---
    ridge = dt[dt > 0.5]
    half = float(np.percentile(ridge, 80)) if ridge.size else 0.0
    glyph_h = float(ys.max() - ys.min() + 1) if len(ys) else 1.0
    ratio = (2 * half) / glyph_h
    out["weight"] = "bold" if ratio > 0.135 else ("thin" if ratio < 0.075 else "regular")
    out["stroke_ratio"] = round(ratio, 3)
    out["size_rel"] = size_rel
    return out


def position_of(box, frame_w: int, frame_h: int) -> str:
    x, y, w, h = box
    cx, cy = (x + w / 2) / frame_w, (y + h / 2) / frame_h
    big = h / frame_h > 0.095
    vert = "top" if cy < 0.33 else ("bottom" if cy > 0.66 else "center")
    horiz = "left" if cx < 0.33 else ("right" if cx > 0.66 else "center")
    if vert == "center" and horiz == "center":
        return "center-big" if big else "center"
    return f"{vert}-{horiz}" if horiz != "center" else f"{vert}-center"
