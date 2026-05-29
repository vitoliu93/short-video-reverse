#!/usr/bin/env python3
"""F3:真实样本字体匹配「视觉合理性」对比图。真实抖音无 ground-truth 字体 →
把 query 字幕 crop 与匹配到的 top-3 字体的渲染并排,人(或 VLM)判像不像。

跑:  .venv-font/bin/python scripts/font_eval_gallery.py <video> <json> [--topn 8]
出:  outputs/font_eval/<stem>_gallery.png
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_ocr
from font_match import FontMatcher

ROOT = Path(__file__).resolve().parent.parent


def frame_at(video: Path, t: float) -> np.ndarray | None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                        "-q:v", "2", str(out), "-hide_banner", "-loglevel", "error"], check=True)
        return cv2.imread(str(out)) if out.exists() else None


def render_phrase(path: Path, text: str, h: int = 80) -> Image.Image:
    try:
        font = ImageFont.truetype(str(path), h)
    except Exception:
        return Image.new("RGB", (h * len(text), h + 20), "white")
    tmp = Image.new("L", (10, 10))
    bb = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    w, hh = bb[2] - bb[0], bb[3] - bb[1]
    img = Image.new("RGB", (w + 20, hh + 20), "white")
    ImageDraw.Draw(img).text((10 - bb[0], 10 - bb[1]), text, fill="black", font=font)
    return img


def fit(img: Image.Image, W: int, H: int) -> Image.Image:
    img = img.copy(); img.thumbnail((W, H))
    canvas = Image.new("RGB", (W, H), "white")
    canvas.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("json"); ap.add_argument("--topn", type=int, default=8)
    args = ap.parse_args()
    video = Path(args.video)
    data = json.loads(Path(args.json).read_text())
    texts = [t for t in data["texts"] if len(t["text"]) >= 4 and t["font"]["match"]]
    texts.sort(key=lambda t: -(t["font"]["score"] or 0))
    texts = texts[:args.topn]
    matcher = FontMatcher()
    name2path = {n: p for n, p in matcher.fonts}

    cellW, cellH, gap = 360, 90, 6
    cols = 4  # query + top3
    rows = []
    for t in texts:
        mid = (t["appear"]["first"] + t["appear"]["last"]) / 2
        frame = frame_at(video, mid)
        qtile = Image.new("RGB", (cellW, cellH), "#ddd")
        if frame is not None:
            for r in font_ocr.ocr_image(frame):
                if r.text.replace(" ", "") == t["text"].replace(" ", ""):
                    qtile = fit(Image.fromarray(r.crop[:, :, ::-1]), cellW, cellH); break
        cells = [qtile]
        for cand in t["font"]["topk"][:3]:
            p = name2path.get(cand["name"])
            tile = fit(render_phrase(p, t["text"]), cellW, cellH) if p else Image.new("RGB", (cellW, cellH), "white")
            cells.append((tile, cand["name"], cand["score"]))
        rows.append((t, cells))

    H = len(rows) * (cellH + 28) + 30
    W = cols * (cellW + gap) + gap
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)
    try:
        lbl = ImageFont.truetype(str(name2path[texts[0]["font"]["match"]]), 15)
    except Exception:
        lbl = ImageFont.load_default()
    for ri, (t, cells) in enumerate(rows):
        y = 24 + ri * (cellH + 28)
        d.text((gap, y - 18), f'"{t["text"]}"  pos={t["position"]} {t["weight"]} {t["color"]["fill"]} '
               f'stroke={bool(t["decoration"]["stroke"])} anim={t["animation"]}', fill="black", font=lbl)
        for ci, c in enumerate(cells):
            x = gap + ci * (cellW + gap)
            if ci == 0:
                canvas.paste(c, (x, y)); d.rectangle([x, y, x+cellW, y+cellH], outline="blue", width=2)
                d.text((x+3, y+3), "QUERY(真实字幕)", fill="blue", font=lbl)
            else:
                tile, name, sc = c
                canvas.paste(tile, (x, y))
                d.rectangle([x, y, x+cellW, y+cellH], outline=("green" if ci == 1 else "#bbb"), width=2)
                d.text((x+3, y+3), f"#{ci} {name} {sc}", fill=("green" if ci == 1 else "#555"), font=lbl)
    out = ROOT / "outputs/font_eval" / f"{video.stem}_gallery.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"[gallery] {len(rows)} events → {out}")


if __name__ == "__main__":
    main()
