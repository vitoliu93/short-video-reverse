# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`short-video-reverse` — research + POC code that **reverse-engineers a short video into structured JSON**. It is one sub-project of the `kox-base` monorepo (KOX, an AI clipping studio); see the parent `../CLAUDE.md` for monorepo conventions (aliases, gitee-ent / volcengine-supabase MCP, etc.).

This is **not a production pipeline**. It is a set of independent "reverse" capabilities, each de-risked as a standalone POC. Output is structured JSON written to `outputs/<pipeline>/`, intended to feed KOX eval Gold Cases and `add_text` parameter recovery. **`compose_` is the orchestration+mapping layer** that stitches the five reverse outputs into one unified JSON and maps it to a KOX `icccut_draft.json` (the end-to-end chain — POC, cache-driven demo).

**Five reverse pipelines + one compose layer**, each a `scripts/<pfx>_*.py` family writing to `outputs/<pfx>/`. They share one venv (see below):

| Pipeline | Prefix | Job | Entry → output |
|-|-|-|-|
| **ARC API** | `test_arc_*` | Smoke-test Tencent ARC-Hunyuan-Video-7B hosted API (video understanding) | `test_arc_api.py` → `outputs/arc/` |
| **BGM reverse** | `bgm_*` | Audio → `bgm{}` JSON: Demucs separate → CLAP tags + FAISS retrieval → librosa DSP | `bgm_extract.py` → `outputs/bgm/` |
| **Font/style** | `font_*` | Video text region → `texts[]` JSON: ffmpeg frames → RapidOCR → closed-set font match (NCC) + 4-D style | `font_extract.py` → `outputs/font/` |
| **Transition/FX** | `fx_*` | Video → `transitions[]`+`effects[]` JSON: TransNetV2⊕ffmpeg locate → VLM (Ark `doubao-seed-2.0-pro`) describe + closed-set tag + 剪映 category | `fx_extract.py` → `outputs/fx/` |
| **Narrative** | `narr_*` | Video → `narrative{}` JSON: fx_detect shots+pacing (deterministic) ⊕ ARC-Hunyuan multi-task (Summary/Segment/QA/Grounding) → doubao synth into closed-set hook/structure/acts/emotion | `narr_extract.py` → `outputs/narr/` |
| **Compose** | `compose_*` | The 5 reverse outputs → unified reverse JSON `{shots,subtitles,bgm,transitions,effects,narrative}` → **map to KOX `icccut_draft.json` add_* actions** (validated against the real icccut-agents validator). The 6th capability: reverse→draft, the chain not a 6th reverse | `compose_extract.py` → `outputs/compose/<stem>.json` + `.draft.json` |

## Running scripts — read this first

All three pipelines share **one `uv`-managed venv**. Dependencies live in `pyproject.toml` (`[project.dependencies]`) and are pinned by the committed `uv.lock`. Standard uv workflow, nothing custom:

- **Set up / sync the env**: `uv sync` (creates `.venv` at Python 3.12 with the exact locked versions).
- **Run any script** (plain `uv run`, no flags): `uv run scripts/bgm_extract.py <video>`.
- **Add a dependency**: `uv add <pkg>` (updates `pyproject.toml` + `uv.lock` together).

> The repo is a set of scripts, not a package (`[tool.uv] package = false`), so `uv run` installs only the deps, never tries to build the project. **Commit `uv.lock`** — the global git ignore has `*.lock`, so `.gitignore` re-includes it via `!uv.lock`.

Common run commands (all from repo root):

