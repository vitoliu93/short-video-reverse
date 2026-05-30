#!/usr/bin/env python3
"""narr_extract — 单视频端到端：叙事结构反解 → outputs/narr/<stem>.json。

数据流（读这个脚本就懂整条管线，见 spec §3）：
  video
   → fx_detect.build_windows : TransNetV2⊕ffmpeg 确定性镜头线 shots[] + 时长
   → narr_common.compute_pacing : 纯计算节奏画像(确定性)
   → narr_common.arc_all     : ARC-Hunyuan 多任务(Summary/Segment/QA/Grounding,带缓存)
   → narr_common.synth_narrative : doubao 把 ARC 自由文本+镜头线 → 闭集 narrative JSON
   → 组装 + provenance        : 写 outputs/narr/<stem>.json

跑：uv run scripts/narr_extract.py <video> [--tasks Summary,Segment,QA,Grounding]
                                          [--no-cache] [--no-synth]
"""
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # fx_detect 经 transnet 引入 torch

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narr_common as nc
import fx_detect as fd

ROOT = Path(__file__).resolve().parent.parent


def _shot_summary(shot, acts):
    """把镜头中点落在哪个 act 区间 → 取该 act 的 summary_cn（best-effort）。"""
    mid = (float(shot["start"]) + float(shot["end"])) / 2.0
    for a in acts or []:
        try:
            if float(a.get("t_start", -1)) <= mid <= float(a.get("t_end", -1)):
                return a.get("summary_cn", "")
        except (TypeError, ValueError):
            continue
    return ""


def extract(video: Path, tasks=None, use_cache=True, do_synth=True):
    t0 = time.time()

    # ── 1. 确定性骨架：镜头线 + 节奏 ────────────────────────────────
    det = fd.build_windows(video)
    pacing = nc.compute_pacing(det)
    print(f"[detect] {det['n_shots']} 镜头 / {det['duration']}s / "
          f"pacing={pacing['label']}({pacing['cuts_per_min']}cuts/min) "
          f"({time.time()-t0:.1f}s)", file=sys.stderr)

    # ── 2. ARC 语义素材（带缓存，命中不烧额度） ────────────────────
    arc = nc.arc_all(video, tasks=tasks, use_cache=use_cache)
    for t, r in arc.items():
        flag = "cache" if r["cached"] else "API"
        head = (r["answer"][:40] or "(空)").replace("\n", " ")
        print(f"[arc:{t}] {flag} ok={r['ok']} :: {head}…", file=sys.stderr)

    # ── 3. doubao 合成 → 闭集 narrative ────────────────────────────
    syn, narrative_err = {}, None
    if do_synth:
        syn = nc.synth_narrative(arc, det["shots"], pacing, det["duration"])
        if syn.get("_parse_error"):
            narrative_err = "synth JSON 解析失败（_raw 见输出）"
            print(f"[synth] ⚠ {narrative_err}", file=sys.stderr)
        else:
            print(f"[synth] hook={syn.get('hook_type')} "
                  f"structure={syn.get('structure')} "
                  f"acts={len(syn.get('acts', []))} model={syn.get('_model')}",
                  file=sys.stderr)

    acts = syn.get("acts", [])
    shots_out = [{
        "shot_id": s["shot_id"], "start": s["start"], "end": s["end"],
        "dur": s["dur"], "summary_cn": _shot_summary(s, acts),
    } for s in det["shots"]]

    out = {
        "video": video.stem,
        "duration": det["duration"],
        "n_shots": det["n_shots"],
        "narrative": {
            "hook_type": syn.get("hook_type"),
            "hook_desc_cn": syn.get("hook_desc_cn"),
            "structure": syn.get("structure"),
            "acts": acts,
            "theme_cn": syn.get("theme_cn"),
            "cta": syn.get("cta"),
            "pacing_profile": pacing,
        },
        "shots": shots_out,
        "content_tags": syn.get("content_tags", []),
        "emotion_curve": syn.get("emotion_curve", []),
        "key_moments": syn.get("key_moments", []),
        "provenance": {
            "shots": "fx_detect(transnet+ffmpeg)",
            "pacing": "computed",
            "narrative": syn.get("_model") or ("(no-synth)" if not do_synth else "(error)"),
            "arc_tasks": list(arc.keys()),
            "arc_model": "ARC-Hunyuan-Video-7B",
            "arc_cached": {t: r["cached"] for t, r in arc.items()},
        },
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    if narrative_err:
        out["narrative"]["_error"] = narrative_err
        out["narrative"]["_raw"] = syn.get("_raw")

    out_dir = ROOT / "outputs" / "narr"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video.stem}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_path.relative_to(ROOT)}  "
          f"({det['n_shots']} 镜头 / {len(acts)} 幕 / {out['elapsed_seconds']}s)",
          file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--tasks", default=",".join(nc.NARR_TASKS),
                    help="逗号分隔的 ARC 任务子集")
    ap.add_argument("--no-cache", action="store_true", help="忽略 ARC 缓存(会烧额度)")
    ap.add_argument("--no-synth", action="store_true", help="跳过 doubao 合成(只出骨架+ARC)")
    args = ap.parse_args()
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    extract(Path(args.video), tasks=tasks,
            use_cache=not args.no_cache, do_synth=not args.no_synth)


if __name__ == "__main__":
    main()
