# Preflight: compose_ 跨仓 + 校验就绪

> compose_ 的「映射对不对」靠 icccut-agents 的真实校验器判定，且部分管线重跑需双凭据。下列检查在 C0 开工前实跑。

| # | 检查项 | 命令 / 方法 | 期望 | 结果 |
|-|-|-|-|-|
| 1 | icccut-agents 仓在 + 可达 | `ls ../../../../icccut-agents` (从 worktree 看 = `/Users/liujiaxi/codebase/icc/kox-base/icccut-agents`) | 目录在 | pending |
| 2 | 校验器存在 | `ls $ICC/.claude/skills/draft-manager/scripts/{validate_action.py,validate_icccut_draft.py,save_to_draft.py}` | 三脚本在 | pending |
| 3 | 枚举源（真闭集）存在 | `ls $ICC/src/capcut_router/pyJianYingDraft/metadata/{filter_meta,video_effect_meta,animation_meta,font_meta}.py` | 在 | pending |
| 4 | 权威参数语言 | `ls $ICC/docs/ICCCUT_JSON_LANGUAGE.md` | 在（已读） | pending |
| 5 | icccut venv 可跑校验器 | 在 $ICC 内 `uv run python .claude/skills/draft-manager/scripts/validate_action.py --help`（或 import 探针） | 能 import / 出 usage | pending |
| 6 | 反解输入缓存在 | worktree `outputs/{fx,narr,bgm}/<stem>.json`（symlink 到主 checkout） | Lotus 有 fx+narr+bgm | pending |
| 7 | （重跑才需）双凭据 | 本仓 `.env` ARC_TOKEN；`$ICC/.env` VOLC_ARK_API_KEY | C0–C2 吃缓存，不必；C3 视情况 | n/a（缓存优先） |

`$ICC = /Users/liujiaxi/codebase/icc/kox-base/icccut-agents`。

## Results (2026-05-30 ✅ 全过)
- #1–#4 全在。#3 枚举源确认：`transition_meta.py / filter_meta.py / video_effect_meta.py / effect_meta.py / font_meta.py / animation_meta.py / mix_mode_meta.py / mask_meta.py / audio_effect_meta.py`（+ capcut_* 变体）。
- **#5 校验路径已锁定（关键）**：`uv run --directory $ICC python .claude/skills/draft-manager/scripts/validate_action.py --action-type <T> --action '<json>'`。输出 `校验通过` 或 `校验失败:\n  - <msg>`。`validate_action(action, action_type)->List[str]`（空=过）可直接 import。
- **C0 核心问题已部分 de-risk**：一条按本 spec 映射搓的 add_text（`transform_y=-0.42`、`font=SourceHanSansCN_Bold` 下划线、`font_color=#FFFF00`、`track_render_index=15000`）→ **校验通过**；非法 transition 名 → 正确报「不在有效列表中」。→ 映射能产出合法 action，枚举强校验生效。
- #6 反解输入：Lotus 有 fx+narr+bgm（symlink 可达）。
- 校验器**无需** ICCCUT_DRAFT_DIR / init_draft 上下文即可单条校验（孤立调用即可），比预想简单。

## 已知约束
- **不写 icccut-agents**：compose_ 只读其校验器/枚举/文档。校验通过 subprocess 在 $ICC 内 `uv run` 调用（用它自己的 venv，不污染本仓 venv）。
- **校验器可能需 ICCCUT_DRAFT_DIR 等环境**：validate_action.py 若依赖 draft 上下文，C0 先探其最小调用形态（可能需先 init_draft 再 save_to_draft 触发校验，而非孤立调 validate_action）。C0 第一步即摸清最小校验路径。
- **font_extract 未跑**：outputs/font 空、字体索引未建（建索引拉 14GB）。C0/C1 用 schema 精确 texts[] fixture；真 font 留 C3 视情况。
