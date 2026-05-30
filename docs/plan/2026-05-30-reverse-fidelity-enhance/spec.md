# Spec: 反解保真度增强 — #2 + #1

## Approach
三件事，按依赖/成本排序，font 拉取（长极）先后台起跑，#2 并行做。

**#2a 真转场时长（免费，无模型）** — `compose_common.py:192` 现 `min(DEFAULT_TRANS_DUR, shot.dur*0.8)`。改读 `tr["t_end"]-tr["t_start"]`（fx_describe 已写 t_start/t_center/t_end，实测窗宽 ~0.3–0.8s），仍 `min(_, shot.dur*0.8)` 兜底、`t_end/t_start` 缺失退回 `DEFAULT_TRANS_DUR`。重生 5 稿、整稿校验。

**#2b k 投票稳标签（模型重跑，烧 VLM/doubao 额度）** — 漂移在上游单次模型调用，compose 只读缓存，故必须在上游加 k 投票并重生缓存。
- fx `type`：`fx_describe.describe_transition()` 加 `k:int=1`，对 `fc.vlm()+parse` 循环 k 次、对 `raw_type` 取多数（平票取最高 confidence/首个）；其余字段取众数所属那次的完整解析。`fx_extract.py:58` 透传 `--k`。**localization(TransNetV2⊕ffmpeg) 完全确定，k 投票只稳 `type`**。fx 无缓存→k×windows 次调用/每跑。
- narr `structure`：`narr_common.synth_narrative()` 加 `k:int=1`，对 doubao synth 调用循环 k 次、对 `structure`(+`hook_type`) 取多数；`acts`/`emotion_curve` 取众数那次的完整解析。`narr_extract.py` 加 `--k`。ARC 4 任务仍命中 `outputs/arc/` 缓存（k 不触发 ARC 重调），synth 无缓存→+（k-1）doubao/每跑。
- 凭据：worktree 下 `fx_common.AGENTS_DIR=ROOT.parent/icccut-agents` 解析错（指向 worktrees/），但 `load_creds()` 先读 `os.environ`→跑前 `set -a; source icccut-agents/.env`(VOLC) + `short-video-reverse/.env`(ARC) 即可。

**#1 font 真跑（长极，无模型/无额度，仅带宽+CPU）** — 字体库与索引都不在盘上。
1. `tosutil cp tos://kox-statics/fonts_effect/ assets/fonts/ -r -f -flat -j=10 '-exclude=*.png'`（14GB/2660 obj，后台）。
2. `font_build_index.py` → `outputs/font_index/manifest.jsonl`（仅 cmap 提取，快）。
3. `font_extract.py <video>` ×样本 → `outputs/font/<stem>.json`（NCC render-compare，无模型）。
4. 重跑 `compose_extract.py`（缓存优先，自动吃新 `outputs/font/`）→ `subtitles[]` 填充、`add_text` 真实落 draft。schema 是干净直通（recon 核对：font.texts[] 字段↔add_text_event 无错配）。

## Affected surfaces
- `scripts/compose_common.py` — `add_video_shot` 用实测转场时长（#2a）。
- `scripts/fx_describe.py` + `scripts/fx_extract.py` — fx `type` k 投票 + `--k`（#2b）。
- `scripts/narr_common.py` + `scripts/narr_extract.py` — `structure` k 投票 + `--k`（#2b）。
- `assets/fonts/`（共享真实 assets，gitignore）+ `outputs/font_index/manifest.jsonl` + `outputs/font/*.json`（#1，产物，gitignore）。
- `scripts/compose_smoke.py` — 若改 transition_duration 断言则同步（#2a）。

## Key decisions
- **k 投票放上游不放 compose** — 漂移源在 fx/narr 单次调用，compose 只读缓存；上游投票一次、缓存即稳，compose 不变。
- **只投分类标签，不投 localization/acts** — 时间戳确定（never let VLM invent），acts/emotion_curve 难投→取众数那次整解析，与 CLAUDE.md 「deterministic skeleton」一致。
- **font 全量拉取** — 闭集 NCC 需真字体在库；`--max-fonts` 只能 smoke 机制、会漏真字体→不能用于真匹配。
- **真转场时长用检测窗宽** — 是 TransNetV2⊕ffmpeg 候选窗，非 VLM 校准的视觉融合时长；比常数 0.5 更贴近，标注为近似（无专门时长估计器前的最优）。

## Risks & open questions
- **font 真匹配可能命中率低/字体名不在 icccut Font_type 枚举** — font.match 是 TTF 文件名 stem，未必是剪映枚举 → add_text 可能 `font` 校验失败。缓解：compose 已设计「带上让 validator 报错」，失败则记 unmapped/规整，诚实记录命中率，不硬编。
- **14GB 拉取耗时/中断** — tosutil 支持续传（-f 覆盖、可重跑补齐）；盘 351GB 充足。
- **k 投票额度** — fx k=3 × windows × 样本数；只对有软转场的样本（主要 Lotus）有意义，硬切样本投 type 无效益 → fx k 投票优先 Lotus；narr structure 投票便宜(每样本+2 doubao)可全跑。
- **worktree 路径坑** — fx_common/narr 的 ROOT.parent 在 worktree 下偏移；靠 env 导入凭据绕过，已验 load_creds OK。
