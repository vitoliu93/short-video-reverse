# Todo: 反解保真度增强 — #2 + #1

## Current State  ← update this constantly; it is the resume cursor
- **Phase**: E4（报告/登记）**[DONE]** — 计划完成
- **Status**: **ALL DONE**（E1 ✅ E2 ✅ E3 ✅ E4 ✅）。font pull 后台收尾(~11GB/1370 ttf,不影响已验结果)。待用户决定并入 main
- **Branch**: dev-plan-2026-05-30-reverse-fidelity-enhance（基于 main=1d4b78b）
- **Last done**: **E4 ✅** spec Results § + CLAUDE.md(fx/narr `--k`、fidelity 增强 bullet、spec 指针) + review.md 写毕。E1/E2/E3 已分别提交(594f406 / 0059120)
- **Next**: 提交 E4 文档 → 问用户是否并入 main（同 compose 的 FF 方式）
- **Blockers**: none

## Phases

### E1 — #2a 真转场时长  [in_progress]
- [ ] `compose_common.py:192` 改读 `tr.t_end-tr.t_start`，缺失退 DEFAULT_TRANS_DUR，仍 min(shot.dur*0.8)
- [ ] 重生 5 稿（build_draft_from_cached）+ compose_smoke（icccut venv）
- **Acceptance**: 转场 transition_duration 来自实测窗宽（Lotus 8 转场各异、非全 0.5）；5 稿整稿全过校验；smoke 全过
- **Verify**: 打印 Lotus 各转场 dur + `validate_icccut_draft` ×5 + compose_smoke → **Result**: ✅ Lotus 转场 0.7/0.544/0.224 等实测值;5 稿全过;smoke 过。提交 594f406

### E2 — #2b k 投票稳标签  [done ✅]
- [ ] `fx_describe.describe_transition(k=1)` k 次投 `type`；`fx_extract --k`
- [ ] `narr_common.synth_narrative(k=1)` k 次投 `structure`(+hook_type)；`narr_extract --k`
- [ ] source 凭据；fx k=3 重跑（优先 Lotus，有软转场）+ narr k=3 重跑（全样本，便宜）→ 重生缓存
- [ ] 重跑 compose 吃新缓存 → 重生稿
- **Acceptance**: 代码可配 --k；Lotus 重跑 type/structure 标签稳定（同 k 投票两跑一致或多数稳）；稿仍过校验
- **Verify**: fx/narr --k=3 跑通 + 标签对比 + validate ×5 → **Result**: ✅ fx k3 Lotus(8→9 present 全可映射)、narr k3 全 5(kid drift 收敛)。5 稿过+smoke 单射 9→9。诚实发现:主漂移跨会话级,within-run k 投票稳单跑不消跨会话。提交 594f406

### E3 — #1 font 真跑  [done ✅]
- [ ] 等 font pull 完成（bu0qzjyi8）→ 校验 obj 数/大小
- [ ] `font_build_index.py` → manifest.jsonl
- [ ] `font_extract.py` ×≥3 样本（含 Lotus）→ outputs/font/<stem>.json
- [ ] 重跑 `compose_extract.py` → subtitles 填充、add_text 落 draft
- **Acceptance**: ≥3 样本真实 texts[]；compose subtitles 维度从 0→真实数；add_text 过校验（font 名命中率诚实记录，未命中走 unmapped/规整不硬编）；整稿过校验
- **Verify**: font_extract 产出 + compose_eval subtitles 列 + validate_icccut_draft → **Result**: ✅ 5 样本 76 字幕→76 add_text,全过校验+smoke。font-face 闸(闭集+score≥0.6)→5/76 发,71 默认(诚实);MIN_SUB_DUR 修零时长。提交 0059120

### E4 — 报告  [done ✅]
- [x] spec Results §（#2a/#2b/#1 数据 + 诚实局限）
- [x] CLAUDE.md 更新（fx/narr --k、fidelity 增强 bullet、spec 指针）
- [x] review.md + 提交 + （问用户）并入 main
- **Acceptance**: 数据量化、局限诚实、CLAUDE.md 更新 ✓
- **Verify**: eval 表 + spec diff + CLAUDE.md diff → **Result**: ✅ 完成,本次提交 E4 文档
