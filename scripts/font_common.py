#!/usr/bin/env python3
"""字体匹配共享件:字形渲染 / 归一化 / 相似度口径(类比 bgm_common.py)。

口径锁定(见 docs/plan/2026-05-29-font-style-recognition/spec.md §3):
  - 渲染:Pillow ImageFont,黑字白底,字号统一 RENDER_PX,画布留白后裁到 ink bbox。
  - 归一化:灰度 → 自动判墨色极性 → Otsu 二值(墨=前景 True) → 裁 ink bbox → resize 到 CANON×CANON。
  - 相似度:在归一化二值掩码上算 —— mask IoU / Chamfer 相似 / 归一化互相关(NCC)。embedding 口径见 font_embed.py(可选)。

为什么这样:视频里的文字 = 渲染后被压缩/缩放/重上色,与库内字体的「干净渲染」之间只剩**字形形状**差异。
归一化把字号、颜色、位置都抹掉,只留形状,这正是闭集字体判别的信号。
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont, TTCollection
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt
from skimage.filters import threshold_otsu

RENDER_PX = 128      # 渲染字号
CANON = 96           # 归一化后边长
PAD = 24             # 渲染画布留白


# ----------------------------------------------------------------------------- 字符覆盖
def font_cmap(path: Path) -> set[int]:
    """返回字体覆盖的 codepoint 集合;ttc 取第一子字体。"""
    try:
        if str(path).lower().endswith(".ttc"):
            tt = TTCollection(str(path)).fonts[0]
        else:
            tt = TTFont(str(path), fontNumber=0)
        return set(tt.getBestCmap().keys())
    except Exception:
        return set()


def covers(cmap: set[int], chars: str) -> bool:
    return all(ord(c) in cmap for c in chars)


# ----------------------------------------------------------------------------- 渲染
def render_char(path: Path, ch: str, px: int = RENDER_PX) -> Image.Image | None:
    """渲染单字,黑字白底,RGB。失败返回 None。"""
    try:
        font = ImageFont.truetype(str(path), px)
    except Exception:
        return None
    canvas = px + 2 * PAD
    img = Image.new("L", (canvas, canvas), 255)
    d = ImageDraw.Draw(img)
    # 居中:用 textbbox 量
    try:
        bb = d.textbbox((0, 0), ch, font=font)
    except Exception:
        return None
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    if w <= 0 or h <= 0:
        return None
    d.text(((canvas - w) / 2 - bb[0], (canvas - h) / 2 - bb[1]), ch, fill=0, font=font)
    return img.convert("RGB")


# ----------------------------------------------------------------------------- 归一化
def to_mask(img: Image.Image) -> np.ndarray | None:
    """RGB/灰度图 → 归一化二值掩码 (CANON×CANON bool, 墨=True)。无墨返回 None。"""
    g = np.asarray(img.convert("L"), dtype=np.float64)
    if g.std() < 1e-6:
        return None
    # Otsu 分前景/背景;墨色是占比更少的那侧(文字一般比背景少)
    try:
        t = threshold_otsu(g)
    except Exception:
        return None
    dark = g <= t
    ink = dark if dark.mean() <= 0.5 else ~dark   # 墨=少数派,自动适配黑底白字/白底黑字
    ys, xs = np.where(ink)
    if len(xs) == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = ink[y0:y1, x0:x1]
    # 等比放进 CANON 方框(保字形长宽比),居中
    h, w = crop.shape
    s = (CANON - 4) / max(h, w)
    nh, nw = max(1, int(round(h * s))), max(1, int(round(w * s)))
    pil = Image.fromarray((crop * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)
    rs = np.asarray(pil) > 127
    out = np.zeros((CANON, CANON), dtype=bool)
    oy, ox = (CANON - nh) // 2, (CANON - nw) // 2
    out[oy:oy + nh, ox:ox + nw] = rs
    return out


# ----------------------------------------------------------------------------- 相似度
def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 0.0


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    """归一化互相关 (-1~1 → 截到 0~1)。"""
    af, bf = a.astype(np.float64).ravel(), b.astype(np.float64).ravel()
    af -= af.mean(); bf -= bf.mean()
    da, db = np.linalg.norm(af), np.linalg.norm(bf)
    if da < 1e-9 or db < 1e-9:
        return 0.0
    return float(max(0.0, (af @ bf) / (da * db)))


def chamfer_sim(a: np.ndarray, b: np.ndarray) -> float:
    """对称 Chamfer 距离 → 相似度。两图各自的墨点到对方墨点的最近距离均值。"""
    if not a.any() or not b.any():
        return 0.0
    dta = distance_transform_edt(~a)   # 到 a 墨点的距离场
    dtb = distance_transform_edt(~b)
    d = (dta[b].mean() + dtb[a].mean()) / 2.0
    return float(1.0 / (1.0 + d))      # 距离 0 → 相似 1


METRICS = {"iou": iou, "ncc": ncc, "chamfer": chamfer_sim}


# ----------------------------------------------------------------------------- 字重(从匹配到的字体本身测,非退化像素)
def intrinsic_weight(path: Path, chars: str = "国本黑体永的是") -> tuple[str | None, float | None]:
    """闭集匹配定到字体后,字重是该字体的固有属性 → 用**干净渲染**测笔宽/字高,绕开视频退化。
    阈值由库内名字带「粗/常规/细」的字体标定(bold≈0.115 / regular≈0.068 / thin≈0.049)。"""
    rs = []
    for ch in chars:
        img = render_char(path, ch)
        if img is None:
            continue
        m = to_mask(img)
        if m is None:
            continue
        dt = distance_transform_edt(m)
        ridge = dt[dt > 0.5]
        if not ridge.size:
            continue
        ys = np.where(m.any(axis=1))[0]
        gh = ys.max() - ys.min() + 1
        rs.append(2 * float(np.percentile(ridge, 80)) / gh)
    if not rs:
        return None, None
    r = float(np.median(rs))
    w = "bold" if r > 0.092 else ("thin" if r < 0.058 else "regular")
    return w, round(r, 3)


# ----------------------------------------------------------------------------- 退化(模拟视频)
def degrade(img: Image.Image, kind: str, rng: np.random.Generator) -> Image.Image:
    """对干净渲染图施加退化,模拟「视频里抠出来的字」。img: RGB 黑字白底。"""
    if kind == "clean":
        return img
    if kind == "downscale":           # 低分辨率视频:缩小再放大
        w, h = img.size
        f = 0.18
        return img.resize((max(1, int(w * f)), max(1, int(h * f))), Image.LANCZOS).resize((w, h), Image.LANCZOS)
    if kind == "jpeg":                # 压缩块效应
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=18)
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    if kind == "recolor_bg":          # 白字 + 彩色/纹理背景(剪映常见)
        arr = np.asarray(img.convert("L"))
        ink = arr < 128
        out = np.zeros((*arr.shape, 3), dtype=np.uint8)
        bg = rng.integers(0, 120, size=3)            # 暗彩底
        out[:] = bg
        out[ink] = [255, 255, 255]                   # 白字
        noise = rng.integers(-25, 25, size=(*arr.shape, 3))
        out = np.clip(out.astype(int) + noise, 0, 255).astype(np.uint8)
        return Image.fromarray(out)
    if kind == "affine":              # 轻微旋转+剪切:检测框非完美轴对齐 + 渲染器字形度量差异
        ang = float(rng.uniform(-6, 6))
        shear = float(rng.uniform(-0.12, 0.12))
        a, b2 = np.cos(np.radians(ang)), np.sin(np.radians(ang))
        w, h = img.size
        cx, cy = w / 2, h / 2
        # 旋转 + x 方向剪切,绕中心
        coeffs = (a, b2 + shear * a, cx - a * cx - (b2 + shear * a) * cy,
                  -b2, a + shear * -b2, cy + b2 * cx - (a + shear * -b2) * cy)
        return img.transform((w, h), Image.AFFINE, coeffs, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    if kind == "combo":               # 现实:仿射抖动 → 重上色 → 缩放 → jpeg
        x = degrade(img, "affine", rng)
        x = degrade(x, "recolor_bg", rng)
        x = degrade(x, "downscale", rng)
        return degrade(x, "jpeg", rng)
    raise ValueError(kind)


DEGRADATIONS = ["clean", "downscale", "jpeg", "recolor_bg", "affine", "combo"]
