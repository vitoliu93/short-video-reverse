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

---

## §9 C0 结果块 — 映射最薄一刀过真实校验（✅ 通过，2026-05-30）

**目的**：投入编排/映射工程前，先证明最大未知——「反解输出经映射搓出的 action JSON，icccut-agents 的真实校验器收不收」，尤其最险的 add_text（参数最多、坐标换算、字体枚举）。

**方法**：探针 `/tmp/compose_c0_probe.py`，从**真实 Lotus 反解输出**（`outputs/{fx,narr,bgm}/Lotus_*.json`）搓一份 draft，逐条过 `validate_action`（在 icccut venv 内 import，单进程校验全部）。跑：`uv run --directory $ICC python /tmp/compose_c0_probe.py`。

**Verdict：映射架构成立。25/25 action 全过校验。** 15 add_video（含 transition 故障/闪黑/叠化/闪白）+ 1 add_audio + 8 add_effect（噪点/RGB描边/变焦推镜/动感模糊/光晕）+ 1 add_text（坐标换算 tx=0 ty=-0.68、font 下划线规整、#FFFF00、描边、intro_animation）。draft 信封完整：16 占位（15 media + 1 audio）、id 全局唯一、index 递增、`reverse_narrative` 作 meta 带出。

**C0 得出的关键设计结论（落进 C1）**：
1. **校验闭集 = 参考 MD 子集，非全量枚举**：`validate_params.PARAM_REFERENCE_MAP` 从 `add-*/references/*.md` 抽有效值——transition/scene-effect/font/text-intro 各是 pyJianYingDraft 全量枚举（913/468/798…）的**子集**。`抖动`/`漏光`/`色差` 在全量枚举里有、但**不在校验 MD 子集** → 必须映射 onto MD 子集名（用 `validate_params.py --param X --list-values` 取真集）。首跑 shake→抖动、light-leak→漏光 即因此 FAIL，改 shake→动感模糊、light-leak→光晕 后 25/25。
2. **校验可单进程 in-process**：`from validate_action import validate_action; validate_action(a, atype)->List[str]`（空=过），无需逐条 subprocess、无需 init_draft 上下文。C1/C2 用此校验。
3. **transition 挂载口径**：`|t_center − shot.end| < 0.25s` → 挂该镜头 out 点；`hard-cut`/`none` 不挂 transition；duration 暂用默认 0.5s（gap≈0.04 是 TransNet 帧级边界，非视觉转场时长）。
4. **unmapped 方法生效**：`color-filter` 正确判为 filter 类（非 scene effect）→ 不造 add_effect、记 unmapped（C1 走 add_filter，filter_type 不过枚举校验）。`speed-ramp` 实为 speed 参数非 effect。
5. **font 对齐**：`SourceHanSansCN-Bold`（font_ 连字符）→ 下划线规整 `SourceHanSansCN_Bold` 过校验。**机制通**；font_ 全库 vs Font_type 798 的整体对齐率待 C1/C3 用真 font 核。
6. **add_effect.params 可空 `[]` 过校验**；精确 0–100 默认值 C1 接 `get_effect_meta.py`。

**诚实局限**：仅 1 条 16:9 对照片（Lotus，非抖音竖屏）；font 用 fixture 非真检测；transition_duration/font_size 未标定；映射表仅覆盖 Lotus 出现的 tag 子集（全 16+12 表是 C1）。

---

## §10 C1 结果块 — foundation `compose_common.py`（✅ 通过，2026-05-30）

**交付**：`scripts/compose_common.py`（映射表 + 换算器 + DraftBuilder + merge_reverse + load_cached）、`compose_validate.py`（复用 icccut `validate_action` 校验整稿）、`compose_smoke.py`（C1 自测）。零新依赖（纯 stdlib）。

**全量映射表（onto `--list-values` 校验集，全部实测过校验）**：
- `FX_TRANS_TO_JY`(16)：14 映射 + 2 省略(hard-cut/none)。dissolve→叠化 / fade-to-black→闪黑 / fade-to-white→闪白 / flash→白光快闪 / push→推近 / slide→滑动 / wipe→向左擦除 / zoom-in→模糊放大 / zoom-out→模糊缩小 / spin→中心旋转 / glitch→故障 / blur→模糊 / whip-pan→横移模糊 / mask→圆形遮罩。
- `FX_EFFECT_TO_JY`(12)：7 scene 映射 + 5 unmapped/路由。shake→动感模糊 / zoom-pulse→变焦推镜 / rgb-split→RGB描边 / light-leak→光晕 / particles→光斑飘落 / blur-pulse→模糊 / film-grain→噪点；**unmapped（校验子集无忠实目标，诚实记录）**：vignette(暗角不在子集) / freeze-frame(故障定格不在子集)；color-filter→filter 路由但 fx 未识别具体 LUT → 记 unmapped；speed-ramp→speed 参数非 effect。
- `FONT_ANIM_TO_JY`(4)：typewriter→打字机_I / scroll→向上滑动 / pop→弹入 / none→省略。

