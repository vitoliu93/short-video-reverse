# Todo: 短视频「转场/特效」反解 (`fx_`)

## Current State  ← update this constantly; it is the resume cursor
- **Phase**: X2 — full chain（fx_extract 全链路 + 聚合去重 + 特效遍）
- **Status**: todo
- **Owner**: 41529b37-8723-4107-8555-72ce2a0a7c9a
- **Branch**: dev-plan-2026-05-30-transition-fx-reverse
- **Last done**: X1 完成——后端锁定(Ark/doubao-seed-2.0-pro)、TransNetV2(CPU)、fx_detect、fx_common、fx_describe 全部落地并冒烟通过(spec §10)。发现 type 标签 model-dependent。
- **Next**: 写 fx_extract.py（遍历候选窗口→describe→视频级聚合→写 outputs/fx/Lotus_*.json），加特效遍，跑 Lotus 验证
- **Blockers**: none（X3 抖音素材待用户提供，不阻塞 X2；外部 Ark 调用偶发分类器瞬时拒绝，重试即可）

## Phases

### X0 — 核心假设 de-risk  [done]
- [x] 探针验证 agent-vision 端点收 base64 图、返回 SSE
- [x] 9 帧跨 cut → 正确结构化转场 JSON（glitch，人工核帧确认）
- **Acceptance**: VLM 能从几帧产出有用的结构化转场描述 + 端点协议摸清
- **Verify**: `/tmp/probe_doubao_vision.py` 两测均 HTTP 200 + 合理输出  → **Result**: ✅ 通过（spec §9）

### X1 — foundation  [done]
- [x] 解决后端可复现：锁定 **Ark 直连 `https://ark.cn-beijing.volces.com/api/coding` + model=`doubao-seed-2.0-pro` + `VOLC_ARK_API_KEY`**；实测确定性返回该 model 且支持图片视觉。Ark `/api/coding` 仅放行 coding-plan 模型，doubao-1.5-vision-pro/vision-pro-32k 均 404。
- [x] `uv add transnetv2-pytorch`（1.0.5，权重内置）；CPU 1.78s/15s（mps 更慢且漏边界）→ 用 CPU
- [x] `fx_detect.py`：TransNetV2 + ffmpeg scene → 候选窗口（并集去重）；Lotus 15镜头→12窗口/3.38s，含 2 个 transnet-only(渐变召回)
- [x] `fx_common.py`：Ark SSE 流式 VLM 客户端（UTF-8 强制解码，分离 thinking/text）+ 闭集 taxonomy + 剪映类目映射 + 帧采样/窗口工具 + .env 解析
- [x] `fx_describe.py` + schema 定稿（以实际产出为准，含审计字段）
- **Acceptance**: TransNetV2 跑通+墙钟✓；fx_detect 候选窗口与 ffmpeg cut 吻合且多召回渐变✓；fx_common 的 VLM 客户端能稳定取到答案✓
- **Verify**: `fx_detect`→12窗口/3.38s；`fx_describe` 4.19窗口→ pro 返回 wipe/conf0.92/中文正常/JSON解析OK  → **Result**: ✅ 全部通过（发现 type 标签 model-dependent，记入 spec §10）

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
