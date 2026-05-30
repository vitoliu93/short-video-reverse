#!/usr/bin/env python3
"""compose_extract — 单视频端到端(第6条能力 compose_):编排 5 反解管线 → 统一反解 JSON + KOX icccut_draft。

口径:**缓存优先**。compose_ 消费各管线已落盘的 outputs/<pfx>/<stem>.json(它们是已 de-risk 的独立 POC),
不自己重算——故正常路径无重复 fx_detect。缺失的管线可 `--run` 委托其独立入口补跑(各自含 detect)。

跑(缓存模式,推荐):
  uv run python scripts/compose_extract.py assets/<video>.mp4
  uv run python scripts/compose_extract.py <stem>
补跑缺失管线(需对应凭据/索引,会较慢/烧额度):
  uv run python scripts/compose_extract.py assets/<video>.mp4 --run fx,narr

出:
  outputs/compose/<stem>.json        统一反解 JSON {shots,subtitles,bgm,transitions,effects,narrative,...}
  outputs/compose/<stem>.draft.json  KOX icccut_draft(${media_N}/${audio_N} 占位)
整稿经兄弟仓 icccut-agents 的 validate_icccut_draft 校验(id 全局唯一 + 串联 + 时间轴)。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_common as cc

ROOT = cc.ROOT
ICC = cc.ICC
OUT = ROOT / "outputs" / "compose"

# 各管线独立入口(--run 委托)
PIPELINE_ENTRY = {"fx": "fx_extract.py", "narr": "narr_extract.py",
                  "bgm": "bgm_extract.py", "font": "font_extract.py"}


def stem_of(arg: str) -> str:
    p = Path(arg)
    return p.stem if p.suffix else p.name


def run_pipeline(pfx: str, video: Path) -> bool:
    """委托独立管线补跑缺失输出。返回是否成功。"""
    entry = ROOT / "scripts" / PIPELINE_ENTRY[pfx]
    print(f"  [run] {pfx}: uv run {entry.name} {video.name} ...", flush=True)
    r = subprocess.run(["uv", "run", str(entry), str(video)], cwd=ROOT)
    return r.returncode == 0


def validate_whole_draft(draft_path: Path) -> tuple[bool, str]:
    """整稿过 icccut-agents validate_icccut_draft(id 唯一 + 串联 + 时间轴)。"""
    r = subprocess.run(
        ["uv", "run", "--directory", str(ICC), "python",
         ".claude/skills/draft-manager/scripts/validate_icccut_draft.py", str(draft_path), "--json"],
        capture_output=True, text=True)
    ok = r.returncode == 0
    summary = (r.stdout.strip().splitlines() or [""])[-1] if r.stdout.strip() else r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""
    return ok, summary


def per_action_validate(draft: dict) -> tuple[int, int, list]:
    """逐条 action 过 validate_action(在 icccut venv 内,经 compose_validate 子进程)。"""
    tmp = OUT / "_validate_tmp.draft.json"
    tmp.write_text(json.dumps(draft, ensure_ascii=False))
    r = subprocess.run(
        ["uv", "run", "--directory", str(ICC), "python", str(ROOT / "scripts" / "compose_validate.py"), str(tmp)],
        capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    out = r.stdout + r.stderr
    fails = [ln for ln in out.splitlines() if ln.strip().startswith("✗")]
    summ = [ln for ln in out.splitlines() if ln.startswith("PASS")]
    npass = nfail = 0
    if summ:
        import re
        m = re.search(r"PASS (\d+) / FAIL (\d+)", summ[-1])
        if m:
            npass, nfail = int(m.group(1)), int(m.group(2))
    return npass, nfail, fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="视频路径或 stem")
    ap.add_argument("--run", default="", help="缺失则补跑的管线,逗号分隔(fx,narr,bgm,font)")
    ap.add_argument("--no-validate", action="store_true", help="跳过整稿校验")
    args = ap.parse_args()

    video = Path(args.video)
    stem = stem_of(args.video)
    run_set = {x.strip() for x in args.run.split(",") if x.strip()}
    print(f"=== compose_extract :: {stem} ===")

    # 1. 编排:缓存优先,缺失且请求重跑则委托
    cached = cc.load_cached(stem)
    for pfx in cc.PIPELINES:
        if cached[pfx] is None and pfx in run_set:
            if not video.exists():
                print(f"  [skip-run] {pfx}: 视频文件不存在 {video}")
                continue
            if run_pipeline(pfx, video):
                p = ROOT / "outputs" / pfx / f"{stem}.json"
                cached[pfx] = json.loads(p.read_text()) if p.is_file() else None
    present = {k: cached[k] is not None for k in cc.PIPELINES}
    print(f"  pipelines present: {present}")
    if not any(present.values()):
        print("  ✗ 无任何反解输出(先跑各管线或 --run)。"); sys.exit(1)

    # 2. 合并 + 映射
    unified, draft = cc.build_draft_from_cached(stem, cached)
    acts = [a for blk in draft["script"] for a in blk["actions"]]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{stem}.json").write_text(json.dumps(unified, ensure_ascii=False, indent=2))
    dpath = OUT / f"{stem}.draft.json"
    dpath.write_text(json.dumps(draft, ensure_ascii=False, indent=2))

    # 3. 保真度摘要
    from collections import Counter
    print(f"  unified: {len(unified['shots'])} shots / {len(unified['transitions'])} trans / "
          f"{len(unified['effects'])} effects / subs={len(unified['subtitles'])} / bgm={unified['bgm'] is not None}")
    print(f"  draft: {dict(Counter(a['action_type'] for a in acts))} (total {len(acts)} actions)")
    if draft.get("_unmapped"):
        print(f"  unmapped({len(draft['_unmapped'])}): " +
              ", ".join(f"{u['kind']}:{u['tag']}" for u in draft["_unmapped"]))

    # 4. 校验
    if not args.no_validate:
        np_, nf_, fails = per_action_validate(draft)
        print(f"  per-action validate_action: PASS {np_} / FAIL {nf_}")
        for f in fails:
            print(f"    {f}")
        ok, summ = validate_whole_draft(dpath)
        print(f"  whole-draft validate_icccut_draft: {'✅ 通过' if ok else '❌ 失败'}  {summ}")
        if nf_ or not ok:
            print(f"  → {dpath}"); sys.exit(1)

    print(f"  ✅ → {OUT}/{stem}.json + {stem}.draft.json")


if __name__ == "__main__":
    main()
