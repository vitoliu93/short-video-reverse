# Todo: 短视频「转场/特效」反解 (`fx_`)

## Current State  ← update this constantly; it is the resume cursor
- **Phase**: X1 — foundation（锁模型 + schema/taxonomy + TransNetV2 + fx_common/fx_detect）
- **Status**: todo
- **Owner**: 41529b37-8723-4107-8555-72ce2a0a7c9a
- **Branch**: dev-plan-2026-05-30-transition-fx-reverse
- **Last done**: X0 de-risk 通过（探针验证 agent-vision 收图 + 产出结构化转场 JSON，见 spec §9）；计划文档落地
- **Next**: 查 icccut-agents 模型别名/路由，尝试锁定 doubao-seed-2.0-pro（preflight 头号 [!]）
- **Blockers**: none（X3 评测素材待用户提供，不阻塞 X1/X2）

## Phases

### X0 — 核心假设 de-risk  [done]
- [x] 探针验证 agent-vision 端点收 base64 图、返回 SSE
- [x] 9 帧跨 cut → 正确结构化转场 JSON（glitch，人工核帧确认）
- **Acceptance**: VLM 能从几帧产出有用的结构化转场描述 + 端点协议摸清
- **Verify**: `/tmp/probe_doubao_vision.py` 两测均 HTTP 200 + 合理输出  → **Result**: ✅ 通过（spec §9）

### X1 — foundation  [todo]
- [ ] 解决后端可复现：查 icccut-agents 模型别名/路由，锁定 doubao-seed-2.0-pro（或确立「记录实际 model + 分层」的退路）
- [ ] `fx_common.py`：SSE 流式 VLM 客户端（分离 thinking/text）+ 闭集 taxonomy + 剪映类目映射 + 帧采样/窗口工具 + .env 解析
- [ ] 定稿 §4 输出 schema
- [ ] `uv add transnetv2-pytorch`（或同等），实测本机 CPU/mps 在 15s 片上的墙钟
- [ ] `fx_detect.py`：TransNetV2 + ffmpeg scene → 候选窗口（并集去重）
- **Acceptance**: TransNetV2 在 Lotus 上跑通并打印墙钟；fx_detect 输出的候选窗口与 ffmpeg cut 大体吻合且能多召回渐变处；fx_common 的 VLM 客户端能稳定取到答案
- **Verify**: `uv run scripts/fx_detect.py assets/Lotus_*.mp4` 打印窗口列表 + 墙钟  → **Result**: pending

### X2 — full chain  [todo]
- [ ] `fx_describe.py`：单窗口 N 帧 → VLM → 结构化转场描述
- [ ] `fx_extract.py`：端到端 + 视频级聚合投票去重（借鉴 font group_events/best_obs）
- [ ] 特效第二遍：镜头内均匀采样窗口 → VLM 描述特效 → effects[]
- [ ] 写出 `outputs/fx/Lotus_*.json`
- **Acceptance**: JSON 生成，transitions[] 非空且字段完整（type/desc_cn-en/capcut/confidence/visual_cues），人工抽查描述合理
- **Verify**: `uv run scripts/fx_extract.py assets/Lotus_*.mp4` + 读 outputs/fx/Lotus_*.json  → **Result**: pending

### X3 — eval + report  [todo]
- [ ] 用户提供真实抖音竖屏爆款 → 跑 fx_extract
- [ ] 人工核对：转场定位召回 + type 准确率 + 标签合理性；标定验收阈值
- [ ] VLM 成本/延迟估算
- [ ] spec.md 追加 X1/X2/X3 结果块 + 诚实 known-limitations
- **Acceptance**: 在真实抖音片上转场被正确定位且 type 多数正确（阈值此处标定）
- **Verify**: 人工评测表 + spec 结果块  → **Result**: pending
