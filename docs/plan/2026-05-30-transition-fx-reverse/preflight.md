# Preflight: 短视频「转场/特效」反解 (`fx_`)

Checks derived from spec. Run before execution. [ ] = unverified, [x] = verified, [!] = broken.

- [x] `ffmpeg` / `ffprobe` 可用 — `which ffmpeg ffprobe` → /opt/homebrew/bin/*
- [x] VLM 端点可达且收 base64 图、返回 SSE — X0 探针 HTTP 200（见 spec §9）
- [x] 凭据存在 — `icccut-agents/.env(.test)` 含 `ANTHROPIC_BASE_URL=http://115.190.62.224:8001` + `ANTHROPIC_API_KEY`(len 35)；脚本直接解析 .env，密钥不入日志
- [x] 测试素材在位 — `assets/Lotus_MY26_Combined-15s_16x9_CLEAN_Audio-250207_v016.mp4` (1080p/25fps/15s)
- [x] **VLM 后端可复现** — 已解决：改走直连 Ark `/api/coding` + `model=doubao-seed-2.0-pro`，实测 `model_seen=doubao-seed-2.0-pro`（确定性）且支持图片视觉（见 Findings）
- [x] **TransNetV2 可装可跑** — `uv add transnetv2-pytorch`(1.0.5, 权重内置 30MB)；Lotus 15s：CPU load 1.86s + infer 1.78s(0.12×实时)，mps 反而更慢且漏边界 → **用 CPU**
- [ ] 真实抖音竖屏爆款素材 — 用户在 X3 提供，放 `assets/`

## Findings
- **SSE 协议**：端点是 Anthropic 流式格式（`event: ping` / `message_start` / `content_block_delta` 的 `thinking_delta`+`text_delta`），不是 OpenAI `choices[]`。前期 recon 判断有误，已在 fx_common 的客户端按 SSE 解析。
- **后端路由不固定（待 X1 解决）**：同一 `model=agent-vision` 两次请求分别返回 `kimi-k2.6` 和 `doubao-seed-2.0-code`。可能的解法：(1) 在 icccut-agents 找更具体的 model alias；(2) 直连火山引擎 doubao-seed-2.0-pro 的原生别名；(3) 退而求其次——输出里记录每次实际 `message.model`，评测分层。X1 开工先查 icccut-agents 的模型别名表 / 路由配置。
