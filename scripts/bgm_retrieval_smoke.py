#!/usr/bin/env python3
"""M0 smoke test: 验证 CLAP 音频→音频检索质量(短视频反解 BGM 子模块最大不确定性)。

做法:
  1. 对 assets/bgm_sample/{lyrics,normal,rhythm}_bgm/ 下的曲库样本逐条算 CLAP embedding
     (每条取 3 个窗口均值池化,L2 归一化)。
  2. 量化:全量 leave-one-out 检索,统计 top-1 / top-5 同类命中率。
  3. 质化:挑若干 query 生成带 <audio> 播放器的 HTML,供人耳听 top-k 像不像。

不依赖 faiss(样本小,numpy 余弦即可),不依赖 Demucs(曲库本身干净)。
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import librosa
import numpy as np
import torch
from transformers import ClapModel, ClapProcessor

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "assets" / "bgm_sample"
OUT_DIR = ROOT / "outputs" / "bgm_smoke"
MODEL_ID = "laion/larger_clap_music"
SR = 48_000
WIN_SEC = 10
WIN_POS = (0.25, 0.50, 0.75)  # 取整首的相对位置做窗口
CATEGORIES = ["lyrics_bgm", "normal_bgm", "rhythm_bgm"]
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".flac"}


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def list_tracks() -> list[tuple[str, Path]]:
    tracks: list[tuple[str, Path]] = []
    for cat in CATEGORIES:
        d = SAMPLE_DIR / cat
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in AUDIO_EXT:
                tracks.append((cat, f))
    return tracks


def load_windows(path: Path) -> list[np.ndarray]:
    """取整首 3 个相对位置的 10s 窗口;短曲则整段。"""
    try:
        y, _ = librosa.load(path, sr=SR, mono=True)
    except Exception as e:  # 解码失败直接暴露,不静默
        print(f"  [decode-fail] {path.name}: {e}")
        return []
    n = len(y)
    if n == 0:
        return []
    win = WIN_SEC * SR
    if n <= win:
        return [y]
    out = []
    for pos in WIN_POS:
        start = int(pos * n) - win // 2
        start = max(0, min(start, n - win))
        out.append(y[start : start + win])
    return out


@torch.no_grad()
def embed_tracks(tracks, model, processor, device) -> np.ndarray:
    vecs = []
    for i, (cat, path) in enumerate(tracks, 1):
        wins = load_windows(path)
        if not wins:
            vecs.append(None)
            continue
        inputs = processor(audios=wins, sampling_rate=SR, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        feats = model.get_audio_features(**inputs)  # [num_win, D] 已投影到共享空间
        v = feats.mean(dim=0)
        v = v / v.norm()
        vecs.append(v.cpu().numpy())
        print(f"  [{i}/{len(tracks)}] {cat}/{path.name}")
    dim = next(v.shape[0] for v in vecs if v is not None)
    return np.stack([v if v is not None else np.zeros(dim, np.float32) for v in vecs])


def evaluate(tracks, emb, topk=5):
    """leave-one-out 检索 + 同类命中率统计。返回 (metrics, per_query_results)."""
    cats = np.array([c for c, _ in tracks])
    valid = np.array([emb[i].any() for i in range(len(tracks))])
    sim = emb @ emb.T
    np.fill_diagonal(sim, -np.inf)

    results = []
    top1_hit = top5_hit = total = 0
    for i in range(len(tracks)):
        if not valid[i]:
            continue
        order = [j for j in np.argsort(-sim[i]) if valid[j]][:topk]
        hits = [(j, float(sim[i, j])) for j in order]
        results.append((i, hits))
        total += 1
        if cats[order[0]] == cats[i]:
            top1_hit += 1
        if any(cats[j] == cats[i] for j in order):
            top5_hit += 1
    metrics = {
        "n_tracks": int(valid.sum()),
        "topk": topk,
        "top1_same_category_rate": round(top1_hit / total, 3),
        "topk_same_category_rate": round(top5_hit / total, 3),
        # 随机基线:同类占比(用于对照,>基线才说明 CLAP 抓到了风格结构)
        "baseline_random_same_cat": round(
            float(np.mean([(cats == c).sum() / len(cats) for c in cats])), 3
        ),
    }
    return metrics, results


def center_embeddings(emb: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """减掉全库质心再 L2 归一化,去掉 CLAP embedding 的公共方向分量(分数压缩的根因)。"""
    mu = emb[valid].mean(axis=0)
    out = emb - mu
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return out / norms


def top1_score_spread(emb: np.ndarray, valid: np.ndarray) -> dict:
    """每条 query 的 top-1 相似度分布,用于看分数有没有被压在窄区间。"""
    sim = emb @ emb.T
    np.fill_diagonal(sim, -np.inf)
    best = []
    for i in range(len(emb)):
        if not valid[i]:
            continue
        order = [j for j in np.argsort(-sim[i]) if valid[j]]
        best.append(float(sim[i, order[0]]))
    a = np.array(best)
    return {
        "min": round(float(a.min()), 3),
        "p10": round(float(np.percentile(a, 10)), 3),
        "median": round(float(np.median(a)), 3),
        "p90": round(float(np.percentile(a, 90)), 3),
        "max": round(float(a.max()), 3),
    }


def rel(path: Path) -> str:
    return str(Path("..") / ".." / path.relative_to(ROOT))


def write_html(tracks, results, metrics, n_queries):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 每类挑前 n_queries//3 条做听感对照
    per = max(1, n_queries // len(CATEGORIES))
    chosen, seen = [], {c: 0 for c in CATEGORIES}
    by_idx = {i: hits for i, hits in results}
    for i, (cat, _) in enumerate(tracks):
        if i in by_idx and seen[cat] < per:
            chosen.append(i)
            seen[cat] += 1

    def audio(path: Path) -> str:
        return f'<audio controls preload="none" src="{html.escape(rel(path))}"></audio>'

    rows = []
    for i in chosen:
        qcat, qpath = tracks[i]
        items = "".join(
            f'<tr><td>{r}</td><td><span class="cat {tracks[j][0]}">{tracks[j][0]}</span></td>'
            f"<td>{score:.3f}</td><td>{html.escape(tracks[j][1].name)}</td>"
            f"<td>{audio(tracks[j][1])}</td></tr>"
            for r, (j, score) in enumerate(by_idx[i], 1)
        )
        rows.append(
            f'<section><h3>Query: <span class="cat {qcat}">{qcat}</span> '
            f"{html.escape(qpath.name)}</h3>{audio(qpath)}"
            f"<table><tr><th>#</th><th>类别</th><th>相似度</th><th>曲名</th><th>试听</th></tr>"
            f"{items}</table></section>"
        )

    doc = f"""<!doctype html><meta charset="utf-8"><title>CLAP BGM 检索 M0</title>
