# Spec: 短视频「整体叙事结构」反解 (pipeline `narr_`)

> 沿用 font/bgm/fx 的 spec 写法：§1–§8 是设计与口径，§9+ 是按 N0→N3 顺序追加的里程碑结果块（含 verdict / 量化表 / 设计决策 / 诚实局限）。**动这条管线前先读本文件。**
> 状态：**N0/N1/N2/N3 ✅ 全过（见 §9/§10/§11），POC 完成**。更新：2026-05-30。

## §1 Goal / scope
单视频 → `outputs/narr/<stem>.json`，输出**叙事/脚本结构**的结构化描述：开场钩子类型、叙事结构（分幕及功能）、节奏画像、逐镜头内容、内容标签、情感曲线、关键时间点。是「自然语言摘要 + 闭集标签 + 确定性节奏指标」三层混合，服务 KOX eval Gold Case 的 `narrative{}` 字段。当前为实验，证明抖音短视频的叙事结构可被反解并结构化。详见 `goal.md`。

## §2 与前 4 条管线的关键差异
| | font / bgm | fx | **narr（本管线）** |
|-|-|-|-|
| 范式 | 闭集检索(我们拥有资产) | VLM 描述+闭集标签 | **AVI 编排**：确定性骨架 + 多任务 VLM 语义 + 合成层 |
| 需 build_index? | 是 | 否 | **否** |
| 主后端 | 本地(CLAP/render) | doubao(Ark) 视觉 | **ARC-Hunyuan hosted API**(理解) + doubao(合成) |
| 闭集在哪 | FAISS / TTF 库 | prompt taxonomy | prompt taxonomy（hook/structure/role） |
| 确定性 | 高 | 定位确定/type 漂 | **骨架(镜头线+pacing)确定**；语义(ARC/doubao)非确定 |

narr 是「整体编排 / AVI 范式」（调研文档 §6）的最小落地：**Plan**（已知镜头线）→ **Invoke**（ARC 多任务）→ **Synthesize**（doubao 收敛进闭集 schema）。它**不重做** font/bgm/fx 已覆盖的字幕/BGM/转场，只在 narrative 层引用结论。

## §3 Module IO contracts
```
video
  │
  ├─[fx_detect]（复用）───────────────► 确定性镜头时间线 shots[] + 时长/边界
  │       │
  │       └─[narr_pacing]────────────► pacing_profile{n_shots, avg_shot_s, std, cuts_per_min, label, fastest_window}（纯计算，确定性）
  │
  ├─[narr_arc]── 上传视频 → ARC short-video API 多任务（带磁盘缓存，省额度）
  │       Summary（主旨/描述）+ Segment（带时间戳分段）+ QA（钩子+结构+意图）+ Grounding（关键时刻时间范围）
  │       每个 response.data[0][0] = [prompt, "[THINK]…[/THINK]\n\n[ANSWER]…[/ANSWER]"] → 解析出 think/answer
  │
  ├─[narr_synth]── (ARC 四任务 answer 文本 + 镜头线 + pacing) → doubao(Ark) → 闭集 narrative JSON
  │       hook_type∈闭集, structure(acts[] 每幕 role∈闭集 + 时间范围 + 一句话), theme, cta,
  │       emotion_curve[](带时间戳), key_moments[](带时间戳), content_tags[]
  │
  └─[narr_extract] 视频级聚合 + provenance 标注 ──► outputs/narr/<stem>.json
```

| 模块 | 职责 | 入 → 出 |
|-|-|-|
| `narr_common.py` | **契约**：ARC 客户端(+缓存+THINK/ANSWER 解析)、闭集 taxonomy、pacing 计算、doubao 合成客户端(复用 fx_common)、合成 prompt 模板、schema | — |
| `narr_arc.py` | ARC short-video 多任务调用 + 缓存到 outputs/arc/ + 解析 | video → {summary, segment, qa, grounding}(各含 think/answer) |
| `narr_extract.py` | 单视频端到端入口：detect → pacing → ARC → synth → 写 JSON | video → outputs/narr/<stem>.json |

（`narr_arc` 可并入 `narr_common`；若文件过大再拆。先以 common+extract 两文件起步。）

