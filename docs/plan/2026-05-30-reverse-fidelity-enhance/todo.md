# Todo: 反解保真度增强 — #2 + #1

## Current State  ← update this constantly; it is the resume cursor
- **Phase**: E4（报告/登记）；E1 ✅ E2 ✅ E3 ✅
- **Status**: in_progress — 三件功能全完成验证；font pull 收尾(1304 ttf+10 temp≈1326)。提 E3 后做 E4
- **Branch**: dev-plan-2026-05-30-reverse-fidelity-enhance（基于 main=1d4b78b）
- **Last done**: **E3 ✅** font 真跑：拉 ~14GB 字体库 → build_index(1326 款,0 坏) → font_extract ×5(Lotus31/ai2/drama12/hair20/kid11=76 字幕,真实 OCR+样式) → 重跑 compose。**subtitles 76→76 全落 add_text、5 稿整稿全过校验+smoke**。抓修两真 bug:(1)hash/低分字体名会注错字 → font-face 闸=命中剪映闭集(798)且 score≥0.6 才发(真分低=渲染器gap,font §F3 中位0.53),否则记 _unmapped 留默认 → 5/76 发(6%,诚实);(2)单帧 OCR(first==last)→ end==start icccut 拒 → MIN_SUB_DUR 0.5s 兜底
- **Next**: E4 = spec 结果块(#2a/#2b/#1 数据+局限) + CLAUDE.md 登记 + review + 提交 + 问用户并入 main
- **Blockers**: none

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
