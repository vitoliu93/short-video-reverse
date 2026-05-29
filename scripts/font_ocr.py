#!/usr/bin/env python3
"""OCR 前端(借用,非研究重点):ffmpeg 抽帧 + RapidOCR → 文字区域(text/bbox/crop)。

contract:
  extract_frames(video, fps) -> [(t_sec, np.ndarray BGR)]
  ocr_image(img) -> [Region]  其中 Region = {text, quad, box(x,y,w,h), score, crop(np BGR)}

per-char crop: CJK 字幕近似等宽全角,按 text 长度把 line bbox 等分(POC 口径,见 spec §8 局限)。
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

_OCR = None


def ocr_engine():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR


@dataclass
class Region:
    text: str
    quad: list                      # 4×[x,y]
    box: tuple                      # (x,y,w,h) 轴对齐
    score: float
    crop: np.ndarray = field(repr=False)  # BGR

    def char_crops(self) -> list[np.ndarray]:
        """按字数等分 line crop(CJK 等宽近似)。返回每字一个 BGR 子图。"""
        n = len(self.text)
        if n == 0:
            return []
        h, w = self.crop.shape[:2]
        step = w / n
        return [self.crop[:, int(i * step):int((i + 1) * step)] for i in range(n)]


def extract_frames(video: Path, fps: float = 2.0) -> list[tuple[float, np.ndarray]]:
    """ffmpeg 按 fps 抽帧 → [(t_sec, BGR帧)]。"""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cmd = ["ffmpeg", "-i", str(video), "-vf", f"fps={fps}", "-q:v", "2",
               str(td / "f_%05d.jpg"), "-hide_banner", "-loglevel", "error"]
        subprocess.run(cmd, check=True)
        frames = []
        for i, fp in enumerate(sorted(td.glob("f_*.jpg"))):
            img = cv2.imread(str(fp))
            if img is not None:
                frames.append((i / fps, img))
        return frames


def ocr_image(img: np.ndarray, min_score: float = 0.5) -> list[Region]:
    res, _ = ocr_engine()(img)
    out = []
    if not res:
        return out
    for quad, text, score in res:
        if score < min_score or not text.strip():
            continue
        xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
        x0, y0 = int(max(0, min(xs))), int(max(0, min(ys)))
        x1, y1 = int(min(img.shape[1], max(xs))), int(min(img.shape[0], max(ys)))
        if x1 <= x0 or y1 <= y0:
            continue
        out.append(Region(text=text.strip(), quad=quad, box=(x0, y0, x1 - x0, y1 - y0),
                          score=float(score), crop=img[y0:y1, x0:x1].copy()))
    return out


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1])
    if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"):
        frames = extract_frames(p, fps=1.0)
        print(f"[frames] {len(frames)} @1fps")
        img = frames[len(frames) // 2][1] if frames else None
    else:
        img = cv2.imread(str(p))
    if img is None:
        print("no image"); sys.exit(1)
    regs = ocr_image(img)
    print(f"[ocr] {len(regs)} regions:")
    for r in regs:
        print(f"  '{r.text}'  box={r.box}  score={r.score:.2f}  chars={len(r.text)}")
