#!/usr/bin/env python3
"""M1 离线建库:tos://kox-statics/bgm/ → CLAP 向量 → faiss 索引(去均值 + 去重)。

磁盘友好:**逐条流式**——下载一条 → embedding → 立即删除音频。峰值占用 = 1 个文件,
全程不落地整个曲库(满足「不要全部下载」)。embedding 很小(512 float/条),增量落盘可断点续跑。

口径见 docs/BGM-反解-spec.md §3:
  - 库内曲本身是纯乐曲,**不跑 Demucs**(Demucs 只用于视频侧抠 BGM)。
  - 存原始 embedding + 全库质心;faiss 建在「去质心后」的向量上(内积=去均值 cosine)。
  - 按音频内容去重:先按 TOS ETag(MD5)去字节级重复,再按 embedding 近重(cosine>0.9995)兜底。
    category 是软标签,一首可属多类 → metadata 保留 categories 列表。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bgm_common import center, embed_file, load_clap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOSUTIL = ROOT.parent / ".claude" / "skills" / "tos-cli" / "bin" / "tosutil"
BUCKET_PREFIX = "tos://kox-statics/bgm/"
CATEGORIES = ["lyrics_bgm", "normal_bgm", "rhythm_bgm"]
WORK_DIR = ROOT / "assets" / "bgm_work"          # 单条临时落地,用后即删
OUT_DIR = ROOT / "outputs" / "bgm_index"
CACHE = OUT_DIR / "_emb_cache.npz"                # 断点续跑
DUP_THRESH = 0.9995                               # embedding 近重阈值

KEY_RE = re.compile(r"tos://kox-statics/bgm/[^\s].*?\.(?:mp3|m4a|wav|flac)", re.I)
ETAG_RE = re.compile(r'"([0-9a-fA-F]{32}(?:-\d+)?)"')


def tos_ls(category: str) -> str:
    r = subprocess.run(
        [str(TOSUTIL), "ls", f"{BUCKET_PREFIX}{category}/"],
        capture_output=True, text=True, check=True,
    )
    return r.stdout


def inventory() -> list[dict]:
    """解析 tosutil ls,产出 [{url, category, etag}]。不下载任何文件。"""
    inv: list[dict] = []
    for cat in CATEGORIES:
        out = tos_ls(cat)
        cur: dict | None = None
        for line in out.splitlines():
            m = KEY_RE.search(line)
            if m:
                cur = {"url": m.group(0), "category": cat, "etag": None}
                inv.append(cur)
                rest = line[m.end():]
                e = ETAG_RE.search(rest)
                if e:
                    cur["etag"] = e.group(1)
            elif cur is not None and cur["etag"] is None:
                e = ETAG_RE.search(line)
                if e:
                    cur["etag"] = e.group(1)
        print(f"  {cat}: {sum(1 for x in inv if x['category'] == cat)} 条")
    return inv


def dedup_by_etag(inv: list[dict]) -> list[dict]:
    """同 ETag(字节级相同)合并为一条,union categories。无 etag 的保留(交给 embedding 去重)。"""
    by_etag: dict[str, dict] = {}
    out: list[dict] = []
    for it in inv:
        et = it["etag"]
        if et and et in by_etag:
            cats = by_etag[et]["categories"]
            if it["category"] not in cats:
                cats.append(it["category"])
            continue
        rec = {"url": it["url"], "categories": [it["category"]], "etag": et}
        out.append(rec)
        if et:
            by_etag[et] = rec
    return out


def download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [str(TOSUTIL), "cp", url, str(dest.parent) + "/", "-f", "-flat"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  [dl-fail] {url}\n    {r.stdout[-300:]}")
        return False
    return dest.exists()


def stream_embed(records: list[dict], model, processor, device) -> tuple[np.ndarray, list[dict]]:
    """逐条:下载→embedding→删除。增量写缓存,可断点续跑。返回 (emb[N,D], kept_records)。"""
    cache: dict[str, np.ndarray] = {}
    durs: dict[str, float] = {}
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=True)
        cache = {u: v for u, v in zip(z["urls"], z["emb"])}
        durs = {u: float(d) for u, d in zip(z["urls"], z["durs"])}
        print(f"缓存命中 {len(cache)} 条,续跑")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for i, rec in enumerate(records, 1):
        url = rec["url"]
        if url in cache:
            continue
        local = WORK_DIR / Path(url).name
        ok = download(url, local)
        if not ok:
            failed.append(url)
            continue
        vec, dur = embed_file(local, model, processor, device)
        local.unlink(missing_ok=True)
        if vec is None:
            failed.append(url)
            continue
        cache[url] = vec
        durs[url] = dur
        if i % 25 == 0:
            _save_cache(cache, durs)
            print(f"  [{i}/{len(records)}] embedded={len(cache)} failed={len(failed)}")
    _save_cache(cache, durs)
    if failed:
        print(f"跳过 {len(failed)} 条(下载/解码失败):")
        for u in failed[:20]:
            print(f"    {u}")

    kept = [r for r in records if r["url"] in cache]
    emb = np.stack([cache[r["url"]] for r in kept])
    for r in kept:
        r["duration"] = round(durs[r["url"]], 2)
    return emb, kept


def _save_cache(cache: dict, durs: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    urls = list(cache.keys())
    np.savez(
        CACHE,
        urls=np.array(urls, dtype=object),
        emb=np.stack([cache[u] for u in urls]),
        durs=np.array([durs[u] for u in urls], dtype=np.float32),
    )


def dedup_by_embedding(emb: np.ndarray, records: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """embedding 近重(re-encode 后字节不同但听感相同):cosine>阈值的合并,union categories。"""
    sim = emb @ emb.T
    n = len(records)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        for j in range(i + 1, n):
            if keep[j] and sim[i, j] > DUP_THRESH:
                keep[j] = False
                for c in records[j]["categories"]:
                    if c not in records[i]["categories"]:
                        records[i]["categories"].append(c)
    kept_idx = np.where(keep)[0]
    merged = sum(1 for k in keep if not k)
    if merged:
        print(f"embedding 近重合并 {merged} 条(阈值 {DUP_THRESH})")
    return emb[kept_idx], [records[i] for i in kept_idx]


def build(emb: np.ndarray, records: list[dict]) -> None:
    import faiss

    centroid = emb.mean(axis=0).astype(np.float32)
    centered = center(emb, centroid).astype(np.float32)

    index = faiss.IndexFlatIP(centered.shape[1])
    index.add(centered)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(OUT_DIR / "index.faiss"))
    np.save(OUT_DIR / "embeddings.npy", emb.astype(np.float32))   # 原始向量,便于换质心/重建
    np.save(OUT_DIR / "centroid.npy", centroid)
    with (OUT_DIR / "metadata.jsonl").open("w", encoding="utf-8") as f:
        for eid, r in enumerate(records):
            f.write(json.dumps(
                {"embedding_id": eid, "url": r["url"],
                 "categories": r["categories"], "duration": r.get("duration")},
                ensure_ascii=False) + "\n")

    cats = [c for r in records for c in r["categories"]]
    print(f"\n=== 索引建成 ===")
    print(f"  向量 {index.ntotal} 条,dim {centered.shape[1]}")
    print(f"  类别分布(含多类): " + ", ".join(
        f"{c}={cats.count(c)}" for c in CATEGORIES))
    print(f"  产物: {OUT_DIR}/ (index.faiss + embeddings.npy + centroid.npy + metadata.jsonl)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help=">0 时只处理前 N 条(调试)")
    args = ap.parse_args()

    print("=== 1. 清点曲库(仅列举,不下载)===")
    inv = inventory()
    print(f"  原始 {len(inv)} 条")
    records = dedup_by_etag(inv)
    print(f"  ETag 去重后 {len(records)} 条")
    if args.limit:
        records = records[: args.limit]
        print(f"  --limit 截到 {len(records)} 条")

    print("\n=== 2. 流式 embedding(下载→编码→删除)===")
    model, processor, device = load_clap()
    print(f"  device={device}")
    emb, records = stream_embed(records, model, processor, device)
    print(f"  成功 embedding {len(records)} 条")

    print("\n=== 3. embedding 近重去重 ===")
    emb, records = dedup_by_embedding(emb, records)

    print("\n=== 4. 建 faiss 索引 ===")
    build(emb, records)


if __name__ == "__main__":
    main()
