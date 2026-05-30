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


def _norm_ttype(p):
    """parsed dict → 规范化 transition type(闭集内或 'unknown')。"""
    rt = p.get("type")
    return rt if rt in fc.TRANSITION_TAGS else "unknown"


def _vote_transition(parses):
    """k 次解析 → 多数投 (present, type);代表解析 = 胜出 type 里 confidence 最高那次。

    type/present run-to-run 漂移(server 端 token 非确定,即便 temperature=0,spec X3),
    多数投票把单次抖动压成可复现标签。confidence/描述等连续字段取代表那次,不投。
    """
    from collections import Counter
    rows = [(bool(p.get("transition_present", False)), _norm_ttype(p), p) for p in parses]
    present = Counter(r[0] for r in rows).most_common(1)[0][0]
    typ = Counter(r[1] for r in rows).most_common(1)[0][0]
    cands = ([p for pr, t, p in rows if pr == present and t == typ]
             or [p for _, t, p in rows if t == typ] or [r[2] for r in rows])
    rep = max(cands, key=lambda p: _num(p.get("confidence")))
    return present, typ, rep


def describe_transition(video, window, creds=None, n=8, width=640, k=1):
    frames = fc.sample_window(video, window["t_start"], window["t_end"], n=n, width=width)
    blocks = [{"type": "text", "text": fc.transition_prompt(len(frames))}]
    for t, b in frames:
        blocks.append({"type": "text", "text": f"[t={t}s]"})
        blocks.append(fc.img_block(b))
    # 帧采样确定、只采一次;VLM 调 k 次投票(k=1 即原行为)
    k = max(1, int(k))
    parses, models, thinkings = [], [], []
    for _ in range(k):
        res = fc.vlm(blocks, creds=creds, max_tokens=1500)
        parses.append(fc.parse_json(res["text"]) or {})
        models.append(res["model"])
        thinkings.append(res.get("thinking") or "")
    present, typ, p = _vote_transition(parses)
    raw_type = p.get("type")
    return {
        "t_start": window["t_start"], "t_center": window["t_center"],
        "t_end": window["t_end"], "gap": window.get("gap"),
        "present": present,
        "type": typ,
        "type_cn": fc.TRANSITION_CN.get(typ, ""),
        "confidence": round(_num(p.get("confidence")), 3),
        "description_cn": p.get("description_cn"),
        "description_en": p.get("description_en"),
        "capcut_category": fc.TRANSITION_CAPCUT.get(typ, ""),
        "capcut_tags": p.get("capcut_tags") or [],
        "visual_cues": p.get("visual_cues") or (thinkings[0][:300] or None),
        "src": window.get("src"),
        "model": models[0],
        "_raw_type": raw_type if typ == "unknown" else None,
        "_parse_ok": bool(p),
        "_k": k,
        "_votes": [_norm_ttype(pp) for pp in parses] if k > 1 else None,
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
    ap.add_argument("--k", type=int, default=1, help="转场 type 多数投票次数(稳住漂移),默认 1")
    args = ap.parse_args()

    creds = fc.load_creds()
    if args.effect:
        out = describe_effect(args.video, args.t_start, args.t_end, creds, n=args.n)
    else:
        win = {"t_start": args.t_start, "t_end": args.t_end,
               "t_center": round((args.t_start + args.t_end) / 2, 3),
               "gap": None, "src": "manual"}
        out = describe_transition(args.video, win, creds, n=args.n, k=args.k)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
