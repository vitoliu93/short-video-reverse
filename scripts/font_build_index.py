#!/usr/bin/env python3
"""F1:字体参考索引。扫描 assets/fonts 下的 TTF/OTF,抽 cmap 覆盖,落 manifest.jsonl。

为什么 manifest 就够(不预渲染字形图集):F0 证明逐字现渲染+NCC 暴力比对算量 trivial
(~1300 款 ×8 字 ×9216 维点积),且现渲染能比对**查询里实际出现的字符**(图集会被固定字表局限)。
所以「索引」= 字体清单 + 本地 TTF 语料 + cmap;匹配时按需渲染。

跑:  .venv-font/bin/python scripts/font_build_index.py
出:  outputs/font_index/manifest.jsonl   (每行: name / file / ext / n_glyphs / has_preview)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_common as fc

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets/fonts"
OUT = ROOT / "outputs/font_index"
COMMON = "我的中国字一是了人这有他你时"   # 抽样常用字,判覆盖率


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(p for p in FONT_DIR.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".ttc"))
    rows, bad = [], 0
    for p in paths:
        cmap = fc.font_cmap(p)
        if not cmap:
            bad += 1
            continue
        rows.append({
            "name": p.stem,
            "file": p.name,
            "ext": p.suffix.lower(),
            "n_glyphs": len(cmap),
            "common_cover": round(sum(ord(c) in cmap for c in COMMON) / len(COMMON), 3),
            "has_preview": (FONT_DIR / f"{p.stem}.preview.png").exists(),
        })
    with (OUT / "manifest.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    full = sum(1 for r in rows if r["common_cover"] >= 0.99)
    print(f"[index] fonts indexed={len(rows)}  bad/unreadable={bad}  full-common-cover={full}")
    print(f"[out] {OUT/'manifest.jsonl'}")


if __name__ == "__main__":
    main()
