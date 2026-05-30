# Todo: 短视频「整体叙事结构」反解 (`narr_`)

## Current State  ← update this constantly; it is the resume cursor
- **Phase**: 全部完成（N0→N3 done）；plan 收尾中（spec/CLAUDE.md 已写，待 commit）
- **Status**: done（待用户决定是否并入 main）
- **Branch**: dev-plan-2026-05-30-narrative-structure-reverse
- **Last done**: N3 评测 + 对抗审计(15 agent) + 两处契约级修复(QA 去框架化 / synth 收紧+visual-shock 定义+情绪不编弧线) + 修真 bug(normalize_acts 消 acts 重叠) + 诚实记录 doubao 残留漂移；spec §9–§11 落地；narr_ 登记进 CLAUDE.md(第5管线)。
- **Next**: 仅剩用户决定——是否把本分支并入 main。后续增强（structure/hook_type 的 k 投票、口播/带货/长片 car_135s 评测、acts↔TransNetV2 边界吻合度量化）均超出本 plan，见 spec §11.7。
- **Blockers**: none

## Phases

### N0 — 核心假设 de-risk  [done]
- [x] 探针 `/tmp/narr_n0_probe.py`：真实抖音 drama 上跑 ARC Segment/QA/Grounding
- **Acceptance**: ARC 能产出带时间戳、可结构化的叙事素材  → **Result**: ✅ 通过（spec §9）

### N1 — foundation  [done]
- [x] `narr_common.py`：ARC 客户端+磁盘缓存+THINK/ANSWER 解析+hms→sec、闭集 taxonomy(10/8/8/5)、`compute_pacing`(确定性)、复用 fx_common 的 doubao 合成客户端+合成 prompt+schema、`normalize_acts`
- **Acceptance**: 各部件单测通过，pacing 数值合理  → **Result**: ✅ 通过（spec §10）

### N2 — full chain  [done]
- [x] `narr_extract.py`：detect→pacing→ARC(缓存)→doubao 合成→写 outputs/narr/<stem>.json + provenance
- **Acceptance**: JSON 生成、字段完整、acts 对齐镜头线  → **Result**: ✅ 通过 Lotus+drama（spec §10）

### N3 — eval + report  [done]
- [x] 5 类样本(drama/Lotus/ai/hair/kid)端到端跑通 + 确定性 schema 校验 5/5
- [x] hook 视觉 ground-truth（contact sheet 肉眼核帧）5/5 正确
- [x] 对抗忠实度审计 15 agent（5 片 × 3 视角）→ 找出合成层明确问题
- [x] 两处契约级修复 + normalize_acts 真 bug 修复 + 重跑全过
- [x] doubao 残留漂移诚实记录（drama 3× 探针）+ spec §11 + known-limitations + CLAUDE.md 登记
- **Acceptance**: 真实抖音叙事结构被正确反解、人工判定多数合理  → **Result**: ✅ 实验目标达成（spec §11.7）

## 额度账
- ARC 免费额度 ~100；本 plan 共用 **20/~100**（缓存复用，re-run 不烧）。outputs/arc/ 存 20 个 <stem>_<task>.json。