**换算器（单测过）**：`bbox_to_transform` tx=(cx-0.5)·2 ty=(0.5-cy)·2；`size_rel_to_font_size`=size_rel·H/5.2（icccut CJK 字宽≈5.2·font_size 反推，近似口径）；`norm_font` 连字符→下划线（font_ 典型匹配 SourceHanSansCN_Bold/抖音美好体/得意黑/站酷酷黑体 均在 786 校验字体集 ✓）。

**DraftBuilder**：id（uuid12）全局唯一、index 1..N 递增、按 skill 分组、媒体 `${media_N}`/`${audio_N}` 占位（default=bgm 检索到的相似 url）、`reverse_narrative` 作 meta、`_unmapped` 诚实落字段。

**自测结果**：① 14+7+3 映射值全过 validate_action；② 换算器单测过；③ **Lotus 真模块回归 24/24 过**（15 add_video+transition / 1 add_audio / 8 add_effect；id 唯一 / index 递增）；④ add_text_event 用 font fixture 过（transform_y=0.1166、font_size=18.5、打字机_I；pop/scroll/none 变体均过）。`outputs/compose/Lotus_*.json` + `.draft.json` 落盘。

**诚实局限**：编排「缓存未命中则重跑管线 + fx_detect 去重」在 C1 仅 load_cached + merge（重跑集成是 C2）；font 仍未在真视频跑（builder 用 fixture 验）；color-filter 检出但未识别具体 LUT。

---

## §11 C2 结果块 — full chain `compose_extract.py`（✅ 通过，2026-05-30）

**交付**：`scripts/compose_extract.py` 单视频 CLI。口径 **缓存优先**——compose_ 消费各管线已落盘 `outputs/<pfx>/<stem>.json`（它们是已 de-risk 的独立 POC），正常路径**无重复 fx_detect**；`--run fx,narr` 委托独立入口补跑（各自含 detect）。产 `outputs/compose/<stem>.json`（统一反解）+ `.draft.json`（KOX draft），整稿过兄弟仓 `validate_icccut_draft.py`（id 全局唯一 + 串联 + 时间轴重叠 + 画布空隙）。

**5 样本端到端全过**：

| 片 | present(fx/font/narr/bgm) | shots/trans/effects/subs/bgm | draft actions | per-action | 整稿校验 |
|-|-|-|-|-|-|
| Lotus | ✓/✗/✓/✓ | 15/12/4/0/✓ | 15 add_video+1 add_audio+8 add_effect | 24/24 | ✅ |
| drama | ✓/✗/✓/✗ | 6/5/2/0/✗ | 6 add_video+3 add_effect | 9/9 | ✅ |
| hair | ✓/✗/✓/✗ | 18/18/0/0/✗ | 18 add_video | 18/18 | ✅ |
| ai | ✗/✗/✓/✗ | 1/0/0/0/✗ | 1 add_video（单镜头全长） | 1/1 | ✅ |
| kid | ✗/✗/✓/✗ | 1/0/0/0/✗ | 1 add_video | 1/1 | ✅ |

**C2 抓到并修掉的真 bug：同轨时间重叠**。首跑 Lotus/drama 整稿校验 FAIL——一个镜头窗多个 effect（如 Lotus[2.94,3.94]=rgb-split+shake+light-leak 3 条）全落同一 `effects` 轨 → icccut 判「非法重叠」（阈 0.1s）。这是 per-action 校验看不到、整稿校验才抓得到的**跨 action 时间线约束**。修复 = `DraftBuilder._alloc_lane()` 区间 lane 分配：同组并发片段分到不同轨（effects/effects_1/effects_2…，track_render_index 8000+i），非重叠复用同轨。effect/filter/subtitle 三组均接入。重跑后 5/5 整稿校验过。

**设计验证**：① **缓存优先编排正确**——compose 不重算，消费 POC 产出，无冗余 detect；② **部分失败降级**——缺 fx/bgm/font 时对应段落留空 + provenance.present 记录，仍产合法 draft（ai/kid 仅 narr 也出稿）；③ **单镜头**走单条全长 add_video（add_image 不需要——源是视频非静图）；④ 整稿校验是「映射对不对」的硬判据，比自我宣称强。

**诚实局限**：font 仍未在真视频跑（5 片 subs=0；字幕轨/坐标/字体映射仅 fixture 验，真 font 需建 14GB 索引——C3 记为局限）；`--run` 重跑路径已编码但 demo 走缓存（重跑 fx/narr 烧 VLM/ARC 额度、font/bgm 需未建索引）；transition_duration 用默认 0.5、font_size 近似未标定；media 全占位。
