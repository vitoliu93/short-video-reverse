# Goal: 短视频「转场/特效」反解 (transition & effect reverse-engineering)

**Created**: 2026-05-30  **Tier**: full

## Intent
把抖音爆款短视频里的**转场**（镜头之间的切换：叠化/推拉/故障/甩镜…）和**特效**（镜头内部的滤镜/抖动/粒子/光效/卡点缩放…）反解成结构化 JSON——能定位、能用自然语言描述、并打标签——作为逆向回剪映草稿的**语义描述层**（不是 1:1 映射剪映特效 ID）。当前阶段是**实验**，唯一目的是证明「抖音爆款的转场/特效可以被拆解并结构化成文字描述」。方向成立后，后续才考虑用 RL 微调 ARC。这是 `short-video-reverse` 的第 4 条独立反解能力（继 ARC / BGM / Font 之后）。

## Done means
- `uv run scripts/fx_extract.py <video>` 端到端跑通，写出 `outputs/fx/<stem>.json`：`transitions[]` 中每个转场含 时间窗口 / 闭集 type 标签 / 自然语言描述(cn+en) / 剪映类目标签 / confidence / visual_cues；并附 best-effort 的 `effects[]`。
- 在用户提供的真实抖音竖屏爆款上评测：转场被正确**定位**且 type 被人工判定为**多数正确**（具体阈值在 spec X3 标定）。
- `spec.md` 沉淀 X0→X3 的可复现结果 + 诚实的 known-limitations（遵循本仓库「动管线前先读 spec」的约定）。

## Explicitly out of scope
- 1:1 映射到具体剪映/CapCut 特效 ID（只做语义标签层；剪映 v6+ draft 已加密）。
- RL 微调 ARC（未来工作，仅在本实验方向被验证后启动）。
- 接入任何端到端编排 / 生产管线（本仓库整体只是 POC 集合）。
- 纯音频驱动的卡点判定超出帧可见范围的部分（音频归 BGM 管线；本管线只用画面 + 可选的 cut 时间戳与节拍对齐）。

## Scope changes (append-only)
- 2026-05-30 立项；范围、素材、定位策略三项决策见 spec §5 Key decisions（用户本会话确认）。