```bash
uv sync                                                   # one-time / after pulling dep changes

# ARC API smoke (needs ARC_TOKEN in .env)
uv run scripts/test_arc_api.py <video> --task Summary

# BGM: build the retrieval index once, then extract per video
uv run scripts/bgm_build_index.py
uv run scripts/bgm_extract.py <video>

# Font: build index once, extract per video, eval/visualize
uv run scripts/font_build_index.py
uv run scripts/font_extract.py <video> [--fps 4] [--max-fonts N]
uv run scripts/font_match_smoke.py [--limit N]      # F0 synthetic-set accuracy
uv run scripts/font_eval_gallery.py <video> <json>  # visual sanity gallery

# Transition/FX: NO index (VLM-based, not retrieval). Needs VOLC_ARK_API_KEY in ../icccut-agents/.env
uv run scripts/fx_extract.py <video>                       # end-to-end → outputs/fx/<stem>.json
uv run scripts/fx_extract.py <video> --k 3                 # k-vote the drifting transition `type` (frames sampled once; only the VLM call repeats k×)
uv run scripts/fx_detect.py <video> [--threshold 0.5]      # localization only (VLM-free, fully deterministic)
uv run scripts/fx_describe.py <video> <t_start> <t_end>    # single-window VLM debug

# Narrative: NO index. Needs BOTH ARC_TOKEN (this repo .env) AND VOLC_ARK_API_KEY (../icccut-agents/.env)
uv run scripts/narr_extract.py <video>                     # end-to-end → outputs/narr/<stem>.json
uv run scripts/narr_extract.py <video> --k 3               # k-vote the drifting `structure` (ARC stays cached; only doubao synth repeats k×)
uv run scripts/narr_extract.py <video> --tasks Summary,Segment,QA,Grounding  # pick ARC task subset
uv run scripts/narr_extract.py <video> --no-synth          # skeleton+ARC only (skip doubao synth)
# ARC calls are disk-cached to outputs/arc/<stem>_<task>.json — re-runs don't burn the ~100-call free quota.
# --no-cache forces a re-fetch (spends quota).

# Compose: NO index, NO model — pure orchestration + mapping. Cache-first (reads outputs/{fx,font,narr,bgm}/<stem>.json).
uv run scripts/compose_extract.py <video>                  # cache-first → outputs/compose/<stem>.json + .draft.json
uv run scripts/compose_extract.py <video> --run            # run any missing reverse pipeline first (burns VLM/ARC quota; font/bgm need built indexes)
uv run scripts/compose_extract.py <video> --no-validate    # skip the icccut validator round-trip
uv run scripts/compose_eval.py [stem ...]                  # fidelity report: each modality landed/lost/why (defaults to all outputs/compose)
# Draft validation reuses the REAL icccut-agents validators (must run in their venv), e.g.:
#   uv run --directory ../icccut-agents python <wt>/scripts/compose_smoke.py        # C1 self-test: mapping values + Lotus regression + transition-injectivity guard
#   uv run --directory ../icccut-agents python .../validate_icccut_draft.py <draft.json> --json   # whole-draft (id-unique + same-track overlap + canvas gaps)
```

There is no test runner, linter, or build step — verification is done by running the smoke/eval scripts against synthetic or real samples and reading the metrics they print / write.

> **`transformers` is pinned to `4.46.3`** — `scripts/bgm_common.py` relies on the CLAP `get_audio_features` projection behavior of that version. transformers 5.x changes it; don't bump without re-validating BGM. (Note: older `docs/.../preflight.md` say to invoke `.venv-font/bin/python` directly — that was a pre-consolidation workaround for an empty-`.venv` trap; the single-venv `uv run` above supersedes it.)

## Code structure (per pipeline)

Each pipeline follows the same layout, so learning one transfers to the others:

- **`<pfx>_common.py`** — the shared *contract / 口径*: model loading, normalization, the similarity metric. When changing how a pipeline measures things, change it here. (`bgm_common` = CLAP load + embed; `font_common` = render + binarize/normalize + NCC/IoU.)
- **`<pfx>_build_index.py`** — offline: build the FAISS / reference index from a TOS bucket. Both use **streaming build** (download one item → process → delete immediately) so peak disk ≈ a single file, with resume-on-restart. The 14 GB font library / BGM library never fully lands on disk. **`fx_` has no `build_index`** — it's a VLM description task, not closed-set retrieval; its "closed set" lives in the prompt's tag taxonomy (`fx_common.TRANSITION_TAGS`), not in a FAISS index.
- **`<pfx>_extract.py`** — the single-video end-to-end entry that consumes the common module + index and writes the output JSON. This is the one to read to understand a pipeline's full data flow.
- Other `<pfx>_*.py` are stage modules (`bgm_separate`/`bgm_dsp`; `font_ocr`/`font_match`/`font_style`/`font_synth`; `fx_detect` = TransNetV2⊕ffmpeg localization, `fx_describe` = per-window VLM call) or smoke/eval harnesses.