## §4 输出 JSON schema（N1 定稿草案）
```json
{
  "video": "<stem>",
  "duration": 16.0,
  "n_shots": 8,
  "narrative": {
    "hook_type": "relatable-pain",          // 闭集，见 §5
    "hook_desc_cn": "用'坐久了站起来'这种人人有共鸣的日常动作开场",
    "structure": "parallel-escalation",     // 闭集叙事结构模式
    "acts": [
      {"role": "hook", "t_start": 0.0, "t_end": 3.0, "summary_cn": "坐久了站起来,腰酸脖子疼"},
      {"role": "escalation", "t_start": 3.0, "t_end": 11.0, "summary_cn": "吹风/上厕所,体感递进夸张"},
      {"role": "climax", "t_start": 11.0, "t_end": 16.0, "summary_cn": "拉开窗帘爆炸特效,情绪顶点"}
    ],                                       // role∈闭集 ACT_ROLES；时间范围对齐镜头线
    "theme_cn": "幽默调侃两广人潮湿天气下的生活状态",
    "cta": null,                             // 有则填(关注/点赞/购买…)，无则 null
    "pacing_profile": {                      // 确定性，来自镜头线
      "avg_shot_s": 2.0, "std_shot_s": 0.8, "cuts_per_min": 30.0,
      "label": "medium-fast", "fastest_window": [11.0, 16.0]
    }
  },
  "shots": [ {"shot_id":0,"start":0.0,"end":3.0,"dur":3.0,"summary_cn":"..."} ],
  "content_tags": ["剧情","幽默","生活共鸣"],
  "emotion_curve": [ {"t":1.5,"emotion":"无奈","valence":-0.3},
                     {"t":13.5,"emotion":"崩溃","valence":-0.8} ],   // 带时间戳
  "key_moments": [ {"t_start":12.0,"t_end":15.0,"label":"情绪转折/高潮","src":"grounding"} ],
  "provenance": {                            // 每个软字段来自哪 + 实际 model，可复现
    "shots": "fx_detect(transnet+ffmpeg)",
    "pacing": "computed",
    "narrative": "doubao-seed-2.0-pro",
    "arc_tasks": ["Summary","Segment","QA","Grounding"],
    "arc_model": "ARC-Hunyuan-Video-7B"
  }
}
```
约定（沿用 bgm/fx）：`present`/`null` 语义清晰、空结果用 `[]` 不省略键、score 3 位小数、时间戳单位秒。

## §5 Key decisions（本会话确认，勿无新证据推翻）
1. **POC = 叙事结构（用户本会话从 3 个未开始候选里选定）。** 镜头切分已在 fx_detect、字幕已在 font_ 覆盖，narr 不重做。
2. **三层架构：确定性骨架 + ARC 语义 + doubao 合成。** 镜头线/节奏必须确定性（来自 fx_detect 纯计算），不让 VLM 编时间戳；叙事语义靠 ARC（专门面向抖音的理解模型）；闭集收敛靠 doubao（沿用 fx 的「VLM 描述、闭集在 prompt」哲学，复用 fx_common 的 Ark 客户端）。
3. **ARC 调 4 个任务：Summary + Segment + QA + Grounding。** N0 实测：Segment 给带时间戳分段、QA 给钩子+结构+意图、Grounding 给关键时刻范围、Summary 给主旨。**全部带磁盘缓存**（outputs/arc/<stem>_<task>.json 存在则复用），re-run 不烧额度。免费额度 ~100，每片 4 调用 → N0–N3 总控 ~20 内。
4. **lang=chinese**（抖音中文内容；ARC 支持 english/chinese）。
5. **闭集 taxonomy（prompt 用）**：
   - `HOOK_TYPES`：`relatable-pain（痛点共鸣）, suspense（悬念设问）, conflict（冲突对立）, visual-shock（视觉冲击）, benefit-promise（利益承诺）, contrast（反差）, authority（权威背书）, story-immersion（剧情代入）, direct（开门见山）, none`
   - `NARRATIVE_STRUCTURES`：`setup-conflict-twist-end（铺垫-冲突-反转-结尾）, parallel-escalation（并列递进）, problem-solution（问题-解答）, hook-proof-cta（钩子-论证-号召）, qijichengzhuan（起承转合）, chronological（流水账/顺叙）, list（清单罗列）, other`
   - `ACT_ROLES`：`hook, setup, conflict, escalation, twist, climax, resolution, cta`
   - `EMOTION` valence ∈ [-1,1]，标签自由中文短词；`PACING_LABELS`：`slow, medium, medium-fast, fast, hyper-cut`
