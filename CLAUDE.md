# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`short-video-reverse` — research + POC code that **reverse-engineers a short video into structured JSON**. It is one sub-project of the `kox-base` monorepo (KOX, an AI clipping studio); see the parent `../CLAUDE.md` for monorepo conventions (aliases, gitee-ent / volcengine-supabase MCP, etc.).

This is **not a production pipeline**. It is a set of independent "reverse" capabilities, each de-risked as a standalone POC. Output is structured JSON written to `outputs/<pipeline>/`, intended to feed KOX eval Gold Cases and `add_text` parameter recovery — not yet integrated into any end-to-end orchestration.

Four pipelines, each a `scripts/<pfx>_*.py` family writing to `outputs/<pfx>/`. They share one venv (see below):

| Pipeline | Prefix | Job | Entry → output |
|-|-|-|-|
| **ARC API** | `test_arc_*` | Smoke-test Tencent ARC-Hunyuan-Video-7B hosted API (video understanding) | `test_arc_api.py` → `outputs/arc/` |
| **BGM reverse** | `bgm_*` | Audio → `bgm{}` JSON: Demucs separate → CLAP tags + FAISS retrieval → librosa DSP | `bgm_extract.py` → `outputs/bgm/` |
| **Font/style** | `font_*` | Video text region → `texts[]` JSON: ffmpeg frames → RapidOCR → closed-set font match (NCC) + 4-D style | `font_extract.py` → `outputs/font/` |
| **Transition/FX** | `fx_*` | Video → `transitions[]`+`effects[]` JSON: TransNetV2⊕ffmpeg locate → VLM (Ark `doubao-seed-2.0-pro`) describe + closed-set tag + 剪映 category | `fx_extract.py` → `outputs/fx/` |

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
uv run scripts/fx_detect.py <video> [--threshold 0.5]      # localization only (VLM-free, fully deterministic)
uv run scripts/fx_describe.py <video> <t_start> <t_end>    # single-window VLM debug
```

There is no test runner, linter, or build step — verification is done by running the smoke/eval scripts against synthetic or real samples and reading the metrics they print / write.

> **`transformers` is pinned to `4.46.3`** — `scripts/bgm_common.py` relies on the CLAP `get_audio_features` projection behavior of that version. transformers 5.x changes it; don't bump without re-validating BGM. (Note: older `docs/.../preflight.md` say to invoke `.venv-font/bin/python` directly — that was a pre-consolidation workaround for an empty-`.venv` trap; the single-venv `uv run` above supersedes it.)

## Code structure (per pipeline)

Each pipeline follows the same layout, so learning one transfers to the others:

- **`<pfx>_common.py`** — the shared *contract / 口径*: model loading, normalization, the similarity metric. When changing how a pipeline measures things, change it here. (`bgm_common` = CLAP load + embed; `font_common` = render + binarize/normalize + NCC/IoU.)
- **`<pfx>_build_index.py`** — offline: build the FAISS / reference index from a TOS bucket. Both use **streaming build** (download one item → process → delete immediately) so peak disk ≈ a single file, with resume-on-restart. The 14 GB font library / BGM library never fully lands on disk. **`fx_` has no `build_index`** — it's a VLM description task, not closed-set retrieval; its "closed set" lives in the prompt's tag taxonomy (`fx_common.TRANSITION_TAGS`), not in a FAISS index.
- **`<pfx>_extract.py`** — the single-video end-to-end entry that consumes the common module + index and writes the output JSON. This is the one to read to understand a pipeline's full data flow.
- Other `<pfx>_*.py` are stage modules (`bgm_separate`/`bgm_dsp`; `font_ocr`/`font_match`/`font_style`/`font_synth`; `fx_detect` = TransNetV2⊕ffmpeg localization, `fx_describe` = per-window VLM call) or smoke/eval harnesses.

External data lives in TOS, pulled via the `tos-cli` skill: `tos://kox-statics/bgm/` and `tos://kox-statics/fonts_effect/` (~2660 objects, 14 GB, ~1300+ fonts). This repo's `.env` holds only `ARC_TOKEN` (ARC video API; **not** a general image-VLM credential). The `fx_` VLM credential is `VOLC_ARK_API_KEY`, read from the sibling **`../icccut-agents/.env`** (`fx_common.load_creds()`), not from this repo.

## Methodology & where decisions live

Work follows a **de-risk-first milestone** rhythm: knock out the biggest unknown first, then foundation, then full chain, then eval+report (BGM = M0→M3, Font = F0→F3, Transition/FX = X0→X3). Each effort is a `dev-plan` materialized under **`docs/plan/<date>-<slug>/`** (goal / spec / preflight / todo / exploration / review).

**Before touching a pipeline, read its spec** — `spec.md`'s numbered sections carry the verified milestone results, the rationale, and honest known-limitations. `docs/BGM-反解-术语与流水线.md` explains the BGM terminology/data-flow; `docs/plan/2026-05-29-font-style-recognition/spec.md` is the font record; `docs/plan/2026-05-30-transition-fx-reverse/spec.md` is the transition/FX record (§9–§12 = X0→X3 results).

Settled design decisions (don't re-litigate without new evidence):
- **Font = closed-set render-and-compare** (we own every TTF), similarity = **NCC, no training**. Single-frame top-1 is noisy on real抖音 video → aggregate by **video-level voting**. **DINOv2 was tried and rejected** (worse than NCC on low-res/degraded frames — spec §12).
- **BGM** modules B (CLAP retrieval) and C (librosa DSP) both consume **only the Demucs-separated `music` stem**, never the raw mix.
- Font weight is read from the *matched* font's clean render, not from degraded pixels; fill color is sampled from the distance-transform core, not Otsu minority ink (color-polarity fix, spec §12).
- **Transition/FX = VLM description, not retrieval.** Localization (`fx_detect`: TransNetV2⊕ffmpeg) is **fully deterministic**; the VLM `type` label is **not** (Ark/doubao drifts run-to-run even at `temperature=0`, server-side token nondeterminism) → for a reliable `type`, take **k=3 majority vote** (spec §11–§12). Backend is pinned to **direct Ark `/api/coding` + `doubao-seed-2.0-pro`** (`VOLC_ARK_API_KEY`); the ICC-Router `agent-vision` alias was rejected — it load-balances to nondeterministic backends. Recall blind spot = low-content-change same-framing micro-cuts (spec §12).

## macOS gotcha

`torch` and `faiss` each link their own libomp → `OMP Error #15` on import. Scripts that import both set `os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")` **before** importing torch/faiss. Keep that line first when adding such a script.
