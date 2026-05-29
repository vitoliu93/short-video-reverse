#!/usr/bin/env python3
"""F3 实验:DINOv2 重排能否在真实抖音上让「视频级投票」更集中/一致?

真实数据无 ground-truth → 用「投票集中度」当代理:同一视频同一字幕字体,
若某法 top-1 在各条字幕间更一致(plurality 占比更高)→ 更可信。
流程:抽 N 条主字幕 → NCC top-K → DINOv2 对这 K 个重排 → 比 NCC-only vs DINOv2 的 plurality。

跑:  .venv-font/bin/python scripts/font_rerank_eval.py <video> <json> [--sample 24] [--topk 15]
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_common as fc
import font_embed
import font_ocr
from font_match import FontMatcher

ROOT = Path(__file__).resolve().parent.parent


def frame_at(video, t):
    with tempfile.TemporaryDirectory() as td:
        o = Path(td) / "f.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                        "-q:v", "2", str(o), "-hide_banner", "-loglevel", "error"], check=True)
        return cv2.imread(str(o))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("json")
    ap.add_argument("--sample", type=int, default=24); ap.add_argument("--topk", type=int, default=15)
    args = ap.parse_args()
    video = Path(args.video)
    d = json.loads(Path(args.json).read_text())
    main_subs = [t for t in d["texts"] if t["position"].startswith("bottom") and 4 <= len(t["text"]) <= 14]
    # 均匀抽样
    step = max(1, len(main_subs) // args.sample)
    main_subs = main_subs[::step][:args.sample]
    matcher = FontMatcher()
    name2path = {n: p for n, p in matcher.fonts}
    ref_emb_cache = {}   # (name,char) -> emb

    def ref_emb(name, ch):
        k = (name, ch)
        if k not in ref_emb_cache:
            img = fc.render_char(name2path[name], ch)
            m = fc.to_mask(img) if img is not None else None
            ref_emb_cache[k] = font_embed.embed_masks([m])[0] if m is not None else None
        return ref_emb_cache[k]

    ncc_top1, dino_top1 = [], []
    for t in main_subs:
        mid = (t["appear"]["first"] + t["appear"]["last"]) / 2
        img = frame_at(video, mid)
        if img is None:
            continue
        reg = next((r for r in font_ocr.ocr_image(img)
                    if r.text.replace(" ", "") == t["text"].replace(" ", "")), None)
        if reg is None:
            continue
        ncc = matcher.match(reg.char_crops(), reg.text, topk=args.topk)
        if not ncc:
            continue
        ncc_top1.append(ncc[0]["name"])
        # DINOv2 重排:query 字符 emb vs 每个候选同字干净渲染 emb
        qmasks = matcher._query_masks(reg.char_crops(), reg.text)
        chars = [c for c in dict.fromkeys(reg.text) if c in qmasks]
        if not chars:
            dino_top1.append(ncc[0]["name"]); continue
        qemb = font_embed.embed_masks([qmasks[c] for c in chars])   # [nc,D]
        best, bestsc = ncc[0]["name"], -1
        for cand in ncc:
            sims = []
            for i, c in enumerate(chars):
                re = ref_emb(cand["name"], c)
                if re is not None:
                    sims.append(float(qemb[i] @ re))
            if sims and np.mean(sims) > bestsc:
                bestsc, best = float(np.mean(sims)), cand["name"]
        dino_top1.append(best)

    def conc(votes):
        c = collections.Counter(votes)
        top = c.most_common(3)
        return top, (top[0][1] / len(votes) if votes else 0)

    n_top, n_frac = conc(ncc_top1)
    d_top, d_frac = conc(dino_top1)
    print(f"\n===== {video.stem}: {len(ncc_top1)} 条主字幕 =====")
    print(f"  NCC   top-1 plurality: {n_top}   集中度={n_frac:.2f}")
    print(f"  DINO  top-1 plurality: {d_top}   集中度={d_frac:.2f}")
    print(f"  → DINOv2 重排{'更集中(可能更可信)' if d_frac > n_frac + 0.05 else '没有更集中' if d_frac < n_frac - 0.05 else '与 NCC 相当'}")


if __name__ == "__main__":
    main()