6. **pacing 确定性指标口径**：avg/std 镜头时长、cuts_per_min=n_cuts/duration*60、fastest_window=滑窗内 cut 密度最高的区间。label 由 cuts_per_min 阈值映射（标定见 §10 N1）。

## §6 Milestones（de-risk-first，N0→N3）
| 里程碑 | 目标 | 交付 | 验收 |
|-|-|-|-|
| **N0** ✅ | 核心假设 de-risk | 探针在真实抖音上跑 ARC Segment/QA/Grounding，证明能产出带时间戳叙事素材 | 见 §9（已通过） |
| **N1** | foundation | `narr_common.py`：ARC 客户端+缓存+解析、闭集 taxonomy、pacing 计算、doubao 合成客户端、schema 定稿；pacing label 阈值标定 | narr_common 各部件单测通过；pacing 在 Lotus/drama 上数值合理 |
| **N2** | full chain | `narr_extract.py` 端到端跑通 Lotus + 1 douyin | `outputs/narr/<stem>.json` 生成，字段完整，acts 时间戳与镜头线/Segment 对得上，人工抽查合理 |
| **N3** | eval + report | douyin_* 评测 + spec 结果块 + known-limitations + 登记 CLAUDE.md | hook_type 正确 & 幕划分合理 & pacing 与肉眼一致（阈值此处标定）|

## §7 Directory & script layout
```
scripts/narr_common.py  narr_extract.py   (+ narr_arc.py 视体量决定是否拆)
outputs/narr/<stem>.json
outputs/arc/<stem>_<task>.json            ← ARC 原始响应缓存(复用 test_arc_api 的命名)
docs/plan/2026-05-30-narrative-structure-reverse/   ← 本计划
```
约定：`ROOT = Path(__file__).resolve().parent.parent`；`sys.path.insert(0, ...)` 以 import fx_detect/fx_common；引入 torch(经 fx_detect/transnet) 则 `os.environ.setdefault("KMP_DUPLICATE_LIB_OK","TRUE")` 置顶。

## §8 Risks & open questions
| 风险/未知 | 缓解 / 如何解决 |
|-|-|
| **ARC 免费额度 ~100 次**，烧完即停 | 全任务磁盘缓存(复用即不重调)；每片 4 调用；N0–N3 总控 ~20；脚本支持 `--tasks` 子集 |
| ARC 输出是自由文本(THINK/ANSWER)，非 JSON | doubao 合成层把自由文本+镜头线收敛进闭集 schema；THINK 块保留作 provenance/审计 |
| ARC 给的时间戳是「场景级」语义边界，未必对齐 TransNetV2 镜头边界 | acts 用 ARC 的语义时间范围；shots[] 用 fx_detect 确定性边界；合成时让 doubao 把 act 对齐到最近镜头边界，两套时间都保留 |
| 叙事结构是主观判断，无客观 ground-truth | N3 用人工判定「多数合理」而非精确率；hook_type/structure 用闭集降低主观漂移；必要时对 hook_type 做 k 投票(同 fx) |
| ARC/doubao run-to-run 漂移 | 软字段标 provenance + 实际 model；关键标签(hook_type)可选 k 投票；骨架(镜头/pacing)完全确定不受影响 |
| Lotus 是 16:9 汽车广告非抖音风格 | 仅用于跑通机制；代表性评测在 N3 用 douyin_* 真实竖屏 |

---

## §9 N0 结果块 — 核心假设 de-risk（✅ 通过，2026-05-30）

**目的**：在投入管线工程前，先证明最大未知——「ARC-Hunyuan 的 Summary 之外的任务(Segment/QA/Grounding)能不能在**真实抖音**上产出**带时间戳的、可结构化的叙事素材**」。Summary 早有(outputs/arc Lotus)，但只是整体描述；叙事结构需要分段+钩子+结构+关键点。

**方法**：throwaway 探针 `/tmp/narr_n0_probe.py`，复用 `test_arc_api.analyze_video`，对真实抖音短剧 `assets/douyin_drama_16s.mp4`（16s，4 场景情景短视频）调 3 个任务（lang=chinese），打印原始 `response.data` 结构并存盘。

