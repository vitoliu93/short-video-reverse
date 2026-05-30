#!/usr/bin/env python3
"""C1 自测:① 映射表每个非 None 值都过 icccut 真实校验  ② 用真模块从 Lotus 缓存搓 draft 全过(C0 回归)。

**须在 icccut venv 内跑**:
  uv run --directory /Users/liujiaxi/codebase/icc/kox-base/icccut-agents \
      python <svr>/scripts/compose_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SVR = Path(__file__).resolve().parent          # <svr>/scripts
sys.path.insert(0, str(SVR))
ICC = Path("/Users/liujiaxi/codebase/icc/kox-base/icccut-agents")
sys.path.insert(0, str(ICC / ".claude/skills/draft-manager/scripts"))

import compose_common as cc
from validate_action import validate_action

STEM = "Lotus_MY26_Combined-15s_16x9_CLEAN_Audio-250207_v016"
fails = []


def _mini(action_type, params):
    return {"type": "action", "action_type": action_type, "id": "x", "index": 1,
            "params": {**params, "draft_id": "d", "width": 1080, "height": 1920}}


def check(label, action_type, params):
    errs = validate_action(_mini(action_type, params), action_type)
    if errs:
        fails.append((label, errs))
        print(f"  ✗ {label}: {errs}")


print("=== 1. 映射表值过真实枚举校验 ===")
for tag, jy in cc.FX_TRANS_TO_JY.items():
    if jy:
        check(f"trans {tag}->{jy}", "add_video",
              {"video_url": "${media_1}", "start": 0, "end": 3, "target_start": 0,
               "transition": jy, "track_name": "video", "track_render_index": 0})
for tag, (jy, route) in cc.FX_EFFECT_TO_JY.items():
    if jy and route == "scene":
        check(f"effect {tag}->{jy}", "add_effect",
              {"effect_type": jy, "effect_category": "scene", "params": [],
               "start": 1, "end": 2, "track_name": "effects", "track_render_index": 8000})
for tag, jy in cc.FONT_ANIM_TO_JY.items():
    if jy:
        check(f"anim {tag}->{jy}", "add_text",
              {"text": "x", "start": 0, "end": 1, "intro_animation": jy,
               "track_name": "subtitle", "track_render_index": 15000})
print(f"  映射表: {sum(1 for v in cc.FX_TRANS_TO_JY.values() if v)} trans + "
      f"{sum(1 for v,_ in cc.FX_EFFECT_TO_JY.values() if v)} effect + "
      f"{sum(1 for v in cc.FONT_ANIM_TO_JY.values() if v)} anim 值校验完")

print("\n=== 2. 换算器单测 ===")
tx, ty = cc.bbox_to_transform([0.30, 0.80, 0.40, 0.08])
assert tx == 0.0 and abs(ty - (-0.68)) < 1e-6, (tx, ty)
assert cc.bbox_to_transform([0.0, 0.0, 1.0, 1.0]) == (0.0, 0.0)
assert abs(cc.size_rel_to_font_size(0.08, 1080) - 16.6) < 0.1
assert cc.norm_font("SourceHanSansCN-Bold") == "SourceHanSansCN_Bold"
assert cc.map_transition("hard-cut") is None and cc.map_transition("glitch") == "信号故障"
assert cc.map_effect("vignette") == (None, "scene") and cc.map_effect("shake") == ("回弹摇摆", "scene")
print("  bbox_to_transform / size_rel / norm_font / map_* ✓")

print("\n=== 3. Lotus 端到端回归(真模块 build_draft_from_cached → 全过校验)===")
cached = cc.load_cached(STEM)
present = {k: cached[k] is not None for k in cc.PIPELINES}
print(f"  cached present: {present}")
unified, draft = cc.build_draft_from_cached(STEM, cached)
acts = [a for blk in draft["script"] for a in blk["actions"]]
from collections import Counter
print(f"  unified: {len(unified['shots'])} shots / {len(unified['transitions'])} trans / "
      f"{len(unified['effects'])} effects / bgm={unified['bgm'] is not None} / subs={len(unified['subtitles'])}")
print(f"  draft action_types: {dict(Counter(a['action_type'] for a in acts))}")
print(f"  unmapped: {draft.get('_unmapped', [])}")
npass = 0
for a in acts:
    errs = validate_action(a, a["action_type"])
    if errs:
        fails.append((f"draft {a['action_type']} {a['id']}", errs))
        print(f"  ✗ {a['action_type']} -> {errs}")
    else:
        npass += 1
# id 唯一 / index 递增
ids = [a["id"] for a in acts]
assert len(set(ids)) == len(ids), "duplicate action ids"
assert [a["index"] for a in acts] == list(range(1, len(acts) + 1)), "index not 1..N"
print(f"  draft 校验: PASS {npass}/{len(acts)}; id 唯一 ✓; index 递增 ✓")

print("\n=== 4. 转场分配单射(C3 回归:无重复挂 / 无漏挂)===")
present_nc = [t for t in unified["transitions"]
              if t.get("present") and t["type"] not in ("hard-cut", "none")]
mapped = [a["params"]["transition"] for a in acts
          if a["action_type"] == "add_video" and "transition" in a["params"]]
exp = Counter(cc.map_transition(t["type"]) for t in present_nc if cc.map_transition(t["type"]))
got = Counter(mapped)
# Lotus 每个 present 非硬切转场都落在某镜头 out 点附近 → 应恰好 1:1(单射),
# 旧 transition_for_shot 会让一个转场挂到两个相邻短镜头(重复)、宽转场漏挂(spec §12)。
assert exp == got, f"转场分配非单射: 反解信号={dict(exp)} ≠ draft={dict(got)}"
print(f"  present 非硬切={len(present_nc)} → mapped={len(mapped)} 单射 ✓; 分布={dict(got)}")

# 写盘
out = cc.ROOT / "outputs" / "compose"
out.mkdir(parents=True, exist_ok=True)
import json as _j
(out / f"{STEM}.json").write_text(_j.dumps(unified, ensure_ascii=False, indent=2))
(out / f"{STEM}.draft.json").write_text(_j.dumps(draft, ensure_ascii=False, indent=2))
print(f"  → {out}/{STEM}.json + .draft.json")

print(f"\n{'❌ FAILS: ' + str(len(fails)) if fails else '✅ C1 SMOKE ALL PASS'}")
sys.exit(1 if fails else 0)
