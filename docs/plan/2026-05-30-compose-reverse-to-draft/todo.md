# Todo: compose_ — 反解结果编排 + 映射到 KOX icccut_draft

## Current State  ← 恢复游标，常更新
- **Phase**: C1 — foundation：compose_common.py
- **Status**: todo（C0 ✅ 完成）
- **Branch**: worktree-dev-plan-2026-05-30-compose-reverse-to-draft
- **Last done**: **C0 通过** — `/tmp/compose_c0_probe.py` 从真实 Lotus 反解搓 draft，25/25 action 过 validate_action（spec §9）。关键结论：校验闭集=参考 MD 子集（非全量枚举）、validate_action 可 in-process、transition 挂载 |t_center−shot.end|<0.25
- **Next**: 写 `scripts/compose_common.py`：① 枚举加载器（从 icccut `validate_params --list-values` 取真集）② 全量映射表 FX_TRANS(16)/FX_EFFECT(12)/FONT_ANIM(4)，逐个 onto 真集校验、无真名落 unmapped ③ 换算器 ④ action builders + 信封 ⑤ 编排器（缓存命中/去重 fx_detect/部分失败）
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

### C1 — foundation：compose_common.py  [todo]
- [ ] 编排器 `run_pipelines(video)`：命中 outputs/ 缓存、去重 fx_detect、部分失败降级 + provenance
- [ ] 映射表：`FX_TRANS_TO_JY`(16)、`FX_EFFECT_TO_JY`(12)、`FONT_ANIM_TO_JY`(4)，未映射项显式 None→unmapped
- [ ] 换算器：bbox→transform_x/y、size_rel→font_size、color 透传、时间秒
- [ ] 枚举加载器：从 ../icccut-agents pyJianYingDraft/metadata 读 Font_type/transition/effect/filter 闭集 + 校验函数
- [ ] action builders：build_add_video / add_text / add_audio / add_effect / add_filter + draft 信封（meta/inputs/script、id 唯一、index 递增）
- [ ] 统一反解 JSON schema（{shots,subtitles,bgm,transitions,effects,narrative,provenance}）
- **Acceptance**: 各 builder 单测产出过 validate_action.py；映射表 16+12+4 全覆盖（命中或显式 unmapped）；枚举校验对接通
- **Verify**: `uv run python -m pytest`-style 内联单测脚本 / 直接 assert 脚本 → **Result**: pending

### C2 — full chain：compose_extract.py  [todo]
- [ ] 单视频入口：编排→统一反解 JSON `outputs/compose/<stem>.json`
- [ ] 映射→`outputs/compose/<stem>.draft.json`
- [ ] 整稿过 `validate_icccut_draft.py`（含 id 全局唯一）
- [ ] Lotus（fx+narr+bgm 全）+ 1 douyin 跑通
- **Acceptance**: 两类视频产出字段完整、整稿校验过、unmapped 段落诚实记录、单镜头相册走 add_image
- **Verify**: 跑 compose_extract + validate_icccut_draft.py 整稿校验 → **Result**: pending

### C3 — eval + report：映射保真度评测  [todo]
- [ ] ≥3 真实抖音（drama/hair/+）跑 compose_extract
- [ ] 量化保真度：各模态反解信号「落进合法 draft 参数 / 丢失 / 为何」表
- [ ] spec §9–§12 结果块 + known-limitations
- [ ] 登记 CLAUDE.md（第 6 条 compose_ 能力 + 运行命令）
- [ ] review.md 复盘
- **Acceptance**: 保真度量化、局限诚实（含 font 未跑真、fx 标签映射模糊项、media 占位）、CLAUDE.md 更新
- **Verify**: 评测表 + spec 结果块 + CLAUDE.md diff → **Result**: pending
