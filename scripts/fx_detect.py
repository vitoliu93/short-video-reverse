#!/usr/bin/env python3
"""fx_detect — 定位短视频里的转场候选窗口。

主定位器：TransNetV2（CPU，可抓硬切+渐变），镜头边界 = 一处转场。
补充：ffmpeg scene 滤镜（仅硬切）作为额外候选，并集去重。
输出：候选窗口 [{t_center, t_start, t_end, gap, prob, src}]，喂给 fx_describe 采样 + VLM 描述。

为何 CPU 不用 mps：X1 实测 mps 比 CPU 还慢且数值不一致会漏掉真实边界
（15s 片：cpu 1.78s/15 镜头 vs mps 2.23s/9 镜头）。见 spec §9-X1。

单跑：uv run scripts/fx_detect.py <video> [--threshold 0.5] [--json]
"""
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # torch libomp guard (仓库约定)

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 边界两侧默认采样半窗（秒）；渐变转场会按 gap 自适应加宽
WIN_PAD = 0.35
# 中心相距小于此值（秒）的候选合并为一个窗口（TransNetV2 与 ffmpeg 报同一处）
MERGE_GAP = 0.30


def video_duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def transnet_boundaries(video: Path, threshold: float = 0.5, device: str = "cpu"):
    """返回 (boundaries, shots)。boundary = 相邻镜头之间的转场；shots = 镜头区间。"""
    from transnetv2_pytorch import TransNetV2

    model = TransNetV2(device=device)
    model.eval()
    scenes = model.detect_scenes(str(video), threshold=threshold)  # 每个 = 一个镜头(shot)
    bounds = []
    for a, b in zip(scenes, scenes[1:]):
        t_end = float(a["end_time"])
        t_start = float(b["start_time"])
        gap = round(t_start - t_end, 3)  # 硬切≈1帧；渐变更大
        bounds.append({
            "t_center": round((t_end + t_start) / 2.0, 3),
            "gap": gap,
            "prob": round(float(b["probability"]), 3),
            "src": "transnet",
        })
    shots = [{
        "shot_id": s["shot_id"],
        "start": round(float(s["start_time"]), 3),
        "end": round(float(s["end_time"]), 3),
        "dur": round(float(s["end_time"]) - float(s["start_time"]), 3),
    } for s in scenes]
    return bounds, shots


def ffmpeg_cuts(video: Path, threshold: float = 0.3):
    """ffmpeg scene 滤镜检测硬切，返回时间戳列表。"""
    out = subprocess.run(
        ["ffmpeg", "-i", str(video), "-filter:v",
         f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    times = []
    for line in out.stderr.splitlines():
        if "pts_time:" in line:
            for tok in line.split():
                if tok.startswith("pts_time:"):
                    times.append(round(float(tok.split(":")[1]), 3))
    return times


def build_windows(video: Path, threshold: float = 0.5):
    """TransNetV2 ⊕ ffmpeg，合并近邻候选，输出带自适应窗宽的转场候选。"""
    dur = video_duration(video)
    bounds, shots = transnet_boundaries(video, threshold=threshold)
    cuts = ffmpeg_cuts(video)

    # 统一成 (t_center, gap, prob, src) 候选列表
    cand = list(bounds)
    for t in cuts:
        cand.append({"t_center": t, "gap": None, "prob": None, "src": "ffmpeg"})
    cand.sort(key=lambda c: c["t_center"])

    # 合并中心相距 < MERGE_GAP 的候选
    merged = []
    for c in cand:
        if merged and abs(c["t_center"] - merged[-1]["_last"]) < MERGE_GAP:
            g = merged[-1]
            g["_members"].append(c)
            g["_last"] = c["t_center"]
        else:
            merged.append({"_members": [c], "_last": c["t_center"]})

    windows = []
    for g in merged:
        mem = g["_members"]
        centers = [m["t_center"] for m in mem]
        center = round(sum(centers) / len(centers), 3)
        gaps = [m["gap"] for m in mem if m["gap"] is not None]
        gap = max(gaps) if gaps else 0.0
        probs = [m["prob"] for m in mem if m["prob"] is not None]
        srcs = sorted({m["src"] for m in mem})
        # 渐变转场窗口要盖住 gap；硬切用默认半窗
        half = max(WIN_PAD, gap / 2.0 + 0.15)
        windows.append({
            "t_center": center,
            "t_start": round(max(0.0, center - half), 3),
            "t_end": round(min(dur, center + half), 3),
            "gap": round(gap, 3),
            "prob": round(max(probs), 3) if probs else None,
            "src": "+".join(srcs),
        })
    return {"duration": round(dur, 3), "n_shots": len(shots),
            "shots": shots, "windows": windows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--json", action="store_true", help="只打印 JSON")
    args = ap.parse_args()

    video = Path(args.video)
    t0 = time.time()
    res = build_windows(video, threshold=args.threshold)
    res["detect_seconds"] = round(time.time() - t0, 2)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    print(f"video={video.name}  duration={res['duration']}s  "
          f"shots={res['n_shots']}  windows={len(res['windows'])}  "
          f"detect={res['detect_seconds']}s")
    print(f"{'t_center':>9} {'window':>16} {'gap':>6} {'prob':>6}  src")
    for w in res["windows"]:
        print(f"{w['t_center']:>9} "
              f"[{w['t_start']:>6},{w['t_end']:>6}] "
              f"{w['gap']:>6} {str(w['prob']):>6}  {w['src']}")


if __name__ == "__main__":
    main()
