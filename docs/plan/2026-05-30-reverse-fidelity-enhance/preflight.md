# Preflight: 反解保真度增强 — #2 + #1

Checks derived from spec. Run before execution. [ ] = unverified, [x] = verified, [!] = broken.

- [x] **磁盘充足**（14GB font 库）— `df -h .` → 351GB free（62% used）✓
- [x] **tosutil 可用 + 已配置** — `/Users/liujiaxi/codebase/icc/kox-base/.claude/skills/tos-cli/bin/tosutil version` → v4.1.7；`~/.tosutilconfig` 存在（1.8K，auth ok）；`ls tos://kox-statics/fonts_effect/` → 2660 obj / 14.05GB ✓
- [x] **VOLC_ARK_API_KEY 可解析（worktree）** — `source icccut-agents/.env` 后 `fx_common.load_creds()` → model=doubao-seed-2.0-pro, key ok ✓（worktree 下 AGENTS_DIR 路径偏移，靠 env 绕过）
- [x] **ARC_TOKEN 在 short-video-reverse/.env** — 存在（narr ARC 命中缓存，不重调；k 投票只重 doubao synth）✓
- [x] **5 样本视频在盘** — assets/{Lotus…,douyin_ai_19s,douyin_drama_16s,douyin_hair_17s,douyin_kid_10s}.mp4 全在 ✓
- [x] **font schema ↔ add_text_event 对齐** — recon 核对 texts[] 字段(bbox/text/color.fill/font.match/size_rel/decoration/animation)↔add_text_event 无错配 ✓
- [x] **font 索引/库现状** — `outputs/font_index/manifest.jsonl` 不存在、`assets/fonts/` 原本不存在 → 确认 NOT BUILT，需全量拉取 ✓

## Findings
- **zsh glob 吃掉 `-exclude=*.png`** → `no matches found`，首次拉取空跑。修：引号包 `'-exclude=*.png'`。
- **tosutil 不要再套 nohup+& 进 run_in_background**：双重后台导致 harness 在 8s wrapper 退出时误报完成。直接把 tosutil 交给 run_in_background（ID bu0qzjyi8）→ 干净追踪 + 真完成通知。
- **worktree 路径坑**：fx_common `AGENTS_DIR=ROOT.parent/icccut-agents` 在 worktree 解析成 `worktrees/icccut-agents`（不存在）；但 load_creds 先读 os.environ → 跑前 source .env 即可。`tosutil`/scripts 用绝对路径，别依赖 ROOT.parent。
- **font_build_index 不自拉 TOS**：只扫 `assets/fonts/` 本地 TTF。TOS 拉取是独立前置步（tosutil），非 streaming（streaming 是 bgm 的事）。