<style>
body{{font-family:-apple-system,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#1d1d1f}}
h1{{font-size:20px}} section{{margin:28px 0;padding:16px;border:1px solid #e5e5e7;border-radius:10px}}
table{{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}}
td,th{{padding:6px 8px;border-bottom:1px solid #f0f0f0;text-align:left;vertical-align:middle}}
audio{{height:32px}}
.cat{{padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600}}
.lyrics_bgm{{background:#ffe9e3;color:#c0392b}} .normal_bgm{{background:#e3f0ff;color:#1f6feb}}
.rhythm_bgm{{background:#e6f7e9;color:#1f9d4d}}
.metrics{{background:#f7f7f9;padding:14px 16px;border-radius:10px;font-size:14px}}
.metrics b{{font-size:18px}}
</style>
<h1>CLAP 音频→音频检索 — M0 验证</h1>
<div class="metrics">
模型 <code>{MODEL_ID}</code> · 样本 {metrics['n_tracks']} 条 · leave-one-out top-{metrics['topk']}<br>
top-1 同类命中率 <b>{metrics['top1_same_category_rate']}</b> ·
top-{metrics['topk']} 同类命中率 <b>{metrics['topk_same_category_rate']}</b> ·
随机基线 {metrics['baseline_random_same_cat']}<br>
<small>同类命中率显著高于随机基线 = CLAP 抓到了风格结构;最终仍以下方人耳试听为准。</small>
</div>
{''.join(rows)}
"""
    out = OUT_DIR / "index.html"
    out.write_text(doc, encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--queries", type=int, default=6, help="HTML 里展示的 query 条数")
    args = ap.parse_args()

    device = pick_device()
    print(f"device={device} model={MODEL_ID}")
    tracks = list_tracks()
    print(f"样本 {len(tracks)} 条:" + ", ".join(f"{c}={sum(1 for x,_ in tracks if x==c)}" for c in CATEGORIES))
    if len(tracks) < 10:
        raise SystemExit("样本太少,先把 assets/bgm_sample/ 下载好")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = OUT_DIR / "emb_cache.npz"
    names = [str(p) for _, p in tracks]

    emb = None
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        if list(z["names"]) == names:
            emb = z["emb"]
            print(f"用缓存 embedding: {cache}")
    if emb is None:
        model = ClapModel.from_pretrained(MODEL_ID).to(device).eval()
        processor = ClapProcessor.from_pretrained(MODEL_ID)
        print("embedding...")
        emb = embed_tracks(tracks, model, processor, device)
        np.savez(cache, emb=emb, names=np.array(names, dtype=object))

    valid = np.array([emb[i].any() for i in range(len(tracks))])
    emb_c = center_embeddings(emb, valid)

    metrics_raw, _ = evaluate(tracks, emb, topk=args.topk)
    metrics_cen, results_cen = evaluate(tracks, emb_c, topk=args.topk)
    metrics = {
        "raw": {**metrics_raw, "top1_score_spread": top1_score_spread(emb, valid)},
        "centered": {**metrics_cen, "top1_score_spread": top1_score_spread(emb_c, valid)},
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    # HTML 用去均值后的分数(推荐口径)
    html_path = write_html(tracks, results_cen, metrics_cen, args.queries)

    print("\n=== 量化结果(raw vs 去均值)===")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"\n听感页(去均值分数): {html_path}")


if __name__ == "__main__":
    main()
