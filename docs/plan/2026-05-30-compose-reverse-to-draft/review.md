# Review: compose_ — 反解结果编排 + 映射到 KOX icccut_draft

**Sessions**: 8ab4fa50-3b44-4ddd-944d-d15c8d3b90fb (+ continuation)
**Outcome**: shipped (POC) — C0→C3 全过；font 真跑留作增强；分支待用户决定是否并入 main

## What went well (fortify)
- **De-risk-first 切对了刀**：先问「映射出的 JSON icccut 收不收」(C0)，而非「5 管线能不能跑」(已知能)。最险的 add_text(坐标/字体/枚举)第一刀就验，避免在地基上盖错楼。
- **以「真实校验器」为准绳，不自造 schema**：全程拿 icccut-agents 的 `validate_action` / `validate_icccut_draft` 当真值，而不是照 SKILL.md 猜参数。直接挡掉「枚举像是合法、实则不在校验子集」(抖动/漏光/暗角) 这类隐形坑——这是 C0 最高价值的发现。
- **评测当探针,真发现 bug**：C3 不是走过场填表——交叉核对「反解信号 vs draft 参数」时抓出转场挂载非单射(重复挂+漏挂)的真 bug，修根因 + 加回归断言锁死，而非把数字圆过去。和 C2 的同轨重叠(`_alloc_lane`)同源：跨 action 约束单点校验看不见，必须建器侧保证。
- **对抗审计映射表**：用独立 agent onto 全候选集 grep 核对每条映射，精修 5 条语义忠实度、确认 4 条 unmapped 正确。避免「能过校验=映射对」的错觉(过校验只证合法，不证忠实)。
- **诚实落 unmapped**：vignette/freeze-frame/color-filter/speed-ramp 无忠实目标 → 显式 `_unmapped` 字段，不硬贴一个「能过校验的近似」。符合「修根因不埋」。

## Friction & fixes
- **Workflow `parallel()` 漏 `await`** → `targets.filter is not a function`。根因：parallel 是 barrier 返回 Promise，忘 await。下次：parallel/pipeline 结果一律先 await 再用。
- **worktree 嵌套符号链接**：`ln -sfn` 进已存在的 `outputs/fx` 目录造出嵌套链接。根因：`-n` 对已存在目录的行为。下次：建链接前先判目标是否为已存在目录。
- **`_c0_probe.draft.json` 污染评测 glob**：手写一次性 glob 没排除 `_` 前缀，把 C0 旧映射(故障)的探针稿算进来，导致转场计数翻倍、新旧值混现——差点据此误判。教训：临时统计脚本要复用 eval 已有的过滤口径(`compose_eval` 本就排 `_`)，别另起一套。**也正是这次「数字对不上」反而把真 bug 钓出来了**——粗糙的交叉核对有价值。
- **`uv run python -c "import scripts.x"` 静默成功**：namespace package(无 `__init__.py`)下 `import scripts.compose_common` 居然成功，`||` 兜底分支不触发→空输出。下次：跑脚本统一 `PYTHONPATH=scripts` + `import compose_common`，别靠 `scripts.` 前缀。
- **icccut 校验器混合 text+JSON 输出**：内联 `json.load(stdin)` 被人类可读文本噎住。无害(`结果: 通过` 已可见)，但内联解析要么 `--json` 取最后一行、要么别解析。

## Corrections for the user
- 无明显需纠正的使用模式。ultracode + 明确二选一(Orchestration+mapping vs 其它)的开局让范围一次锁定，省去反复对齐。若要更快：可在开局就点明「font 真跑是否在本轮范围」——本轮判它为增强(需建 14GB 索引)，若用户其实想要会改变 C3 验收。

## Knowledge to promote
已固化进 `short-video-reverse/CLAUDE.md`(本轮提交)：
- 第 6 条 compose_ 能力(管线表行 + 运行命令 + 设计决策 + spec 指针)。
- **核心口径**：合法剪映枚举集 = icccut `add-*/references/*.md` 子集，**非** pyJianYingDraft 全枚举(抖动/漏光/暗角/故障定格 不在子集，禁用)。
- 跨 action 约束归建器：同轨重叠→`_alloc_lane`，转场↔镜头单射→`assign_transitions`(argmin+consume)。单 action 校验看不见。
- compose_ 跨仓只读(import icccut 校验器，绝不写入)，不导出剪映工程/不云渲染(范围外)。
- 已写 project memory: `compose-pipeline-reverse-to-draft.md`。
