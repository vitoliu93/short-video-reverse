# Goal: 短视频「整体叙事结构」反解 (narrative / script structure reverse-engineering)

**Created**: 2026-05-30  **Tier**: full  **Pipeline prefix**: `narr_`

## Intent
把一条短视频（仅像素+音频，无工程文件）反解成结构化的**叙事/脚本结构 JSON**——回答「这片子是怎么讲故事的」：开场钩子类型、叙事结构（几幕/段落及其功能）、节奏画像、逐镜头内容、内容标签、情感曲线、关键时间点。这是 `short-video-reverse` 的**第 5 条独立反解能力**（继 ARC-smoke / BGM / Font / FX 之后），也是调研文档 `docs/高质量视频结构化拆解-方案调研.md` 的**头号结论**（ARC-Hunyuan-Video-7B = 唯一专门面向抖音风格短视频的开源多模态理解模型）落地为真正管线。

当前阶段是**实验**：唯一目的是证明「短视频的叙事结构可以被反解并结构化成机器可读 JSON」，产出供 KOX eval Gold Case 的 `narrative{}` 字段使用。**不**追求 1:1 还原创作者真实意图，只追求结构化、可复现、人工判定多数合理。

## 与现有 4 条管线的关系
- 复用 `fx_detect`（TransNetV2⊕ffmpeg）拿**确定性镜头时间线**——叙事结构的物理骨架（镜头数/时长/节奏来自这里，确定性，不靠 VLM）。
- 复用 `test_arc_api.py` 的 ARC 客户端思路（hosted API，`ARC_TOKEN`），扩展到 Summary 之外的 Segment / Grounding / QA 任务取**带时间戳的语义素材**。
- 复用 `fx_common.load_creds()` 的 doubao(Ark) 客户端做**合成层**：把 ARC 的自由文本 + 镜头时间线 → 收敛进闭集 schema（hook_type / structure 闭集标签）。
- 是「整体编排 / AVI 范式」（调研文档 §6）的最小落地：Plan(已知镜头线) → Invoke(ARC 多任务) → Synthesize(结构化)。

## Done means
- `uv run scripts/narr_extract.py <video>` 端到端跑通，写出 `outputs/narr/<stem>.json`：含
  - `narrative{ hook_type, structure(闭集 act 列表，每幕含 role/时间范围/一句话), pacing_profile(由镜头线计算的确定性指标), theme, cta }`
  - `shots[]`（来自 fx_detect 的确定性时间线，每镜头附 ARC/合成给的一句话内容）
  - `content_tags[]`、`emotion_curve[]`（带时间戳）、`key_moments[]`（带时间戳）
  - `provenance`（每个软字段标注来自哪个 ARC 任务/合成，及实际 model，可复现）
- 在用户提供的真实抖音竖屏样本（`assets/douyin_*.mp4`）上评测：叙事结构被人工判定为**多数合理**（hook_type 正确、幕划分与时间戳对得上、节奏指标与肉眼一致）。具体阈值在 spec N3 标定。
- `spec.md` 沉淀 N0→N3 可复现结果 + 诚实 known-limitations（遵循本仓库「动管线前先读 spec」约定）。
- ARC API 免费额度有限（~100 次，已用 1 次 Summary）：N0–N3 总调用控制在 ~20 次内，并在 spec 记录每条样本各调了哪些 task。

## Explicitly out of scope
- 微调 / 训练任何模型（含对 ARC 做 RL）；本实验只用 hosted ARC API + 现成 doubao 合成。
- 1:1 还原创作者真实主观意图、脚本原文逐字（只做结构化标签 + 一句话摘要层）。
- 接入任何端到端编排 / 生产管线（本仓库整体只是 POC 集合）。
- 字幕逐字 OCR / 字体 / BGM / 转场——已分别由 font_ / bgm_ / fx_ 覆盖；本管线只在 narrative 层引用其结论，不重做。
- 长视频（>5min）：ARC short-video 端点限 5min 内，抖音样本均满足。

## Scope changes (append-only)
- 2026-05-30 立项；POC 选择（叙事结构）经用户本会话确认。后端/素材/合成层三项关键决策见 spec §5 Key decisions。
