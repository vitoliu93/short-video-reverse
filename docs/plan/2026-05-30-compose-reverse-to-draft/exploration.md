# Exploration: compose_

## [session 8ab4fa50 · 2026-05-30] 立项前 recon（两侧映射全摸清）

### 目标侧 = icccut-agents「cutting skills」action-JSON 生态
- **权威参数字典**（非 SKILL.md）：`icccut-agents/docs/ICCCUT_JSON_LANGUAGE.md`（1019 行，§4 含每种 action_type 的实例）+ `draft-manager/scripts/validate_action.py` + 枚举源 `src/capcut_router/pyJianYingDraft/metadata/*.py`。`edit-icccut-draft` 技能明示：字段字面量以这三者为准，**不以 SKILL.md 为参数字典**。
- **draft 形**（实样 `icc_output/icccut_draft.json`，由 reverse-draft 产，draft_id 带 `_reverse`）：
  `{meta, inputs, script:[{skill, skill_type:"core"|"user", actions:[{type:"action", action_type, id, index, params:{...}}]}], jianying_zip_tos_key, video_tos_key, ...}`
- **时间=秒**；transition/animation/effect/font 名=**中文剪映枚举**（实样：`"transition":"向左"`,`"intro_animation":"缩小"`）。
- **生命周期**：`init_draft.py --template T --width --height` → `save_to_draft.py <draft_id> --skill X --action '{json}'`（**自动过 validate_action.py 枚举校验**）→ `icccut_to_jianying_draft.py` 导出。
- **轨道**：`track_name`+`track_render_index`（0=主轨底层；约定：1-100 overlay / 5000-10000 effects / 14000 title / 15000 subtitle / 20000+ 人像前景 / BGM≈1000）。
- **action_type 全集**：add_video, add_image, add_audio, add_text, add_text_template, add_effect, add_filter(走 add-filter 技能), add_sticker, add_video_keyframe。**注意 add_effect ≠ add_filter**：filter=调色 LUT（Filter_type 468 成员），effect=场景/人物特效（Video_scene_effect 913 / character 227）。

### 既有近邻 = `reverse-draft` 技能
- 把剪映工程 `draft_content.json` → `icccut_draft.json`（"有工程文件"路径）。**compose_ = 同目标，但从像素**（无工程文件）。`reverse_draft.py` 的产出结构（material index→tracks→actions→`${media_N}`/`${audio_N}` 占位）可直接镜像。
- 可复用：`substitute_icccut_placeholders.py`（媒体填充）、`text_display_units.py`（文案排版校验）、`scale_to_corner.py`（像素→scale/transform）、`get_effect_meta.py`（effect 默认 params 0–100）、`save_to_draft.py`/`validate_action.py`/`validate_icccut_draft.py`（校验）。

### 目标侧关键闭集（映射 onto 的对象）
- transition：剪映 transition 名 ~370/85（向左/叠化/闪白/闪黑/故障/模糊/中心旋转/横移模糊/鱼眼/放射/向左擦除/...）。12 官方大类：Overlay/Camera/Blur/Basic/Light Effect/Glitch/Distortion/Slide/Split/Mask/MG/Social Media。
- Filter_type：468（赛博朋克/港风/...）。Video_scene_effect_type：913（抖动/模糊/故障/色差/鱼眼/胶片漏光/RGB描边/噪点/暗角/变焦推镜/故障定格/...）。Video_character_effect_type：227。
- Font_type：798（480 free/318 paid）：SourceHanSansCN_Bold/抖音美好体/得意黑/... **标识名用下划线**。
- Text_intro：145（渐显/弹入/打字机_I/向上滑动/缩小/...）。Text_outro 97。Text_loop_anim 93。
- add_text 坐标：transform_x/y **中心原点半画布单位**（0=中心；x:-1左+1右；y:负=下 正=上）。实例 `transform_y=-0.42≈近底`、默认 -0.6。

### 源侧 = 5 反解管线 outputs schema（详见 /tmp/recon_source.md）
- `bgm`: `{bgm:{present,start,end(s),volume_profile{hz,values[]},beat{tempo},style_tags[],match{audio_url(tos://),categories[],score,topk[]}}}`
- `font`: `{video,frame:[W,H],texts:[{text,appear{first,last(s),n_obs},bbox_px[x,y,w,h px 左上],bbox[归一],position,font{match,score,topk},color{fill #RRGGBB,gradient},decoration{stroke{color,width_px},shadow},weight,size_rel(占帧高),animation:none|typewriter|scroll|pop}]}`
- `fx`: `{...,transitions:[{t_start,t_center,t_end(s),gap,present,type(16闭集),type_cn,capcut_category(12类),capcut_tags[],...}],effects:[{t_start,t_end(s),present,types[](12闭集),types_cn[],...}]}`
- `narr`: `{...,narrative{hook_type,structure,acts[{role,t_start,t_end(s),summary_cn}],theme_cn,cta,pacing_profile{avg_shot_s,n_cuts,cuts_per_min,label,fastest_window}},shots[{shot_id,start,end,dur,summary_cn}],content_tags[],emotion_curve[{t,emotion,valence}],key_moments[{t_start,t_end,label,src}],provenance{...}}`
- **去重点**：narr 内部跑 fx_detect 出 shots；fx 也跑。compose 只跑一次 detect 喂两边。

### 映射缺口（= 本计划唯一新增的「知识」，现不存在于任何代码）
1. fx TRANSITION_TAGS(16) → 剪映 transition 名(370)。`hard-cut`/`none`→无 transition。
2. fx EFFECT_TAGS(12) → Video_scene_effect_type/Filter_type。`speed-ramp`其实是 speed 参数非 effect；`color-filter`→走 add_filter。
3. font animation(4) → Text_intro。
4. 坐标换算 bbox(归一左上) → transform（中心半画布）：`tx=(cx-0.5)*2, ty=(0.5-cy)*2`（cx=x+w/2,cy=y+h/2；核 cy=0.71→ty=-0.42 ✓）。
5. font.match 名 vs Font_type：font_ 匹配 TOS 字体库（kox-statics/fonts_effect）是否=剪映 798 库？连字符 vs 下划线、显示名 vs 标识名——C0 核。

### worktree 环境
- gitignore：`.venv`/`assets/`/`outputs/`（仅 `outputs/arc` force-track，29 文件 ARC 缓存）。
- 已 symlink 主 checkout 的 `.venv`/`assets`/`outputs/{fx,narr,bgm,bgm_index,bgm_smoke}`；nested-link 坑已清；symlink 加进 `.git/info/exclude`。
- C0 候选：**Lotus**（fx+narr+bgm 全；16:9 非抖音，仅跑通机制）；drama/hair（fx+narr）。outputs/font 空、字体索引未建 → C0 用 fixture。
