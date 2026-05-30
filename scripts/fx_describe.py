#!/usr/bin/env python3
"""fx_describe — 单个候选窗口 → VLM → 结构化转场/特效描述。

转场：跨边界采 N 帧 → transition_prompt → doubao-seed-2.0-pro → 规范化成 schema。
特效：镜头内采 N 帧 → effect_prompt → 同模型。

单跑（X1 VLM 客户端冒烟 / 调试单个窗口）：
  uv run scripts/fx_describe.py <video> --t-start 3.84 --t-end 4.54
  uv run scripts/fx_describe.py <video> --t-start 0 --t-end 2.7 --effect
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx_common as fc


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def describe_transition(video, window, creds=None, n=8, width=640):
    frames = fc.sample_window(video, window["t_start"], window["t_end"], n=n, width=width)
    blocks = [{"type": "text", "text": fc.transition_prompt(len(frames))}]
    for t, b in frames:
        blocks.append({"type": "text", "text": f"[t={t}s]"})
        blocks.append(fc.img_block(b))
    res = fc.vlm(blocks, creds=creds, max_tokens=1500)
    p = fc.parse_json(res["text"]) or {}
    raw_type = p.get("type")
    typ = raw_type if raw_type in fc.TRANSITION_TAGS else "unknown"
    return {
        "t_start": window["t_start"], "t_center": window["t_center"],
        "t_end": window["t_end"], "gap": window.get("gap"),
        "present": bool(p.get("transition_present", False)),
        "type": typ,
        "type_cn": fc.TRANSITION_CN.get(typ, ""),
        "confidence": round(_num(p.get("confidence")), 3),
        "description_cn": p.get("description_cn"),
        "description_en": p.get("description_en"),
        "capcut_category": fc.TRANSITION_CAPCUT.get(typ, ""),
        "capcut_tags": p.get("capcut_tags") or [],
        "visual_cues": p.get("visual_cues") or (res["thinking"][:300] or None),
        "src": window.get("src"),
        "model": res["model"],
        "_raw_type": raw_type if typ == "unknown" else None,
        "_parse_ok": bool(p),
    }


def describe_effect(video, t_start, t_end, creds=None, n=6, width=512):
    frames = fc.sample_window(video, t_start, t_end, n=n, width=width)
    blocks = [{"type": "text", "text": fc.effect_prompt(len(frames))}]
    for t, b in frames:
        blocks.append({"type": "text", "text": f"[t={t}s]"})
        blocks.append(fc.img_block(b))
    res = fc.vlm(blocks, creds=creds, max_tokens=1200)
    p = fc.parse_json(res["text"]) or {}
    types = [t for t in (p.get("types") or []) if t in fc.EFFECT_TAGS]
    return {
        "t_start": round(t_start, 3), "t_end": round(t_end, 3),
        "present": bool(p.get("effect_present", False)),
        "types": types,
        "types_cn": [fc.EFFECT_CN.get(t, t) for t in types],
        "confidence": round(_num(p.get("confidence")), 3),
        "description_cn": p.get("description_cn"),
        "description_en": p.get("description_en"),
        "visual_cues": p.get("visual_cues"),
        "model": res["model"],
        "_parse_ok": bool(p),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--t-start", type=float, required=True)
    ap.add_argument("--t-end", type=float, required=True)
    ap.add_argument("--effect", action="store_true", help="按镜头内特效描述（否则按转场）")
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args()

    creds = fc.load_creds()
    if args.effect:
        out = describe_effect(args.video, args.t_start, args.t_end, creds, n=args.n)
    else:
        win = {"t_start": args.t_start, "t_end": args.t_end,
               "t_center": round((args.t_start + args.t_end) / 2, 3),
               "gap": None, "src": "manual"}
        out = describe_transition(args.video, win, creds, n=args.n)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