External data lives in TOS, pulled via the `tos-cli` skill: `tos://kox-statics/bgm/` and `tos://kox-statics/fonts_effect/` (~2660 objects, 14 GB, ~1300+ fonts). This repo's `.env` holds only `ARC_TOKEN` (ARC video API; **not** a general image-VLM credential). The `fx_` VLM credential is `VOLC_ARK_API_KEY`, read from the sibling **`../icccut-agents/.env`** (`fx_common.load_creds()`), not from this repo. **`narr_` needs both**: `ARC_TOKEN` (this repo `.env`, for ARC understanding) and `VOLC_ARK_API_KEY` (sibling, for the doubao synth layer it reuses from `fx_common`).

## Methodology & where decisions live

Work follows a **de-risk-first milestone** rhythm: knock out the biggest unknown first, then foundation, then full chain, then eval+report (BGM = M0→M3, Font = F0→F3, Transition/FX = X0→X3, Narrative = N0→N3). Each effort is a `dev-plan` materialized under **`docs/plan/<date>-<slug>/`** (goal / spec / preflight / todo / exploration / review).

**Before touching a pipeline, read its spec** — `spec.md`'s numbered sections carry the verified milestone results, the rationale, and honest known-limitations. `docs/BGM-反解-术语与流水线.md` explains the BGM terminology/data-flow; `docs/plan/2026-05-29-font-style-recognition/spec.md` is the font record; `docs/plan/2026-05-30-transition-fx-reverse/spec.md` is the transition/FX record (§9–§12 = X0→X3 results); `docs/plan/2026-05-30-narrative-structure-reverse/spec.md` is the narrative record (§9–§11 = N0→N3 results); `docs/plan/2026-05-30-compose-reverse-to-draft/spec.md` is the compose record (§9–§12 = C0→C3 results: mapping contract, builder, full chain, fidelity); `docs/plan/2026-05-30-reverse-fidelity-enhance/spec.md` is the fidelity-enhance record (Results § = measured transition_duration, k-vote for drifting type/structure, font real-video run + font-face gate).

