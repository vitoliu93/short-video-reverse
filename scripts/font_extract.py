#!/usr/bin/env python3
"""F2 全链路:video → 抽帧 → OCR → [字体匹配 ‖ 颜色/修饰 ‖ 字重字号 ‖ 位置 ‖ 动画] → texts[] JSON。

复用 F0/F1 件:font_common(口径) / font_ocr(前端) / font_match(字体) / font_style(样式)。
跑:  .venv-font/bin/python scripts/font_extract.py <video> [--fps 4] [--max-fonts N]
出:  outputs/font/<name>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_common as fc
import font_ocr
import font_style
from font_match import FontMatcher

ROOT = Path(__file__).resolve().parent.parent


def _norm(s: str) -> str:
    return "".join(s.split())


def group_events(per_frame, frame_w):
    """把多帧里的同一条字幕聚成 event。键:文字相似(一个是另一个前缀,容 typewriter)+ 框水平接近。"""
    events = []
    for t, regs in per_frame:
        for r in regs:
            cx = (r.box[0] + r.box[2] / 2) / frame_w
            hit = None
            for e in events:
                a, b = _norm(r.text), _norm(e["text_full"])
                same = a == b or a.startswith(b) or b.startswith(a)
                if same and abs(cx - e["cx"]) < 0.18:
                    hit = e
                    break
            if hit is None:
                events.append({"text_full": r.text, "cx": cx, "obs": [(t, r)]})
            else:
                hit["obs"].append((t, r))
                if len(r.text) > len(hit["text_full"]):
                    hit["text_full"] = r.text       # 取最完整文本
    return events


def detect_animation(obs, frame_h) -> str:
    obs = sorted(obs, key=lambda o: o[0])
    if len(obs) < 3:
        return "none"
    lens = [len(o[1].text) for o in obs]
    cys = [o[1].box[1] + o[1].box[3] / 2 for o in obs]
    hs = [o[1].box[3] for o in obs]
    # typewriter:字数单调增且起点明显短
    if lens[0] <= 0.6 * max(lens) and lens[-1] >= max(lens) - 1 and all(lens[i] <= lens[i+1] + 1 for i in range(len(lens)-1)):
        return "typewriter"
    # scroll:中心纵向单调移动且幅度大
    span = (max(cys) - min(cys)) / frame_h
    mono = all(cys[i] <= cys[i+1] for i in range(len(cys)-1)) or all(cys[i] >= cys[i+1] for i in range(len(cys)-1))
    if span > 0.15 and mono:
        return "scroll"
    # pop:高度起点小、快速涨到稳定
    if hs[0] < 0.72 * max(hs) and hs[len(hs)//2] >= 0.9 * max(hs):
        return "pop"
    return "none"


def best_obs(obs):
    """取最适合测字体/样式的一帧:文本最全里 OCR 分最高 + 最清晰(拉普拉斯方差)。"""
    full = max(len(o[1].text) for o in obs)
    cand = [o for o in obs if len(o[1].text) >= full - 1]
    def sharp(o):
        g = cv2.cvtColor(o[1].crop, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(g, cv2.CV_64F).var()
    return max(cand, key=lambda o: o[1].score * 0.5 + sharp(o) / 1000.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--max-fonts", type=int, default=None)
    args = ap.parse_args()

    video = Path(args.video)
    frames = font_ocr.extract_frames(video, fps=args.fps)
    if not frames:
        print("no frames"); sys.exit(1)
    H, W = frames[0][1].shape[:2]
    per_frame = [(t, font_ocr.ocr_image(img)) for t, img in frames]
    n_reg = sum(len(r) for _, r in per_frame)
    print(f"[extract] {len(frames)} frames @{args.fps}fps, {W}x{H}, {n_reg} raw regions")

    events = group_events(per_frame, W)
    matcher = FontMatcher(max_fonts=args.max_fonts)
    name2path = {n: p for n, p in matcher.fonts}
    texts = []
    for e in events:
        obs = e["obs"]
        t0, t1 = min(o[0] for o in obs), max(o[0] for o in obs)
        bo = best_obs(obs)
        reg = bo[1]
        top = matcher.match(reg.char_crops(), reg.text, topk=5)
        style = font_style.extract_style(reg.crop, reg.box, H)
        # 字重:从匹配到的字体本身(干净渲染)测,绕开视频退化;匹配失败再退回像素估计
        weight = style.get("weight")
        if top and top[0]["name"] in name2path:
            iw, _ = fc.intrinsic_weight(name2path[top[0]["name"]])
            if iw:
                weight = iw
        x, y, w, h = reg.box
        # 字号用「稳定后」尺寸:pop/zoom 动画下逐帧大小变化,取全 obs 框高 p75(避免被早期小帧带偏)
        settled_h = float(np.percentile([o[1].box[3] for o in obs], 75))
        size_rel = round(settled_h / H, 4)
        pos_box = (x, y, w, int(round(settled_h)))
        texts.append({
            "text": e["text_full"],
            "appear": {"first": round(t0, 2), "last": round(t1, 2), "n_obs": len(obs)},
            "bbox": [round(x / W, 4), round(y / H, 4), round(w / W, 4), round(h / H, 4)],
            "position": font_style.position_of(pos_box, W, H),
            "font": {"match": top[0]["name"] if top else None,
                     "score": top[0]["score"] if top else None,
                     "topk": top},
            "color": {"fill": style.get("fill"), "gradient": style.get("gradient")},
            "decoration": {"stroke": style.get("stroke"), "shadow": style.get("shadow")},
            "weight": weight,
            "size_rel": size_rel,
            "animation": detect_animation(obs, H),
        })
    texts.sort(key=lambda x: x["appear"]["first"])

    out_dir = ROOT / "outputs/font"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{video.stem}.json"
    out.write_text(json.dumps({"video": video.name, "frame": [W, H], "texts": texts},
                              ensure_ascii=False, indent=2))
    print(f"[extract] {len(texts)} text events → {out}")
    for t in texts:
        f = t["font"]
        print(f"  '{t['text'][:16]}' | {t['position']} | font={f['match']}({f['score']}) | "
              f"{t['color']['fill']} stroke={bool(t['decoration']['stroke'])} {t['weight']} | anim={t['animation']}")


if __name__ == "__main__":
    main()
