# Review: 反解保真度增强 — #2 + #1

**Sessions**: 8ab4fa50-3b44-4ddd-944d-d15c8d3b90fb（compose 续）
**Outcome**: shipped — E1/E2/E3 全过验证；分支 dev-plan-2026-05-30-reverse-fidelity-enhance 待并入 main

## What went well (fortify)
- **长极先起跑、其余并行**：14GB font 拉取是关键路径，第一时间后台起跑，#2 的代码+重跑全程并行，没让带宽空等。三个后台任务(pull/fx-k3/narr-k3)同时跑，靠 harness 完成通知衔接。
- **先 recon 再动手**：两个 code-search agent 并行摸清 k 投票插入点、font 库现状、schema 对齐、缓存影响，避免边写边猜。recon 直接定位「font.match=文件名 stem」「ARC 缓存全 4/4」「fx 无缓存」等关键事实。
- **评测/校验当探针，抓真 bug 修根因**：E3 不是「跑通就行」——whole-draft 校验抓出零时长 add_text(单帧 OCR)、字体名校验抓出 hash/低分注入风险。都在根因处修(MIN_SUB_DUR、font-face 闸)并记诚实数字，不掩盖。
- **拿 spec 当真值校准阈值**：font-face score 阈值不是拍脑袋——查 font §F3「真实中位 0.53、渲染器 gap」才定 0.6，并诚实接受由此带来的 6% 低命中率（宁缺勿错）。
- **诚实记录反直觉发现**：k 投票本以为能消漂移，实测发现「单跑内多数一致、主漂移在跨会话」——没有粉饰成功，而是把这个限制写进 spec/commit/CLAUDE.md。

## Friction & fixes
- **zsh glob 吃 `-exclude=*.png`** → `no matches found`，14GB 拉取空跑一次。根因：zsh 对未匹配 glob 报错中止。修：引号包 `'-exclude=*.png'`。教训：传给外部 CLI 的 glob 一律引号。
- **run_in_background 套 nohup+&** → harness 在 8s wrapper 退出时误报「完成」，真下载脱管。修：直接把长命令交给 run_in_background，别再内部 `&`。
- **worktree 路径偏移**：fx_common `AGENTS_DIR=ROOT.parent/icccut-agents`、tosutil 路径在 worktree 下都错。绕过：凭据走 `source .env` 注入 env(load_creds 先读 environ)、tosutil 用绝对路径。
- **`git add` 拒 outputs/**：outputs/ 被 gitignore，但 fx/narr 早被 force-add 成 tracked。修：`git add -f` 更新 tracked-但-ignored 文件(沿用原仓约定)。
- **假设全库 hash 命名 → 错**：先验文件名是 hash(`32a9..._font.ttf`)，以为 font-face 全不可映射；实跑发现库混真实字体名(SourceHanSansCN_Medium/仓耳酷黑…)，8/12 在闭集。教训：少假设、多实跑一条看真数据。
- **eval 旧文案「font 未跑」**：font 真跑后陈述过时。修：compose_eval 加 font-face 命中率 + 改文案。代码里写死的状态字符串要随能力变更同步。

## Corrections for the user
- 无需纠正。「complete #2 & #1」范围清晰、一次到位。唯一可优化：#1 实际需 14GB TOS 拉取(此前只说「建索引」)——若提前点明「带宽/耗时」预期，决策更充分；本轮已认定用户授权 14GB（之前已告知需建库）后直接起跑。

## Knowledge to promote
已固化进 `short-video-reverse/CLAUDE.md`（本轮提交）：
- fx/narr `--k` k 投票命令 + 「主漂移是跨会话级」的诚实判断。
- compose fidelity 增强 bullet：实测 transition_duration、font 真跑 + font-face 闸(闭集+score≥0.6)、MIN_SUB_DUR、「文本/样式库无关、仅 font-face 依赖库」的关键认知。
- preflight.md 沉淀踩坑：zsh glob 引号、run_in_background 别套 nohup、worktree 路径绕过。
- 待更新 project memory [[compose-pipeline-reverse-to-draft]]：font 已真跑、k 投票已实现。