**Verdict：三层 AVI 方向成立。** ARC 在真实抖音上对每个叙事任务都给出了**准确、带时间戳、已半结构化**的素材，doubao 合成层有充足原料收敛进闭集 schema。

| 任务 | 调用结果（douyin_drama_16s） |
|-|-|
| **Segment** | 正确切成 4 段并各带时间范围 + 一句话：场景1`00:00:00-00:00:03`坐久了站起来 / 场景2`00:00:03-00:00:06`出去吹风 / 场景3`00:00:06-00:00:11`上厕所 / 场景4`00:00:11-00:00:15`拉开窗帘(爆炸特效结尾)。→ 叙事分段骨架 ✅ |
| **QA** | 显式答出**钩子**(「开场'坐久了站起来'极日常 relatable」) + **结构**(「遵循铺垫-冲突-反转-结尾」并逐条展开) + **意图**(「反差夸张制造喜剧,娱乐观众」)。→ hook_type/structure/theme 原料 ✅ |
| **Grounding** | 对「情绪最强烈/关键转折」查询返回单一时间范围 `00:00:12 - 00:00:15`(ANSWER 仅时间范围,THINK 给推理)。→ key_moments 原料 ✅ |
| 输出协议 | 统一 `response.data[0][0] = [prompt, "[THINK]…[/THINK]\n\n[ANSWER]…[/ANSWER]"]`；ANSWER 即交付物(Segment/QA 为带时间戳的 markdown,Grounding 为时间范围),THINK 为推理(留作审计/provenance)。code=0/message=Success。 |

**设计决策（由 N0 得出）**：(1) narr_common 必须解析 THINK/ANSWER 并分离；(2) ARC 时间戳是 HH:MM:SS,需 `hms→sec`;(3) ARC 输出已足够结构化,doubao 合成层负责「收敛到闭集 + 对齐镜头线」而非「无中生有」;(4) 4 任务全部缓存到 outputs/arc/,re-run 不烧额度。

**诚实局限**：仅 1 条真实抖音、1 类内容(情景短剧)上验证；hook_type/structure 闭集映射的准确率、不同内容类型(口播/带货/vlog)的代表性、ARC 时间戳与 TransNetV2 边界的吻合度，均未测——这是 N1–N3 的事。ARC 额度已用 4/~100。

---

## §10 N1/N2 结果块 — foundation + full chain（✅ 通过，2026-05-30）

**N1 交付**：`narr_common.py`（ARC 客户端+磁盘缓存+THINK/ANSWER 解析+hms→sec、闭集 taxonomy 10/8/8/5、`compute_pacing` 确定性节奏、复用 fx_common 的 doubao 合成客户端+合成 prompt+schema）。单测：`hms_to_sec` ✓、THINK/ANSWER 分离 ✓、缓存命中 ✓、taxonomy 尺寸 ✓。pacing 阈值（cuts/min）：<12 slow / <24 medium / <40 medium-fast / <80 fast / ≥80 hyper-cut（N1 初值；5 片实测落点合理，见下表）。

**N2 交付**：`narr_extract.py` 端到端（detect→pacing→ARC(缓存)→doubao 合成→写 JSON + provenance + 镜头一句话回填）。Lotus + drama 两类跑通，字段完整、acts 时间戳对齐镜头线。

| 片 | 类型 | 镜头 | duration | pacing(label/cuts·min⁻¹/avg) | 墙钟(全缓存命中) |
|-|-|-|-|-|-|
| drama_16s | 情景短剧 | 6 | 15.7s | medium / 19.1 / 2.59s | ~5s |
| Lotus | 汽车广告(16:9) | 15 | 15.0s | fast / 56.0 / 0.96s | ~6s |

**设计验证**：三层解耦成立——骨架(镜头/pacing)完全确定性，语义(ARC)与收敛(doubao)分离。首跑实测 Lotus 识别 visual-shock 鱼眼开场、drama 识别 relatable-pain，骨架字段稳定。墙钟主要花在 ARC 首调(每任务 10–40s)，缓存命中后仅 detect(~3s)+synth(~3s)。
> 注：合成层的软字段(cta 有无、structure、emotion 点数等)**run-to-run 会漂**（见 §11.4），故此处不固定具体软字段值；只有镜头/pacing/duration 是确定性可复现的。

