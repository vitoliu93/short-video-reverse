#!/usr/bin/env python3
"""F0:验证闭集字体匹配可行性。

合成集做法(真实视频字体无 ground-truth,精度只能这样量化):
  对样本里的每款字体 q,渲染测试字 → **施加退化**(模拟视频)→ 当作 query;
  参考 = 每款字体 k 的**干净**渲染。query 归一化后跟所有候选比形状,看真字体 q 能否排进 top-K。
  退化是关键:query 与参考同字同体时仅剩字形差异,退化制造真实域差距,否则是平凡的「找相同图」。

跑:  .venv-font/bin/python scripts/font_match_smoke.py [--limit N] [--chamfer] [--embed]
出:  outputs/font_smoke/metrics.json + gallery.html(query vs top-5 可视核对)
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_common as fc

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets/fonts"
OUT = ROOT / "outputs/font_smoke"
TEST_CHARS = "我的中国字永三和"           # 常用 + 笔画复杂度多样(永字八法)
SEED = 20260529


def load_fonts(limit: int | None) -> list[tuple[str, Path]]:
    paths = sorted([p for p in FONT_DIR.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".ttc")])
    keep = []
    for p in paths:
        if fc.covers(fc.font_cmap(p), TEST_CHARS):
            keep.append((p.stem, p))
    if limit:
        keep = keep[:limit]
    return keep


def masks_for(path: Path, chars: str) -> list[np.ndarray] | None:
    """干净渲染 → 归一化掩码列表(每字一个)。任一字失败则整条丢。"""
    out = []
    for ch in chars:
        img = fc.render_char(path, ch)
        if img is None:
            return None
        m = fc.to_mask(img)
        if m is None:
            return None
        out.append(m)
    return out


def degraded_masks(path: Path, chars: str, kind: str, rng) -> list[np.ndarray] | None:
    out = []
    for ch in chars:
        img = fc.render_char(path, ch)
        if img is None:
            return None
        m = fc.to_mask(fc.degrade(img, kind, rng))
        if m is None:
            return None
        out.append(m)
    return out


def flat_bits(masks: list[np.ndarray]) -> np.ndarray:
    """[C, CANON, CANON] bool → [C, P] float。"""
    return np.stack([m.reshape(-1).astype(np.float64) for m in masks])


def score_matrix(query_flat, ref_flat, metric):
    """query_flat: [Q, C, P], ref_flat: [K, C, P] → score[Q,K] (按字平均)。
    iou/ncc 向量化全矩阵;chamfer 走 font_common 逐对(慢,可选)。"""
    Q, C, P = query_flat.shape
    K = ref_flat.shape[0]
    if metric == "ncc":
        # 每字 center+normalize → 余弦 = 点积
        acc = np.zeros((Q, K))
        for c in range(C):
            qc = query_flat[:, c, :].copy(); qc -= qc.mean(1, keepdims=True)
            kc = ref_flat[:, c, :].copy(); kc -= kc.mean(1, keepdims=True)
            qn = np.linalg.norm(qc, axis=1, keepdims=True); qn[qn < 1e-9] = 1
            kn = np.linalg.norm(kc, axis=1, keepdims=True); kn[kn < 1e-9] = 1
            acc += np.clip((qc / qn) @ (kc / kn).T, 0, None)
        return acc / C
    if metric == "iou":
        acc = np.zeros((Q, K))
        for c in range(C):
            qc, kc = query_flat[:, c, :], ref_flat[:, c, :]
            inter = qc @ kc.T
            qa, ka = qc.sum(1), kc.sum(1)
            union = qa[:, None] + ka[None, :] - inter
            union[union < 1e-9] = 1
            acc += inter / union
        return acc / C
    raise ValueError(metric)


def chamfer_matrix(query_masks, ref_masks):
    """逐对 chamfer(慢)。query_masks/ref_masks: list[list[mask]] (font×char)。"""
    Q, K, C = len(query_masks), len(ref_masks), len(query_masks[0])
    score = np.zeros((Q, K))
    for q in range(Q):
        for k in range(K):
            score[q, k] = np.mean([fc.chamfer_sim(query_masks[q][c], ref_masks[k][c]) for c in range(C)])
    return score / 1.0


def ranks_from_scores(score):
    """每行(query)真字体在对角线;返回每个 query 的真字体排名(0-based)。"""
    Q = score.shape[0]
    ranks = []
    for q in range(Q):
        order = np.argsort(-score[q])           # 降序
        ranks.append(int(np.where(order == q)[0][0]))
    return np.array(ranks)


def metrics_from_ranks(ranks, N):
    return {
        "top1": float((ranks == 0).mean()),
        "top5": float((ranks < 5).mean()),
        "top10": float((ranks < 10).mean()),
        "mrr": float(np.mean(1.0 / (ranks + 1))),
        "median_rank": float(np.median(ranks)),
        "random_top5": round(5.0 / N, 4),
    }


def tile(mask) -> Image.Image:
    return Image.fromarray((~mask * 255).astype(np.uint8)).convert("RGB").resize((72, 72), Image.NEAREST)


def thumb(mask) -> str:
    buf = io.BytesIO(); tile(mask).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def build_montage(rows, path):
    """rows: list of (query_tile, [(cand_tile, is_hit, score)]). 存可直接 Read 的 PNG。"""
    from PIL import ImageDraw
    cell, gap, ncol = 72, 8, 6
    H = len(rows) * (cell + gap) + gap
    W = ncol * (cell + gap) + gap
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)
    for r, (q_tile, cands) in enumerate(rows):
        y = gap + r * (cell + gap)
        canvas.paste(q_tile, (gap, y))
        d.rectangle([gap, y, gap + cell, y + cell], outline="blue", width=2)
        for ci, (c_tile, hit, sc) in enumerate(cands):
            x = gap + (ci + 1) * (cell + gap)
            canvas.paste(c_tile, (x, y))
            d.rectangle([x, y, x + cell, y + cell], outline=("green" if hit else "#bbb"), width=3 if hit else 1)
    canvas.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--chamfer", action="store_true")
    ap.add_argument("--embed", action="store_true", help="加 DINOv2 形状 embedding(需 torch)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    fonts = load_fonts(args.limit)
    N = len(fonts)
    print(f"[fonts] {N} 款覆盖测试字 '{TEST_CHARS}'  (assets/fonts 下)")
    if N < 10:
        print("!! 字体太少,等下载完再跑"); sys.exit(1)

    # 参考:干净渲染
    ref_masks, ok_fonts = [], []
    for name, p in fonts:
        m = masks_for(p, TEST_CHARS)
        if m is not None:
            ref_masks.append(m); ok_fonts.append((name, p))
    N = len(ok_fonts)
    ref_flat = np.stack([flat_bits(m) for m in ref_masks])   # [N,C,P]
    print(f"[ref] {N} 款渲染成功")

    metrics_used = ["iou", "ncc"]
    results = {}
    gallery_rows = []

    for kind in fc.DEGRADATIONS:
        # query:同样 N 款,退化渲染
        q_masks = [degraded_masks(p, TEST_CHARS, kind, rng) for _, p in ok_fonts]
        q_flat = np.stack([flat_bits(m) for m in q_masks])
        per_metric = {}
        score_cache = {}
        for metric in metrics_used:
            score = score_matrix(q_flat, ref_flat, metric)
            score_cache[metric] = score
            ranks = ranks_from_scores(score)
            per_metric[metric] = metrics_from_ranks(ranks, N)
        if args.chamfer:
            score = chamfer_matrix(q_masks, ref_masks)
            score_cache["chamfer"] = score
            per_metric["chamfer"] = metrics_from_ranks(ranks_from_scores(score), N)
        results[kind] = per_metric
        line = " | ".join(f"{m}:t1={per_metric[m]['top1']:.2f},t5={per_metric[m]['top5']:.2f}" for m in per_metric)
        print(f"[{kind:11s}] N={N} rand_t5={5/N:.3f}  {line}")

        # gallery:combo 退化下,用最好的 metric 取前 N 个 query 的 top-5
        if kind == "combo":
            best_metric = max(per_metric, key=lambda m: per_metric[m]["top5"])
            score = score_cache[best_metric]
            montage = []
            for q in range(min(14, N)):
                full_order = np.argsort(-score[q])
                order = full_order[:5]
                true_rank = int(np.where(full_order == q)[0][0])
                cells = "".join(
                    f'<td class="{"hit" if k==q else ""}"><img src="data:image/png;base64,{thumb(ref_masks[k][0])}"><br>{ok_fonts[k][0][:10]}<br>{score[q,k]:.2f}</td>'
                    for k in order)
                gallery_rows.append(
                    f'<tr><td class="q"><img src="data:image/png;base64,{thumb(q_masks[q][0])}"><br><b>{ok_fonts[q][0][:10]}</b><br>真rank={true_rank}</td>{cells}</tr>')
                montage.append((tile(q_masks[q][0]),
                                [(tile(ref_masks[k][0]), k == q, score[q, k]) for k in order]))
            build_montage(montage, OUT / "gallery.png")

    (OUT / "metrics.json").write_text(json.dumps(
        {"n_fonts": N, "test_chars": TEST_CHARS, "metric_set": list(results["clean"].keys()), "by_degradation": results},
        ensure_ascii=False, indent=2))

    html = f"""<!doctype html><meta charset=utf8><title>font F0 gallery</title>
<style>body{{font:13px sans-serif}}table{{border-collapse:collapse}}td{{border:1px solid #ccc;padding:4px;text-align:center;font-size:11px}}
td.q{{background:#eef}}td.hit{{background:#cfc;font-weight:bold}}img{{image-rendering:pixelated}}</style>
<h3>combo 退化下:query(左,带退化) → top-5 候选(干净参考)。绿=命中真字体</h3>
<table><tr><th>query</th><th>#1</th><th>#2</th><th>#3</th><th>#4</th><th>#5</th></tr>
{''.join(gallery_rows)}</table>"""
    (OUT / "gallery.html").write_text(html)
    print(f"\n[out] {OUT/'metrics.json'}  +  {OUT/'gallery.html'}")


if __name__ == "__main__":
    main()
