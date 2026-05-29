#!/usr/bin/env python3
"""合成带已知字体+样式的「视频帧/视频」,给 F1/F2 做有 ground-truth 的端到端验证。

真实抖音无可知字体 ground-truth(spec §1);合成视频则把 font/color/stroke/position/animation 都钉死,
跑完管线后能逐项对答案。注意:渲染器仍是 Pillow(同 F0 局限),但叠加了真实 h264 编码/解码 + OCR 切分,
比 F0 的「渲染图直接退化」更接近真实成像链路。
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _bg(w: int, h: int, seed: int) -> Image.Image:
    """photo 风背景:斜向渐变 + 色块 + 噪声。"""
    rng = np.random.default_rng(seed)
    c0, c1 = rng.integers(20, 100, 3), rng.integers(60, 160, 3)
    yy = np.linspace(0, 1, h)[:, None, None]
    grad = (c0 * (1 - yy) + c1 * yy).astype(np.uint8)
    arr = np.broadcast_to(grad, (h, w, 3)).copy()
    for _ in range(6):                          # 随机色块,模拟画面内容
        x, y = rng.integers(0, w), rng.integers(0, h)
        rw, rh = rng.integers(60, 240, 2)
        col = rng.integers(0, 200, 3)
        arr[max(0, y):y + rh, max(0, x):x + rw] = (
            0.5 * arr[max(0, y):y + rh, max(0, x):x + rw] + 0.5 * col).astype(np.uint8)
    arr = np.clip(arr.astype(int) + rng.integers(-12, 12, (h, w, 3)), 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def render_subtitle(bg: Image.Image, text: str, font_path: Path, font_px: int,
                    fill=(255, 255, 255), stroke=(0, 0, 0), stroke_w=4,
                    position="bottom-center", reveal=1.0, scale=1.0, alpha=1.0,
                    y_off=0) -> Image.Image:
    """把字幕画到 bg 上。reveal: typewriter 显示比例; scale: pop 缩放; alpha: fade。"""
    img = bg.convert("RGBA")
    W, H = img.size
    shown = text[:max(1, round(len(text) * reveal))] if reveal < 1 else text
    px = max(8, int(font_px * scale))
    font = ImageFont.truetype(str(font_path), px)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bb = d.textbbox((0, 0), shown, font=font, stroke_width=stroke_w)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (W - tw) / 2 - bb[0]
    if position == "bottom-center":
        y = H * 0.82 - th / 2 - bb[1] + y_off
    elif position == "top":
        y = H * 0.12 - bb[1] + y_off
    else:  # center
        y = (H - th) / 2 - bb[1] + y_off
    d.text((x, y), shown, font=font, fill=(*fill, int(255 * alpha)),
           stroke_width=stroke_w, stroke_fill=(*stroke, int(255 * alpha)))
    return Image.alpha_composite(img, layer).convert("RGB")


def make_video(out: Path, text: str, font_path: Path, *, dur=3.0, fps=15,
               font_px=84, fill=(255, 255, 255), stroke=(0, 0, 0), stroke_w=4,
               position="bottom-center", animation="none", w=720, h=1280, seed=7):
    bg = _bg(w, h, seed)
    n = int(dur * fps)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i in range(n):
            t = i / n
            reveal, scale, alpha, y_off = 1.0, 1.0, 1.0, 0
            if animation == "fade":
                alpha = min(1.0, t / 0.25)
            elif animation == "pop":
                scale = min(1.0, 0.4 + t / 0.2 * 0.6) if t < 0.2 else 1.0
            elif animation == "typewriter":
                reveal = min(1.0, t / 0.5)
            elif animation == "scroll":
                y_off = int((0.5 - t) * h * 0.3)
            frame = render_subtitle(bg, text, font_path, font_px, fill, stroke, stroke_w,
                                    position, reveal, scale, alpha, y_off)
            frame.save(td / f"f_{i:05d}.png")
        subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(td / "f_%05d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", str(out),
             "-hide_banner", "-loglevel", "error"], check=True)
    return out


if __name__ == "__main__":
    import sys
    ROOT = Path(__file__).resolve().parent.parent
    fp = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets/fonts/Aa全息黑体.ttf"
    out = ROOT / "outputs/font_smoke/synth_frame.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    bg = _bg(720, 1280, 7)
    render_subtitle(bg, "今天教你一个小技巧", fp, 84).save(out)
    print(f"[synth] frame → {out}  (font={fp.stem})")
