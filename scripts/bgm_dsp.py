#!/usr/bin/env python3
"""模块 C:BGM 用法刻画(纯 DSP,librosa)。

输入分离后的 music stem(或任意音频),产出 eval 的硬指标:
  - volume_profile: 下采样 RMS 包络 + 采样率(Hz)
  - start / end:    BGM 起止时间(秒),按 RMS 越过噪声地板判定
  - beat.tempo:     估计 BPM
  - beat.aligned_with_cuts: 需镜头切点(TransNetV2),未就绪置 null(见 spec §2)

库内曲是纯乐曲,直接喂;视频侧需先过模块 A(Demucs)拿 music stem。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np

ENV_HZ = 10.0          # 包络下采样到 10Hz(每 0.1s 一个点)
PRESENCE_REL = 0.08    # 越过 max-RMS 的此比例视为「有 BGM」


def dsp_describe(path: Path, env_hz: float = ENV_HZ) -> dict:
    y, sr = librosa.load(path, sr=None, mono=True)
    dur = len(y) / sr

    hop = max(1, int(round(sr / env_hz)))
    rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]

    # 起止:RMS 越过 (噪声地板 + 相对阈值) 的首/末帧
    floor = float(np.percentile(rms, 5))
    thresh = floor + PRESENCE_REL * (float(rms.max()) - floor)
    on = np.where(rms > thresh)[0]
    if len(on):
        start = float(on[0] * hop / sr)
        end = float(min((on[-1] + 1) * hop / sr, dur))
    else:
        start = end = 0.0

    tempo = librosa.beat.beat_track(y=y, sr=sr)[0]
    tempo = float(np.asarray(tempo).ravel()[0])

    return {
        "duration": round(dur, 2),
        "volume_profile": {
            "hz": env_hz,
            "values": [round(float(v), 5) for v in rms],
        },
        "start": round(start, 2),
        "end": round(end, 2),
        "beat": {"tempo": round(tempo, 1), "aligned_with_cuts": None},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    r = dsp_describe(args.audio)
    summary = {k: v for k, v in r.items() if k != "volume_profile"}
    summary["volume_profile"] = f"<{len(r['volume_profile']['values'])} pts @ {r['volume_profile']['hz']}Hz>"
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(r, ensure_ascii=False, indent=2))
        print(f"完整结果 → {args.out}")


if __name__ == "__main__":
    main()
