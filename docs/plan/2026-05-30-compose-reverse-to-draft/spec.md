# Spec: compose_ — 反解结果编排 + 映射到 KOX icccut_draft

> 动 compose_ 前先读本 spec。§9+ 为各里程碑（C0→C3）的实测结果块（完成后回填）。

## Approach

三段式，沿用仓库 de-risk-first 节奏（C0 先打掉最大未知，再地基，再全链，再评测）：

1. **编排层（orchestrator）**：`compose_extract.py` 在一个视频上调度 bgm/font/fx/narr。各管线已有 `outputs/<pfx>/<stem>.json` 磁盘缓存 → 命中即不重算。**去重**：narr_extract 内部已跑 `fx_detect`、fx_extract 也跑 → 只跑一次 detect，shots 复用。部分失败不致命（缺哪条反解，统一 JSON 对应段落留空 + 记 provenance）。
2. **映射层（mapping）**：`compose_common.py` 把统一反解 JSON 翻成 `add_*` action。新知识 = **反解闭集 → 剪映闭集的映射表**（不存在于任何现有代码）+ 坐标/单位换算器。无法映射 → 落 `unmapped` 字段，不硬编。
3. **校验层（validate）**：产出的每条 action 过 icccut-agents 的 `validate_action.py`（真实枚举校验），整稿过 `validate_icccut_draft.py`。这是「映射对不对」的客观判据，不靠自我宣称。

**为什么从像素反解仍产出 `${media_N}` 占位 draft**：我们只有像素、无源素材文件。draft 捕获的是**编辑结构**（时序/转场/文字/特效/BGM 风格），媒体是可填槽——这正是 reverse-draft 既有模式，也正好服务 eval Gold Case（结构而非具体素材）。

## Affected surfaces
- **新增** `scripts/compose_common.py` — 编排 + 映射表 + 换算器 + 枚举加载/校验 + action builders + draft 信封。
- **新增** `scripts/compose_extract.py` — 单视频入口：编排→统一反解 JSON + .draft.json。
- **新增** `outputs/compose/<stem>.json`（统一反解）+ `outputs/compose/<stem>.draft.json`（KOX draft）。
- **只读消费**：`outputs/{bgm,font,fx,narr}/<stem>.json`（各管线产出）；`scripts/{fx_detect,fx_common,...}`（复用 detect 去重）。
- **跨仓只读**：`../icccut-agents/`（`docs/ICCCUT_JSON_LANGUAGE.md`、`draft-manager/scripts/validate_action.py`、`src/capcut_router/pyJianYingDraft/metadata/*.py` 枚举源）。compose_ 不写 icccut-agents。

## 映射契约（source → target，单位已核）

目标 draft 形：`{meta, inputs, script:[{skill, skill_type, actions:[{type:"action", action_type, id, index, params}]}]}`。时间**秒**；transition/animation/effect/font 名为**中文剪映枚举**；坐标 transform_x/y 为**中心原点、半画布单位**（0=中心，x:-1左+1右，y:-1下+1上）。

| 反解源 | → action | 关键换算 / 映射 |
|-|-|-|
| `narr.shots[]`（或 fx_detect） | `add_video`（单镜头相册→`add_image`） | `target_start=shot.start`；`start=0,end=shot.dur`；`video_url=${media_N}`；主轨 `track_name="video",track_render_index=0` |
| `fx.transitions[].type`(16 tags) | `add_video.transition`+`transition_duration` | 映射表 `FX_TRANS→剪映名`（`dissolve→叠化`,`fade-to-white→闪白`,`fade-to-black→闪黑`,`glitch→故障`,`zoom-in→放射?`,`blur→模糊`,`spin→中心旋转`,`whip-pan→横移模糊`,`wipe→向左擦除`,`slide→向左`,`push→?`,`mask→?`；`hard-cut`/`none`→不加 transition）。挂在切点**前一镜头**的 out 点。`transition_duration≈gap` 或默认 0.5 |
| `font.texts[]` | `add_text` | `appear.first/last→start/end`✓；`bbox`[x,y,w,h]归一左上→`transform_x=(cx-0.5)*2, transform_y=(0.5-cy)*2`（cx=x+w/2,cy=y+h/2；已核 cy=0.71→ty=-0.42）；`color.fill→font_color`✓ `#RRGGBB`；`font.match→font`（连字符→下划线规整后过 Font_type 枚举，未命中落 unmapped+默认体）；`decoration.stroke→border_width/border_color`；`decoration.shadow→shadow_enabled`；`animation→intro_animation`（`typewriter→打字机_I`,`scroll→向上滑动`,`pop→弹入`,`none→渐显`）；`size_rel→font_size`（近似换算，待标定）；字幕轨 `track_render_index=15000`（标题 14000） |
| `bgm.bgm{}` | `add_audio` | `start→target_start`；`duration=end-start`；`volume`默认或取 volume_profile 均值；`audio_url`=检索到的相似 BGM `match.audio_url`（tos://→占位 `${audio_1}`，real url 留 default/注释）；BGM 轨 `track_name="audio_bgm",track_render_index≈1000` |
| `fx.effects[].types`(12 tags) | `add_effect`（色调类→`add_filter`） | 映射表 `FX_EFFECT→剪映名`（`shake→抖动`,`rgb-split→RGB描边`,`light-leak→胶片漏光`,`film-grain→噪点`,`blur-pulse→模糊`,`vignette→暗角`,`zoom-pulse→变焦推镜`,`particles→星光?`,`freeze-frame→故障定格`,`color-filter→走 add_filter`,`speed-ramp→其实是 speed 参数非 effect`,`none→跳过`）；`t_start/t_end→start/end`✓；`effect_category="scene"`；params 经 `get_effect_meta.py` 取 0–100 默认；特效轨 `track_render_index∈[5000,10000]` |
| `narr.narrative{}` | `meta.reverse_narrative`（注释） | 非时间线 action。acts/hook/structure/pacing/emotion/key_moments 作 eval-gold 元数据存 meta + 统一 JSON，不造 add_text |

