# Todo: compose_ — 反解结果编排 + 映射到 KOX icccut_draft

## Current State  ← 恢复游标，常更新
- **Phase**: C3 — eval + report **[DONE ✅]** — 计划完成
- **Status**: **ALL DONE**（C0 ✅ / C1 ✅ / C2 ✅ / C3 ✅）
- **Branch**: worktree-dev-plan-2026-05-30-compose-reverse-to-draft
- **Last done**: **C3 通过** — `compose_eval.py` 保真度评测：镜头 41→41(1:1) / 非硬切转场 8/8 / 特效 11/12 / bgm 1/1 / 叙事 5/5。评测钓出真 bug：转场挂载非单射(重复挂+漏挂)→`assign_transitions` argmin+消费 修根因 + smoke 回归断言。对抗审计精修映射表 5 条 + 确认 4 条 unmapped。spec §12 + CLAUDE.md 第6条 + review.md 已写。
- **Next**: 待用户决定是否将分支并入 main（`review` 已出，工件齐）
- **Blockers**: none

## Phases

### C0 — de-risk：映射最薄一刀过真实校验  [done ✅ 2026-05-30]
最大未知不是「能不能跑 5 管线」（能），而是「反解输出→draft 映射出的 JSON，icccut-agents 收不收」。最险的是 add_text（参数最多、坐标换算、字体枚举对齐）。
- [ ] 跑 preflight（validate_action.py 可跑、枚举源在、icccut venv ok）
- [ ] 取 Lotus 真实 fx+narr+bgm 输出 + 一条 schema 精确的 font texts[] fixture
- [ ] 手搓映射：≥1 add_video（含 1 transition）+ 1 add_text + 1 add_audio + 1 add_effect → 一份 `outputs/compose/_c0_probe.draft.json`
- [ ] 每条 action 过 `../icccut-agents` 的 `validate_action.py`；记录通过/失败 + 失败根因
- [ ] 人工核：transform_x/y、font_color、transition 名、effect 名 与视频/源 JSON 吻合
- **Acceptance**: 至少 add_text + add_audio + add_video(+transition) 三类 action 过 validate_action.py；坐标/颜色/枚举名经人工核对合理；font.match→Font_type 对齐情况摸清（对齐/需规整/需 unmapped）
- **Verify**: `uv run --directory $ICC python validate_action.py`（in-process 校验每条 action）→ **Result**: ✅ **25/25 过**（Lotus 真反解：15 add_video+transition / 1 add_audio / 8 add_effect / 1 add_text）。校验闭集=MD 子集（抖动/漏光不在→改 动感模糊/光晕）。spec §9。draft: `outputs/compose/_c0_probe.draft.json`，探针 `/tmp/compose_c0_probe.py`

### C1 — foundation：compose_common.py  [done ✅ 2026-05-30]
- [ ] 编排器 `run_pipelines(video)`：命中 outputs/ 缓存、去重 fx_detect、部分失败降级 + provenance
- [ ] 映射表：`FX_TRANS_TO_JY`(16)、`FX_EFFECT_TO_JY`(12)、`FONT_ANIM_TO_JY`(4)，未映射项显式 None→unmapped
- [ ] 换算器：bbox→transform_x/y、size_rel→font_size、color 透传、时间秒
- [ ] 枚举加载器：从 ../icccut-agents pyJianYingDraft/metadata 读 Font_type/transition/effect/filter 闭集 + 校验函数
- [ ] action builders：build_add_video / add_text / add_audio / add_effect / add_filter + draft 信封（meta/inputs/script、id 唯一、index 递增）
- [ ] 统一反解 JSON schema（{shots,subtitles,bgm,transitions,effects,narrative,provenance}）
- **Acceptance**: 各 builder 单测产出过 validate_action.py；映射表 16+12+4 全覆盖（命中或显式 unmapped）；枚举校验对接通
- **Verify**: `uv run --directory $ICC python scripts/compose_smoke.py` → **Result**: ✅ **全过**（14+7+3 映射值过校验 / 换算器单测过 / Lotus 回归 24/24 / add_text fixture 过）。spec §10

### C2 — full chain：compose_extract.py  [done ✅ 2026-05-30]
- [ ] 单视频入口：编排→统一反解 JSON `outputs/compose/<stem>.json`
- [ ] 映射→`outputs/compose/<stem>.draft.json`
- [ ] 整稿过 `validate_icccut_draft.py`（含 id 全局唯一）
- [ ] Lotus（fx+narr+bgm 全）+ 1 douyin 跑通
- **Acceptance**: 两类视频产出字段完整、整稿校验过、unmapped 段落诚实记录、单镜头相册走 add_image
- **Verify**: 跑 compose_extract + validate_icccut_draft.py 整稿校验 → **Result**: ✅ **5/5 整稿过**（Lotus24/drama9/hair18/ai1/kid1）。抓修同轨重叠真 bug→_alloc_lane 分轨。spec §11

### C3 — eval + report：映射保真度评测  [done ✅ 2026-05-30]
- [x] 5 样本（Lotus + drama/hair/ai/kid 真实抖音）跑 compose_extract + compose_eval
- [x] 量化保真度：各模态反解信号「落进合法 draft 参数 / 丢失 / 为何」表（§12.1）
- [x] spec §12 结果块（§12.1 保真度 + §12.1a 抓修转场单射 bug + §12.2 对抗审计 + §12.3 verdict/局限）
- [x] 登记 CLAUDE.md（第 6 条 compose_ 能力 + 运行命令 + 设计决策 + spec 指针）
- [x] review.md 复盘
- **Acceptance**: 保真度量化、局限诚实（含 font 未跑真、color-filter 未识别、media 占位、近似参数）、CLAUDE.md 更新 ✓
- **Verify**: `compose_eval.py`（镜头 41→41 / 转场 8/8 / 特效 11/12 / bgm 1/1 / 叙事 5/5）+ 5 稿整稿全过 `validate_icccut_draft` + `compose_smoke.py` ✅ ALL PASS（含新增转场单射回归断言）→ **Result**: ✅ **达成**。抓修转场挂载非单射真 bug→`assign_transitions`。spec §12