---

## §11 N3 结果块 — 真实抖音评测 + 对抗审计 + 修复（✅ 实验目标达成，2026-05-30）

**目的**：在 5 条不同类型样本上评测叙事反解质量，用对抗审计找合成层的幻觉/误贴，并诚实记录修复与残留漂移。

**评测集**（5 类，覆盖差异化内容）：drama(情景短剧) / Lotus(汽车广告16:9) / ai(静态AI二创) / hair(剪发改造) / kid(六一相册)。

### 11.1 hook 视觉 ground-truth（开场 contact sheet 肉眼核帧）
| 片 | 最终 hook | 开场画面 | 判定 |
|-|-|-|-|
| drama | relatable-pain | "坐久了站起来"揉脖子 | ✅ 正确 |
| Lotus | visual-shock | 扭曲鱼眼摩天楼 | ✅ 正确 |
| ai | direct | 真人×动漫融合肖像(静态展示) | ✅ 正确(修复前误判 visual-shock) |
| hair | suspense | "剪短发只有0次和无数次"POV 文案设悬念 | ✅ 正确(relatable-pain 亦可辩) |
| kid | direct | 六一可爱女孩比手势 | ✅ 正确(修复前误判 visual-shock) |
**hook 正确率 5/5**（含 2 个可辩；修复后 ai/kid 的 visual-shock 误判已纠正——见 11.3）。

### 11.2 对抗忠实度审计（15 agent = 5 片 × 3 视角，只读 ARC 证据+合成 JSON，看不到视频）
裁判视角：忠实度(查幻觉) / 闭集贴合(查标签是否最优) / 时间戳一致。结果：**0 clean / 14 minor / 1 major（按 verdict）；其中 major-严重度 issue 6 条**——总判读：**无重大幻觉、对 ARC 证据普遍忠实，但合成层有可收敛的标签/措辞漂移**。审计找出的**明确正确**问题：

| 片 | 字段 | 审计发现 | 根因 | 修复动作 |
|-|-|-|-|-|
| kid | hook_type | visual-shock 言过其实(只是可爱非惊吓) | 闭集判定无「visual-shock 仅指突兀/惊吓」定义 | synth prompt 加该定义 → kid/ai 均纠正为 **direct** ✅ |
| kid | structure | qijichengzhuan 无「转」 | 同上 | 加「按实际内容判、勿被措辞带偏」→ **chronological** ✅ |
| ai | emotion_curve | 编造情绪弧线(ARC Grounding 明说"持续轻微") | synth 默认给起伏 | 加「情绪平稳则只给1~2点不编弧线」→ ai 收成单点 valence=-0.6 ✅ |
| drama | structure | parallel-escalation「漏 twist」 | **我的 QA prompt 泄漏框架**「(铺垫/冲突/反转/结尾之类)」诱导 ARC 套用该词 → 污染下游 | QA prompt 去框架化 ✅（见下，但 structure 标签本身受漂移影响，见 11.4） |

**关键根因（按 CLAUDE.md「修根因不埋」）——两处契约级修复，非逐样本硬改**：
1. **QA prompt 去框架化**：旧「整体叙事结构是怎样的（铺垫/冲突/反转/结尾之类）？」→ 新「整体是怎么组织和推进叙事的？」。**验证有效**：去偏后 drama 的 ARC QA 回答**不再出现「铺垫/反转」字样**（实测 `mentions 铺垫/反转: False`），改用「场景序列」中性描述。
2. **synth 契约收紧**：加「只用证据内内容、不编名词」+ visual-shock 定义 + 「情绪平稳不编弧线」+ 「acts 必须首尾相接互不重叠」。

### 11.3 修复中发现并修掉的真 bug：acts 重叠
契约收紧后重跑，**hair/kid 的 acts 出现非单调**（schema 校验 FAIL）：kid 的 `escalation` 与 `hook` 同从 0.0 起（头部重叠）、hair 的 `cta` 嵌在 `resolution` 尾部。根因 = doubao 偶发把特殊节拍(hook/cta)嵌进相邻幕。修复 = `narr_common.normalize_acts()`（确定性后处理：排序→消重叠→丢零宽幅；属对外部非确定 API 输出的规整）。单测两 case 均转单调，重跑后 **5/5 schema 校验全过**。

