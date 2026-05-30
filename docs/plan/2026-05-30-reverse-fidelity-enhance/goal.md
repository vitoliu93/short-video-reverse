# Goal: 反解保真度增强 (compose POC 后续) — #2 + #1

**Created**: 2026-05-30  **Tier**: full（含 14GB TOS 拉取 infra → 需 preflight + 模型重跑）

## Intent
在已合并的 compose_ POC 之上，关掉评测/复盘暴露的保真缺口，让 reverse→draft 更可信：
1. **#2a 真转场时长**：`transition_duration` 不再硬编码 0.5，改读反解转场窗实测宽 `t_end−t_start`（数据已在 transition dict）。
2. **#2b 稳住漂移标签**：对 run-to-run 漂移的分类标签做 k=3 多数投票——fx 转场 `type`、narr `structure`——让 Gold Case 标签可复现。
3. **#1 font 真跑**：补上唯一没在真实视频跑通的模态。拉 14GB 字体库 → 建索引 → `font_extract` 跑样本 → 重跑 compose，让 `subtitles[]`/`add_text` 全链在真实抖音视频端到端落进合法 draft（此前仅 fixture 验）。

## Done means
- [ ] `transition_duration` 来自实测窗宽；5 稿仍整稿全过 icccut 校验。
- [ ] fx `type` / narr `structure` 走 k 投票，代码可配 `--k`；Lotus 重跑标签稳定。
- [ ] ≥3 样本（含 Lotus）`font_extract` 产真实 `texts[]`，重跑 compose 后 `add_text` 真实落进 draft 且过校验；保真度评测 subtitles 维度从 0 提到真实数。
- [ ] spec 结果块 + CLAUDE.md 更新（k 投票/真时长/font 真跑）+ review。

## Explicitly out of scope
- 导出剪映工程 / 云渲染；真实媒体召回（仍 `${media_N}` 占位）。
- color-filter LUT 识别；长视频/口播新样本（car_135s 等留后续）。

## Scope changes (append-only)
- 2026-05-30 立项；范围 = 用户在 compose 合并后点名的 #2(=2a+2b) + #1。
