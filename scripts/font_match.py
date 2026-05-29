#!/usr/bin/env python3
"""F 模块:闭集字体匹配(query 时)。复用 F0 验证过的口径(font_common: to_mask + NCC)。

输入 = OCR 给的「line crop + text」;按字等分成 char crops,逐字归一化后跟每款候选字体的
现渲染参考比 NCC,按字平均,排序。候选用 cmap 过滤(字体得覆盖查询字)。参考掩码按 (font,char) 缓存。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_common as fc

ROOT = Path(__file__).resolve().parent.parent


class FontMatcher:
    def __init__(self, font_dir: Path = ROOT / "assets/fonts",
                 manifest: Path = ROOT / "outputs/font_index/manifest.jsonl",
                 max_fonts: int | None = None):
        self.font_dir = Path(font_dir)
        rows = [json.loads(l) for l in manifest.read_text().splitlines()]
        if max_fonts:
            rows = rows[:max_fonts]
        self.fonts = [(r["name"], self.font_dir / r["file"]) for r in rows]
        self._cmap: dict[int, set] = {}
        self._ref: dict[tuple, np.ndarray | None] = {}

    def cmap(self, i: int) -> set:
        if i not in self._cmap:
            self._cmap[i] = fc.font_cmap(self.fonts[i][1])
        return self._cmap[i]

    def ref_mask(self, i: int, ch: str):
        k = (i, ch)
        if k not in self._ref:
            img = fc.render_char(self.fonts[i][1], ch)
            self._ref[k] = fc.to_mask(img) if img is not None else None
        return self._ref[k]

    @staticmethod
    def _query_masks(char_crops, text):
        out = {}
        for ch, crop in zip(text, char_crops):
            if crop.size == 0:
                continue
            rgb = crop[:, :, ::-1] if crop.ndim == 3 else crop
            m = fc.to_mask(Image.fromarray(np.ascontiguousarray(rgb)))
            if m is not None:
                out[ch] = (out.get(ch), m)[1]   # 同字多次取最后一个即可
                out[ch] = m
        return out

    def match(self, char_crops, text: str, topk: int = 5):
        qmasks = self._query_masks(char_crops, text)
        chars = [c for c in dict.fromkeys(text) if c in qmasks]   # 去重保序
        if not chars:
            return []
        scores = []
        for i, (name, _) in enumerate(self.fonts):
            cm = self.cmap(i)
            if not all(ord(c) in cm for c in chars):
                continue
            sims = []
            for c in chars:
                rm = self.ref_mask(i, c)
                if rm is not None:
                    sims.append(fc.ncc(qmasks[c], rm))
            if sims:
                scores.append((name, float(np.mean(sims))))
        scores.sort(key=lambda x: -x[1])
        return [{"name": n, "score": round(s, 4)} for n, s in scores[:topk]]


if __name__ == "__main__":
    import cv2
    import font_ocr
    img_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "outputs/font_smoke/synth_frame.png"
    truth = sys.argv[2] if len(sys.argv) > 2 else None
    img = cv2.imread(str(img_path))
    regs = font_ocr.ocr_image(img)
    m = FontMatcher()
    print(f"[matcher] {len(m.fonts)} 款候选字体")
    for r in regs:
        top = m.match(r.char_crops(), r.text, topk=5)
        print(f"\n'{r.text}'  →")
        for rank, t in enumerate(top):
            flag = "  ← TRUTH" if truth and t["name"] == truth else ""
            print(f"  #{rank+1} {t['name']}  {t['score']:.3f}{flag}")
        if truth:
            names = [t["name"] for t in m.match(r.char_crops(), r.text, topk=len(m.fonts))]
            print(f"  truth '{truth}' rank = {names.index(truth)+1 if truth in names else 'NOT FOUND'} / {len(names)}")
