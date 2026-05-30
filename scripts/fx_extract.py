#!/usr/bin/env python3
"""fx_extract — 单视频端到端：定位 → VLM 描述 → 聚合 → outputs/fx/<stem>.json。

数据流（读这个脚本就懂整条管线）：
  video
   → fx_detect.build_windows   : TransNetV2⊕ffmpeg 候选转场窗口 + 镜头区间
   → fx_describe.describe_*     : 每个窗口跨边界采 N 帧 → doubao-seed-2.0-pro → 结构化
   → 聚合                       : VLM 判 present=true 才算真转场（VLM 即对候选的投票）
   → 特效遍(best-effort)        : 较长镜头内部采样 → 特效描述
   → 写 outputs/fx/<stem>.json

跑：uv run scripts/fx_extract.py <video> [--n 8] [--no-effects] [--min-conf 0]
"""
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # fx_detect 经 transnetv2 引入 torch

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx_common as fc
import fx_detect as fd
import fx_describe as fdesc

ROOT = Path(__file__).resolve().parent.parent

# 特效遍：只在时长 ≥ 此值的镜头内采样，最多采 N 个镜头（控成本，特效是 bonus）
EFFECT_MIN_SHOT = 1.2
EFFECT_MAX = 6


def video_size(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(video)],
        capture_output=True, text=True,
    )
    w, h = out.stdout.strip().split("x")
    return int(w), int(h)


def extract(video: Path, n_frames=8, do_effects=True, min_conf=0.0):
    creds = fc.load_creds()
    t0 = time.time()
    det = fd.build_windows(video)
    W, H = video_size(video)
    print(f"[detect] {det['n_shots']} 镜头 → {len(det['windows'])} 候选窗口 "
          f"({time.time()-t0:.1f}s)", file=sys.stderr)

    # ── 转场遍 ───────────────────────────────────────────────────────
    transitions = []
    for i, w in enumerate(det["windows"], 1):
        try:
            t = fdesc.describe_transition(video, w, creds, n=n_frames)
        except Exception as e:                       # 外部 API 偶发瞬时失败：记录但不中断整批
            print(f"[trans {i}/{len(det['windows'])}] t={w['t_center']} 失败: {e}",
                  file=sys.stderr)
            continue
        flag = "✓" if t["present"] else "·"
        print(f"[trans {i}/{len(det['windows'])}] t={w['t_center']} "
              f"{flag} {t['type']}({t['type_cn']}) conf={t['confidence']}",
              file=sys.stderr)
        if t["present"] and t["confidence"] >= min_conf:
            transitions.append(t)

    # ── 特效遍（best-effort，较长镜头内部） ──────────────────────────
    effects = []
    if do_effects:
        cand = sorted([s for s in det["shots"] if s["dur"] >= EFFECT_MIN_SHOT],
                      key=lambda s: -s["dur"])[:EFFECT_MAX]
        for j, s in enumerate(cand, 1):
            mid = (s["start"] + s["end"]) / 2.0
            try:
                e = fdesc.describe_effect(video, max(0.0, mid - 0.5), mid + 0.5, creds, n=6)
            except Exception as ex:
                print(f"[fx {j}/{len(cand)}] shot{s['shot_id']} 失败: {ex}", file=sys.stderr)
                continue
            flag = "✓" if e["present"] else "·"
            print(f"[fx {j}/{len(cand)}] shot{s['shot_id']}@{round(mid,1)}s "
                  f"{flag} {e['types']}", file=sys.stderr)
            if e["present"]:
                effects.append(e)

    out = {
        "video": video.stem,
        "frame": [W, H],
        "duration": det["duration"],
        "n_shots": det["n_shots"],
        "n_windows": len(det["windows"]),
        "model": creds["model"],
        "transitions": transitions,
        "effects": effects,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    out_dir = ROOT / "outputs" / "fx"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video.stem}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n→ {out_path.relative_to(ROOT)}  "
          f"({len(transitions)} 转场 / {len(effects)} 特效 / {out['elapsed_seconds']}s)",
          file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--n", type=int, default=8, help="每个转场窗口采样帧数")
    ap.add_argument("--no-effects", action="store_true")
    ap.add_argument("--min-conf", type=float, default=0.0)
    args = ap.parse_args()
    extract(Path(args.video), n_frames=args.n,
            do_effects=not args.no_effects, min_conf=args.min_conf)


if __name__ == "__main__":
    main()
