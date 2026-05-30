# Todo: 反解保真度增强 — #2 + #1

## Current State  ← update this constantly; it is the resume cursor
- **Phase**: E3（#1 font 真跑）等 font pull；E1 ✅ E2 ✅
- **Status**: in_progress — font pull(bu0qzjyi8) 1178/2660≈7GB 仍跑；E1/E2 完成并验证
- **Branch**: dev-plan-2026-05-30-reverse-fidelity-enhance（基于 main=1d4b78b）
- **Last done**: **E2 ✅** k 投票：fx `type`/narr `structure` 加 `--k`。fx k=3 Lotus 重跑(present 非硬切 8→9，全可映射)，narr k=3 全 5 样本(kid 的 structure 漂移 [chrono,chrono,hook-proof-cta]→多数 chrono 被收敛)。重跑 compose 5 稿全过校验+smoke(单射 9→9)。**发现**：单跑内 3 票多数一致(per-call 抖动小)，主漂移是跨 run/session 级(k1 baseline vs k3 多窗不同)→ within-run k 投票稳单跑、压 per-call flip，但不能全消跨会话漂移(诚实记 §结果块)
- **Next**: 提交 E1+E2 代码 → 等 font pull 完 → build_index → font_extract ×≥3 → 重跑 compose 填 subtitles
- **Blockers**: E3 待 font pull（~半程）

## Phases

### E1 — #2a 真转场时长  [in_progress]
- [ ] `compose_common.py:192` 改读 `tr.t_end-tr.t_start`，缺失退 DEFAULT_TRANS_DUR，仍 min(shot.dur*0.8)
- [ ] 重生 5 稿（build_draft_from_cached）+ compose_smoke（icccut venv）
- **Acceptance**: 转场 transition_duration 来自实测窗宽（Lotus 8 转场各异、非全 0.5）；5 稿整稿全过校验；smoke 全过
- **Verify**: 打印 Lotus 各转场 dur + `validate_icccut_draft` ×5 + compose_smoke → **Result**: pending

### E2 — #2b k 投票稳标签  [todo]
- [ ] `fx_describe.describe_transition(k=1)` k 次投 `type`；`fx_extract --k`
- [ ] `narr_common.synth_narrative(k=1)` k 次投 `structure`(+hook_type)；`narr_extract --k`
- [ ] source 凭据；fx k=3 重跑（优先 Lotus，有软转场）+ narr k=3 重跑（全样本，便宜）→ 重生缓存
- [ ] 重跑 compose 吃新缓存 → 重生稿
- **Acceptance**: 代码可配 --k；Lotus 重跑 type/structure 标签稳定（同 k 投票两跑一致或多数稳）；稿仍过校验
- **Verify**: fx/narr --k=3 跑通 + 标签对比 + validate ×5 → **Result**: pending

### E3 — #1 font 真跑  [todo, 待 pull]
- [ ] 等 font pull 完成（bu0qzjyi8）→ 校验 obj 数/大小
- [ ] `font_build_index.py` → manifest.jsonl
- [ ] `font_extract.py` ×≥3 样本（含 Lotus）→ outputs/font/<stem>.json
- [ ] 重跑 `compose_extract.py` → subtitles 填充、add_text 落 draft
- **Acceptance**: ≥3 样本真实 texts[]；compose subtitles 维度从 0→真实数；add_text 过校验（font 名命中率诚实记录，未命中走 unmapped/规整不硬编）；整稿过校验
- **Verify**: font_extract 产出 + compose_eval subtitles 列 + validate_icccut_draft → **Result**: pending

### E4 — 报告  [todo]
- [ ] spec 结果块（#2a/#2b/#1 数据 + 局限）
- [ ] CLAUDE.md 更新（k 投票/真时长/font 真跑现状）
- [ ] review.md + 提交 + （问用户）并入 main
- **Acceptance**: 数据量化、局限诚实、CLAUDE.md 更新
- **Verify**: eval 表 + spec diff + CLAUDE.md diff → **Result**: pending
