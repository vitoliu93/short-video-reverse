# Goal: compose_ — 反解结果编排 + 映射到 KOX icccut_draft

**Created**: 2026-05-30  **Tier**: full

## Intent
把 5 条已 de-risk 的独立反解管线（bgm / font / fx / narr + arc）在**一个视频上端到端编排**，产出统一反解 JSON `{shots, subtitles, bgm, transitions, effects, narrative}`，并**映射成 KOX `icccut_draft.json` 的 `add_*` action 参数**。这是调研文档 `docs/高质量视频结构化拆解-方案调研.md` 结论里点名的两大瓶颈（① 多模型工程整合调度 ② 反解结果→KOX draft 参数映射规则），也是 CLAUDE.md 明写的「尚未集成的 end-to-end orchestration」。本质 = icccut-agents `reverse-draft` 技能，但**从像素反解**（无剪映工程文件）。

## Done means
- **单入口** `compose_extract.py <video>` 跑通：编排 5 管线（命中各自 `outputs/` 缓存，去重共享的 `fx_detect`）→ 写统一反解 JSON `outputs/compose/<stem>.json`。
- 同时产出 `outputs/compose/<stem>.draft.json`：合法 `icccut_draft.json`（`{meta, inputs, script:[...]}`），媒体用 `${media_N}`/`${audio_N}` 占位。
- **draft 通过 icccut-agents 真实校验**：每条 action 过 `draft-manager/scripts/validate_action.py`（枚举/参数合法），整稿过 `validate_icccut_draft.py`。这是「映射正确」的客观判据。
- 反解侧的闭集标签**映射进剪映闭集**：fx transition tags(16)→剪映 transition 名；fx effect tags(12)→Video_scene_effect/Filter；font animation(4)→Text_intro；坐标/单位换算正确（bbox→transform_x/y、颜色 #RRGGBB、时间秒）。无法映射的诚实落 `unmapped` 而非硬编。
- 在 ≥3 条真实抖音样本上评测「映射保真度」：多少反解信号落进合法 draft 参数、丢了什么、为什么；spec 结果块 + known-limitations + 登记 CLAUDE.md。

## Explicitly out of scope
- **不做端到端成片**：不跑 `icccut_to_jianying_draft.py` 导出剪映工程/云渲染（draft 合法即止）。
- **不召回真实媒体**：媒体用占位符，不接 VikingDB 召回填充 `${media_N}`（那是下游 recreate 的事）。
- **不改 5 条管线的反解口径**：compose_ 只消费它们的 `outputs/` JSON，不动 bgm/font/fx/narr 的检测逻辑。
- **不做 k 投票稳定化**：fx type / narr structure 的 run-to-run 漂移是上游已知局限，本计划不在此修。
- **不把 narrative 塞进时间线 action**：`narrative{}` 作为 `meta` 注释 / eval-gold 元数据，不强行造 add_text。

## Scope changes (append-only)
- 2026-05-30 立项；范围由用户在 AskUserQuestion 选定为「Orchestration + KOX mapping」（含映射层，非仅编排）。