**信封**：`meta{template_type:"reverse_compose", draft_id, canvas w/h}`；`inputs{${media_N}:{type:video_url}, ${audio_1}:{type:audio_url}}`；`script` 按 skill 分组（add-video / add-text / add-audio / add-effect）。`id` 全局唯一、`index` 1-based 递增。

## Key decisions
- **校验用 icccut-agents 真枚举，不自造**：compose_common 运行期从 `../icccut-agents/.../pyJianYingDraft/metadata/*.py` 加载枚举做校验（DRY）；映射表是本计划唯一新增的「知识」。— 避免枚举漂移、保证 draft 真能被 KOX 吃下。
- **媒体占位而非召回** — 见 Approach；draft 是结构模板，服务 eval gold + 一键复刻。
- **narrative 不进时间线** — pacing≠叙事节奏（narr spec §11.5）；硬塞 add_text 会造假。作元数据。
- **去重 fx_detect** — 一次 detect 喂 fx + narr，省一遍 transnet。
- **unmapped 诚实落字段** — 反解标签映射不到剪映闭集时记 `{tag, reason}`，不静默丢、不硬贴最近邻。CLAUDE.md #1「不埋」。

## Risks & open questions
- **fx tag→剪映名映射的语义对不对**：16 transition + 12 effect tag 手工映射，无 ground-truth。缓解：C0 先在真稿上验证「映射后过 validate_action.py」+ 人工核名；模糊的（push/mask/particles）落 unmapped 并记。
- **font.match 名 vs Font_type 枚举对不齐**：font_ 匹配的是 TOS 字体库（kox-statics/fonts_effect）= 剪映字体库？需核 798 成员是否同源；连字符/下划线、显示名 vs 标识名差异。C0 验证。
- **font_extract 未在样本上跑过**（outputs/font 空、字体索引未建，建索引要拉 14GB）。C0/C1 用 schema 精确的 texts[] fixture 验映射；C3 才视情况跑真 font（或诚实记为局限）。
- **add_text 坐标半画布单位的精确口径**：`transform_y=-0.42≈near bottom` 已核，但 size_rel→font_size 的换算系数未标定。C1 标定或近似 + 标注。
- **跨仓校验的环境**：validate_action.py 跑在 icccut-agents 自己的 venv（uv），compose_ 通过 subprocess 调它。preflight 验证可达 + 可跑。
- **Lotus 是 16:9 非抖音**：仅用于跑通机制（有 fx+narr+bgm 全套）；代表性评测在 C3 用 douyin_* 真实竖屏。

## 里程碑
| 里程碑 | 类型 | 交付 | 通过判据 |
|-|-|-|-|
| **C0** | de-risk 最大未知 | 用现有反解输出，手搓最薄一刀（add_text + add_audio + add_video + 1 transition + 1 effect）→ 一份 draft.json，过 icccut-agents 真实校验 | validate_action.py 全过 + 人工核参数与视频吻合 → 映射成立 |
| **C1** | foundation | `compose_common.py`：编排（去重 detect/缓存/部分失败）+ 映射表 + 换算器 + 枚举加载校验 + action builders + 信封 + 统一 JSON schema | 各部件单测过；映射表覆盖 16+12+4 tag；枚举校验对接通 |
| **C2** | full chain | `compose_extract.py` 端到端：Lotus + 1 douyin → 统一 JSON + .draft.json，整稿过 validate_icccut_draft.py | 两类视频产出字段完整、整稿校验过、unmapped 诚实记录 |
| **C3** | eval + report | ≥3 真实抖音评测映射保真度（落进/丢失/为何）+ spec 结果块 + known-limitations + CLAUDE.md 登记 | 保真度量化、局限诚实、第 6 条能力登记 |
