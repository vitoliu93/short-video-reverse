#!/usr/bin/env python3
"""Preflight: 验证 (1) 能从库内 TTF 渲染 CJK 字形, (2) RapidOCR 能读回, (3) fonttools 能查字符覆盖.
不是交付件, 仅 F0 前的可行性自检。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets/fonts/Aa全息黑体.ttf"
OUT = ROOT / "outputs/font_smoke/preflight_render.png"
TEXT = "测试中文字体识别"

# 1) fonttools: 字符覆盖
tt = TTFont(str(FONT))
cmap = tt.getBestCmap()
covered = [c for c in TEXT if ord(c) in cmap]
print(f"[fonttools] cmap glyphs={len(cmap)}  query chars covered={len(covered)}/{len(TEXT)}")

# 2) Pillow + freetype 渲染
img = Image.new("RGB", (720, 160), "white")
d = ImageDraw.Draw(img)
f = ImageFont.truetype(str(FONT), 96)
d.text((20, 20), TEXT, fill="black", font=f)
OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
ink = sum(1 for px in img.getdata() if px != (255, 255, 255))
print(f"[render] saved {OUT.name}  ink_pixels={ink} ({'OK 非空白' if ink > 1000 else '!! 空白, 渲染失败'})")

# 3) RapidOCR 读回
ocr = RapidOCR()
res, _ = ocr(str(OUT))
texts = [r[1] for r in res] if res else []
print(f"[ocr] read back: {texts}")
joined = "".join(texts).replace(" ", "")
hit = sum(1 for c in TEXT if c in joined)
print(f"[ocr] char recall vs '{TEXT}': {hit}/{len(TEXT)}")