Settled design decisions (don't re-litigate without new evidence):
- **Font = closed-set render-and-compare** (we own every TTF), similarity = **NCC, no training**. Single-frame top-1 is noisy on real抖音 video → aggregate by **video-level voting**. **DINOv2 was tried and rejected** (worse than NCC on low-res/degraded frames — spec §12).
- **BGM** modules B (CLAP retrieval) and C (librosa DSP) both consume **only the Demucs-separated `music` stem**, never the raw mix.
- Font weight is read from the *matched* font's clean render, not from degraded pixels; fill color is sampled from the distance-transform core, not Otsu minority ink (color-polarity fix, spec §12).
- **Transition/FX = VLM description, not retrieval.** Localization (`fx_detect`: TransNetV2⊕ffmpeg) is **fully deterministic**; the VLM `type` label is **not** (Ark/doubao drifts run-to-run even at `temperature=0`, server-side token nondeterminism) → for a reliable `type`, take **k=3 majority vote** (spec §11–§12). Backend is pinned to **direct Ark `/api/coding` + `doubao-seed-2.0-pro`** (`VOLC_ARK_API_KEY`); the ICC-Router `agent-vision` alias was rejected — it load-balances to nondeterministic backends. Recall blind spot = low-content-change same-framing micro-cuts (spec §12).
- **Narrative = three-layer AVI (deterministic skeleton + ARC semantics + doubao synth).** Shots/pacing come from `fx_detect` (deterministic — **never let the VLM invent timestamps**); narrative *meaning* comes from ARC-Hunyuan's hosted multi-task API (Summary/Segment/QA/Grounding); the closed-set `hook_type`/`structure`/`acts` JSON is synthesized by doubao from that evidence. **Don't put the narrative framework into the ARC prompt** — an earlier QA prompt that listed "铺垫/冲突/反转/结尾" biased ARC into parroting it and polluted the `structure` label (spec §11.2 fix: neutral prompt). doubao's high-level categorical labels (esp. `structure`) **drift run-to-run** like fx_'s `type` → use k-vote if you need a stable `structure` (not done in the POC; `hook_type`/`acts` are comparatively stable). ARC calls are **disk-cached** to `outputs/arc/` (free quota ~100). `pacing_profile` = edit rhythm (deterministic), **≠ narrative pacing** — single-shot photo-album videos get acts from ARC's *semantic* segments, not cuts (spec §11.5).
- **Compose = orchestrate + map, validate against the REAL icccut validator (don't re-implement the schema).** The mapping contract lives in `compose_common.py`: closed-set tables (`FX_TRANS_TO_JY` 16 / `FX_EFFECT_TO_JY` 12 / `FONT_ANIM_TO_JY` 4) + converters (bbox→transform_x/y, size_rel→font_size, time in seconds). **The valid 剪映 enum set = the icccut-agents `add-*/references/*.md` subset, NOT the full pyJianYingDraft 900+ enum** — many real enum members (抖动/漏光/暗角/故障定格) are absent from that subset and must NOT be used (C0 learning). What can't be faithfully mapped (vignette/freeze-frame/color-filter/speed-ramp) is recorded as an honest `_unmapped` entry, never force-fit. **Cross-action constraints are the builder's job, not the per-action validator's**: same-track time overlap → `DraftBuilder._alloc_lane` lane allocation (C2 fix); transition↔shot must be **injective** → `assign_transitions` argmin+consume, NOT per-shot nearest-search which double-claims/drops (spec §12.1a fix). Media is always a `${media_N}` placeholder (we reverse from pixels, no source files — the draft is a structure template for eval-gold/复刻, not a finished render). The demo runs **cache-first**; `--run` re-invokes the standalone pipelines but burns VLM/ARC quota. compose_ is **read-only across repos** — it imports icccut's validator but never writes into `../icccut-agents`, and does not export 剪映工程 / cloud-render (out of scope).
- **Fidelity enhancements (reverse-fidelity-enhance plan, spec Results §):** (1) **transition_duration** = the measured fx window `t_end−t_start` (clamped ≤0.8× shot), not a flat 0.5. (2) **Drifting categorical labels get k-vote** — `fx_extract --k`/`narr_extract --k` majority-vote the transition `type` / narrative `structure`; frames/ARC aren't re-sampled, only the VLM/doubao call repeats. **Honest finding: per-call drift at temp=0 is small (within-run votes ~unanimous); the dominant drift is cross-run/session**, which within-run k-vote stabilizes-per-run but doesn't eliminate. (3) **font on real video works** — pull the ~14 GB lib (`tos://kox-statics/fonts_effect/` → `assets/fonts/`, exclude `*.png`, **quote the glob** or zsh eats it), `font_build_index` (~1326 fonts), `font_extract`. The text/position/color/size/stroke/shadow/animation are OCR+pixel-derived (library-independent); only the font-FACE depends on the library. **font-face is gated**: emitted only if the matched name is in the 剪映 `Font_type` closed-set (`scripts/compose_valid_fonts.txt`, 798) AND `score ≥ FONT_MATCH_MIN` (0.6) — real 抖音 NCC scores run low (renderer gap, 剪映≠Pillow; font §F3 median 0.53), so a low-score match is likely wrong → omit + `_unmapped`, default face (≈6% emit rate, conservative for Gold-Case correctness). Single-frame OCR (`first==last`) → zero-duration add_text (icccut rejects) → `MIN_SUB_DUR` 0.5s floor.

## macOS gotcha

`torch` and `faiss` each link their own libomp → `OMP Error #15` on import. Scripts that import both set `os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")` **before** importing torch/faiss. Keep that line first when adding such a script.