### 11.4 残留漂移（诚实记录，按 CLAUDE.md「不埋」）
**doubao 合成层的 categorical 标签 run-to-run 漂移仍在**（与 fx_ §11 同源：服务端 token 级非确定，temp=0 不解决）。实测：drama 用**完全相同的缓存 ARC 输入**连跑 3 次，`structure` 漂为 `list / parallel-escalation / parallel-escalation`，而 `hook_type=relatable-pain` **3/3 稳定**、`acts` 角色序列 3/3 稳定。即：**hook_type / acts 结构较稳，structure 这种高层抽象标签最易漂**。磁盘上 drama 落 `structure=list`（末次写入）。
- **缓解**（未在本 POC 落地，留作增强）：对 `hook_type`/`structure` 做 **k=3 多数投票**（同 fx_extract 的 type 投票），可消除该漂移。骨架(镜头/pacing/acts 时间)完全确定、不受影响。

### 11.5 关键设计发现：pacing(剪辑节奏) ≠ 叙事节奏
ai/kid 是**单镜头相册/静态作品**（fx_detect=1 镜头 → pacing=slow/0 cuts），但 acts 仍由 ARC **语义** Segment 切出多幕（ai 7 幕 / kid 3 幕）。证明三层解耦正确：**叙事节拍可在单一长镜头内靠内容推进，与剪辑点无关**。口径：`pacing_profile` 反映**剪辑节奏**（确定性、来自镜头线），叙事推进看 `acts[]`（语义、来自 ARC）。二者独立，勿混用。

### 11.6 最终 5 片产出（落盘快照）
**确定性列**（镜头/pacing/duration——可复现，每次一致）+ **合成层快照**（hook_type/structure/n_acts/cta——doubao 产出，会按 §11.4 漂移；下表是某次落盘值，非可复现保证）：

| 片 | 镜头(确定) | pacing(确定) | hook_type△ | structure△△ | n_acts△ | cta△△ |
|-|-|-|-|-|-|-|
| drama | 6 | medium/19.1 | relatable-pain | list | 5 | 有 |
| Lotus | 15 | fast/56.0 | visual-shock | parallel-escalation | 4 | 无 |
| ai | 1 | slow/0 | direct | other | 7 | 有 |
| hair | 18 | fast/57.9 | suspense | chronological | 5 | 有 |
| kid | 1 | slow/0 | direct | chronological | 3 | 有 |

△ = 较稳（drama 3×探针中 hook_type/acts-角色序列 3/3 一致）；△△ = 最易漂（structure/cta 跨次会变，见 §11.4）。**实验结论看「确定性列稳 + hook 视觉 5/5 正 + 无重大幻觉」，不依赖 △△ 列的具体取值。**

### 11.7 Verdict & 成本
**实验目标达成**：5 类真实/对照样本上，叙事结构(hook/structure/acts/pacing/情绪/关键点)被反解成 **schema 合法(5/5)、对 ARC 证据无重大幻觉、hook 视觉 5/5 正确、人工判定多数合理**的 JSON。三层架构(确定性骨架 + ARC 语义 + doubao 合成)经真实数据验证成立。
- **成本**：每片 4 ARC 调用(免费额度，全缓存复用) + 1 doubao 合成/次。总 ARC 用量 **20/~100**（QA 因去偏重取过一轮）。墙钟：首跑每片 ~45–52s(ARC 首调主导)，全缓存后 ~6s（仅 detect+synth）。
- **诚实局限**：(1) 叙事主观、无客观 GT，"多数合理"是人工判定非精确率；(2) **structure 标签 run-to-run 漂移未根治**，需 k 投票(11.4，本 POC 未做)；(3) hook/structure 闭集粒度有限(如"可爱萌"无精确档→落 direct)；(4) 仅 5 片、均 ≤19s，口播/带货/长片(car_135s)未测；(5) emotion_curve/act 边界是合成层产物经 normalize_acts 规整，非逐帧测量；(6) `acts` 用 ARC 语义时间(对齐到镜头边界)，与 TransNetV2 物理边界的吻合度未量化。
