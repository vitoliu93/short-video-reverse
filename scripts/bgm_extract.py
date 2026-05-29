#!/usr/bin/env python3
"""M2 全链路:短视频 → 结构化 bgm{} JSON(schema 见 docs/BGM-反解-spec.md §1)。

  video.mp4
    │ ffmpeg 抽音
    ▼
  audio.wav ──Demucs(A)──> music.wav
                              │
                  ┌───────────┴───────────┐
            C: librosa DSP            B2: CLAP
            volume/start/end/tempo    style_tags + 库内 match
                  └───────────┬───────────┘
                              ▼
                          bgm{} JSON

模块全部复用 M1 件:bgm_separate(A) / bgm_dsp(C) / bgm_common(CLAP) + outputs/bgm_index(faiss)。
"""
from __future__ import annotations

import os

# faiss 与 torch 在 macOS 各自链了一份 libomp,共存会 OMP Error #15。
# 用官方文档的 workaround;flat 检索无并行正确性风险。必须在 import torch/faiss 前设。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bgm_common import center, embed_file, embed_texts, load_clap  # noqa: E402
from bgm_dsp import dsp_describe  # noqa: E402
from bgm_separate import run as separate_run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = ROOT / "outputs" / "bgm_index"
OUT_DIR = ROOT / "outputs" / "bgm"
PRESENCE_RMS = 0.01          # music stem 包络峰值低于此视为「无 BGM」
TAG_TOPN = 5

# 零样本 style 词表(BGM 常见风格/情绪),CLAP 文字→音频打分取 top-N
STYLE_TAGS = [
    "upbeat", "energetic", "calm", "relaxing", "sad", "happy", "epic", "cinematic",
    "electronic", "acoustic", "rock", "pop", "hip hop", "classical", "ambient",
    "suspenseful", "romantic", "dramatic", "uplifting", "dark", "intense", "chill",
]


def load_index():
    import faiss

    index = faiss.read_index(str(INDEX_DIR / "index.faiss"))
    centroid = np.load(INDEX_DIR / "centroid.npy")
    meta = [json.loads(l) for l in (INDEX_DIR / "metadata.jsonl").open(encoding="utf-8")]
    return index, centroid, meta


def style_tags(vec_raw, model, processor, device, topn=TAG_TOPN):
    """raw 音频 embedding × 文字 embedding 的 cosine,取 top-N 标签(文字侧不去质心)。"""
    txt = embed_texts([f"{t} music" for t in STYLE_TAGS], model, processor, device)
    sims = txt @ vec_raw
    order = np.argsort(-sims)[:topn]
    return [STYLE_TAGS[i] for i in order]


def retrieve(vec_raw, centroid, index, meta, topk=5):
    q = center(vec_raw, centroid).astype("float32")[None]
    D, I = index.search(q, topk)
    top = [{"url": meta[i]["url"], "categories": meta[i]["categories"], "score": round(float(d), 3)}
           for d, i in zip(D[0], I[0])]
    best = top[0]
    return {"audio_url": best["url"], "categories": best["categories"],
            "score": best["score"], "topk": top}


def extract(video: Path, model, processor, device, index, centroid, meta) -> dict:
    with tempfile.TemporaryDirectory() as td:
        stems = separate_run(video, Path(td))          # A:分离
        music = stems["music"]
        c = dsp_describe(music)                         # C:DSP

        peak = max(c["volume_profile"]["values"]) if c["volume_profile"]["values"] else 0.0
        present = peak >= PRESENCE_RMS
        bgm = {
            "present": present,
            "start": c["start"], "end": c["end"],
            "volume_profile": c["volume_profile"],
            "beat": c["beat"],
        }
        if not present:                                # 无 BGM → 不做 B2
            bgm["style_tags"] = []
            bgm["match"] = None
            return bgm

        vec, _ = embed_file(music, model, processor, device)   # B2:CLAP
        bgm["style_tags"] = style_tags(vec, model, processor, device)
        bgm["match"] = retrieve(vec, centroid, index, meta)
    return bgm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="默认 outputs/bgm/<name>.json")
    args = ap.parse_args()

    model, processor, device = load_clap()
    index, centroid, meta = load_index()
    print(f"device={device}  index={index.ntotal} 向量")

    bgm = extract(args.video, model, processor, device, index, centroid, meta)

    out = args.out or OUT_DIR / f"{args.video.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"bgm": bgm}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台只打摘要(volume_profile 太长)
    summary = {k: v for k, v in bgm.items() if k != "volume_profile"}
    summary["volume_profile"] = f"<{len(bgm['volume_profile']['values'])} pts @ {bgm['volume_profile']['hz']}Hz>"
    print(json.dumps({"bgm": summary}, ensure_ascii=False, indent=2))
    print(f"\n完整 → {out}")


if __name__ == "__main__":
    main()
