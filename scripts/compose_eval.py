#!/usr/bin/env python3
"""compose_eval — 映射保真度评测(C3):各模态反解信号「落进合法 draft 参数 / 丢失 / 为何」。

读 outputs/compose/<stem>.json(统一反解) + .draft.json(KOX draft),逐样本 + 汇总。
跑:  uv run python scripts/compose_eval.py [stem ...]   (省略=评测 outputs/compose 下全部)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "compose"
HARDCUT = {"hard-cut", "none"}


def eval_one(stem: str) -> dict:
    u = json.loads((OUT / f"{stem}.json").read_text())
    d = json.loads((OUT / f"{stem}.draft.json").read_text())
    acts = [a for blk in d["script"] for a in blk["actions"]]
    by = Counter(a["action_type"] for a in acts)
    trans = u["transitions"]
    cut = sum(1 for t in trans if t["type"] in HARDCUT)
    mapped_t = sum(1 for a in acts if a["action_type"] == "add_video" and "transition" in a["params"])
    unmapped = d.get("_unmapped") or []
    eff_tags = sum(len(e.get("types", [])) for e in u["effects"])
    return {
        "stem": stem, "shots": len(u["shots"]), "add_video": by.get("add_video", 0),
        "trans_present": len(trans), "trans_cut": cut, "trans_mapped": mapped_t,
        "trans_unmapped": sum(1 for x in unmapped if x["kind"] == "transition"),
        "eff_tags": eff_tags, "add_effect": by.get("add_effect", 0), "add_filter": by.get("add_filter", 0),
        "eff_unmapped": sum(1 for x in unmapped if x["kind"] == "effect"),
        "subs": len(u["subtitles"]), "add_text": by.get("add_text", 0),
        "bgm": bool(u["bgm"]), "add_audio": by.get("add_audio", 0),
        "narrative": bool(u.get("narrative")), "n_actions": len(acts),
    }


def main():
    stems = sys.argv[1:] or sorted({p.name[:-len(".draft.json")] for p in OUT.glob("*.draft.json")
                                    if not p.name.startswith("_")})
    rows = [eval_one(s) for s in stems]
    print(f"{'sample':12} {'shot→vid':9} {'trans cut/map/unmap':19} {'eff tags→eff/unmap':18} {'sub→txt':8} bgm narr")
    for r in rows:
        print(f"{r['stem'][:12]:12} {r['shots']:3}→{r['add_video']:<4} "
              f"{r['trans_cut']:2}/{r['trans_mapped']:2}/{r['trans_unmapped']:<2}{'':11} "
              f"{r['eff_tags']:2}→{r['add_effect']:2}/{r['eff_unmapped']:<2}{'':10} "
              f"{r['subs']:2}→{r['add_text']:<3} {'Y' if r['bgm'] else '-'}/{r['add_audio']}  {'Y' if r['narrative'] else '-'}")
    g = Counter()
    for r in rows:
        for k in ("shots", "add_video", "trans_present", "trans_cut", "trans_mapped", "trans_unmapped",
                  "eff_tags", "add_effect", "eff_unmapped", "subs", "add_text", "add_audio"):
            g[k] += r[k]
        g["bgm"] += int(r["bgm"]); g["narr"] += int(r["narrative"])
    n = len(rows)
    print(f"\n=== AGGREGATE ({n} samples) ===")
    print(f"shots→add_video: {g['shots']}→{g['add_video']} (1:1 {g['shots']==g['add_video']})")
    nonctut = g["trans_present"] - g["trans_cut"]
    print(f"transitions: {g['trans_present']} present = {g['trans_cut']} 硬切(相邻直切) + "
          f"{g['trans_mapped']} 映射 + {g['trans_unmapped']} unmapped  "
          f"→ 非硬切映射率 {g['trans_mapped']}/{nonctut}")
    print(f"effects: {g['eff_tags']} tags → {g['add_effect']} add_effect + {g['eff_unmapped']} unmapped  "
          f"→ 落地率 {g['add_effect']}/{g['eff_tags']}")
    print(f"bgm→add_audio: {g['bgm']}/{n} have bgm, {g['add_audio']} audio actions")
    print(f"subtitles→add_text: {g['subs']}→{g['add_text']} (font 未在样本上跑)")
    print(f"narrative carried(meta): {g['narr']}/{n}")


if __name__ == "__main__":
    main()
