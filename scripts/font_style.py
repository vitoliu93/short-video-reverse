#!/usr/bin/env python3
"""S 模块:样式抽取(颜色/修饰/字重/字号)。规则 + opencv,不训练。

口径(spec §4):
  - text mask: Otsu,墨=少数派(自动适配黑底白字/白字深底)。
  - fill: 墨像素主色(中位)。gradient: 沿字高的亮度方差。
  - stroke: 墨膨胀环采样到的对比色 → 描边色 + 宽度(膨胀到颜色变 bg 为止)。
  - shadow: 向某方向偏移的暗带(粗判)。
  - weight: 距离变换求笔画半宽 → 笔宽/字高 → bold/regular/thin。
  - size_rel: box 高 / 画面高。
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt


def _hex(bgr) -> str:
    b, g, r = [int(round(v)) for v in bgr]
    return f"#{r:02X}{g:02X}{b:02X}"


def text_mask(crop_bgr: np.ndarray):
    """返回 (ink_mask bool, gray)。墨=少数派。"""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    t, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = gray <= t
    ink = dark if dark.mean() <= 0.5 else ~dark
    return ink, gray


def extract_style(crop_bgr: np.ndarray, box, frame_h: int) -> dict:
    ink, gray = text_mask(crop_bgr)
    out = {}
    if ink.sum() < 20:
        return {"fill": None, "gradient": None, "stroke": None, "shadow": None,
                "weight": None, "size_rel": round(box[3] / frame_h, 4), "_lowconf": True}

    # --- 填充色 + 渐变 ---
    ink_px = crop_bgr[ink]
    fill_bgr = np.median(ink_px, axis=0)
    out["fill"] = _hex(fill_bgr)
    ys = np.where(ink.any(axis=1))[0]
    if len(ys) > 8:
        top = gray[ys[:len(ys)//3]][ink[ys[:len(ys)//3]]]
        bot = gray[ys[-len(ys)//3:]][ink[ys[-len(ys)//3:]]]
        out["gradient"] = bool(abs(float(top.mean()) - float(bot.mean())) > 35) if top.size and bot.size else False
    else:
        out["gradient"] = False

    # --- 描边:墨膨胀环颜色。真描边 = 连续多层(≥2px)颜色稳定、既不像字也不像背景的色带;
    #     抗锯齿边只有 1 层且颜色随 k 渐变 → 据此排除假阳性 ---
    h_, w_ = ink.shape
    corners = np.concatenate([crop_bgr[:5, :5].reshape(-1, 3), crop_bgr[:5, -5:].reshape(-1, 3),
                              crop_bgr[-5:, :5].reshape(-1, 3), crop_bgr[-5:, -5:].reshape(-1, 3)])
    bg_color = np.median(corners, axis=0)
    ink_u8 = ink.astype(np.uint8)
    ker = np.ones((3, 3), np.uint8)
    rings = []
    for k in range(1, 7):
        outer = cv2.dilate(ink_u8, ker, iterations=k).astype(bool)
        inner = ink if k == 1 else cv2.dilate(ink_u8, ker, iterations=k - 1).astype(bool)
        ring = outer & ~inner                 # 第 k 层壳
        if ring.sum() < 8:
            break
        rings.append(np.median(crop_bgr[ring], axis=0))
    # 从最里层起,数连续「像描边」的层:离 fill 远、离 bg 远、且与上一层颜色稳定
    run, scolor = 0, None
    for j, rc in enumerate(rings):
        stroke_like = np.linalg.norm(rc - fill_bgr) > 45 and np.linalg.norm(rc - bg_color) > 35
        stable = j == 0 or np.linalg.norm(rc - rings[j - 1]) < 28
        if stroke_like and stable:
            run += 1
            scolor = rc if scolor is None else (scolor + rc) / 2
        else:
            break
    out["stroke"] = {"color": _hex(scolor), "width_px": run} if run >= 2 else None

    # --- 阴影:向右下偏移的暗带(简单方向探测) ---
    h, w = ink.shape
    off = max(2, h // 25)
    shifted = np.zeros_like(ink)
    shifted[off:, off:] = ink[:-off, :-off]
    halo = shifted & ~ink
    if out["stroke"]:  # 排除描边环
        dil = cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8),
                         iterations=out["stroke"]["width_px"] + 1).astype(bool)
        halo = halo & ~dil
    out["shadow"] = bool(halo.sum() > ink.sum() * 0.04 and
                         np.linalg.norm(np.median(crop_bgr[halo], axis=0) - bg_color) > 25) if halo.sum() > 10 else False

    # --- 字重:距离变换的「脊」≈ 笔画半宽。用高分位(脊值)而非全墨中位(后者被边缘像素压低) ---
    dt = distance_transform_edt(ink)
    ridge = dt[dt > 0.5]
    half = float(np.percentile(ridge, 80)) if ridge.size else 0.0
    glyph_h = float(ys.max() - ys.min() + 1) if len(ys) else 1.0
    ratio = (2 * half) / glyph_h              # 笔宽 / 字高
    out["weight"] = "bold" if ratio > 0.135 else ("thin" if ratio < 0.075 else "regular")
    out["stroke_ratio"] = round(ratio, 3)

    out["size_rel"] = round(box[3] / frame_h, 4)
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
