# Spec: 短视频「转场/特效」反解 (pipeline `fx_`)

> 沿用 font/bgm 的 spec 写法：§1–§8 是设计与口径，§9+ 是按 X0→X3 顺序追加的里程碑结果块（含 verdict / 量化表 / 设计决策 / 诚实局限）。**动这条管线前先读本文件。**

## §1 Goal / scope
单视频 → `outputs/fx/<stem>.json`，主线是**转场**（镜头间切换），附带 best-effort 的**特效**（镜头内）。输出是「自然语言描述 + 闭集标签 + 剪映类目」的语义层，不绑定剪映特效 ID。当前为实验，证明抖音爆款转场/特效可被结构化拆解。

## §2 与三条已有管线的关键差异
**本管线不需要 `build_index`。** font/bgm 是闭集检索（我们拥有全部 TTF / BGM 库，render-and-compare 或 CLAP+FAISS）。转场/特效我们**不拥有渲染资产**，且需求是 NL 描述 + 标签而非 1:1 匹配 → 这是一个 **VLM 描述/分类任务**，闭集体现在 prompt 里的 **tag taxonomy**，不在 FAISS 索引里。因此管线更短：定位 → 采样 → VLM 描述 → 聚合。

## §3 Module IO contracts
```
video
  │
  ├─[fx_detect]──────────────────────────────► 转场候选窗口 [{t_center, t_start, t_end, src:"transnet"|"ffmpeg", score}]
  │     TransNetV2 边界(渐变召回) ⊕ ffmpeg scene 硬切(精度提示)，并集去重
  │
  ├─ 对每个候选窗口 [fx_common.sample_window] 采样 N 帧(跨边界) ──► jpeg 帧条
  │
  ├─[fx_describe]── 帧条 → agent-vision(SSE) → {transition_present,type,confidence,desc_cn/en,capcut_tags,visual_cues}
  │
  ├─[fx_extract] 视频级聚合：相邻/重复候选去重投票(借鉴 font group_events/best_obs) ──► transitions[]
  │
  └─[fx_describe (effects pass)] 镜头内均匀采样窗口 → VLM 描述特效 ──► effects[]  (best-effort)
                                                                              │
                                                                              ▼
                                                                  outputs/fx/<stem>.json
```

| 模块 | 职责 | 入 → 出 |
|-|-|-|
| `fx_common.py` | **契约**：VLM 调用(SSE 流解析、模型锁定)、闭集 taxonomy + 剪映类目映射、帧采样/窗口工具 | — |
| `fx_detect.py` | 边界检测：TransNetV2 + ffmpeg scene，输出带时间戳的候选窗口 | video → windows[] |
| `fx_describe.py` | 单窗口 N 帧 → VLM → 结构化转场/特效描述（含 thinking） | frames → dict |
| `fx_extract.py` | 单视频端到端入口 + 视频级聚合去重 | video → outputs/fx/<stem>.json |

## §4 输出 JSON schema（X1 定稿，先给草案）
```json
{
  "video": "<stem>",
  "frame": [W, H],
  "duration": 15.0,
  "transitions": [
    {
      "t_start": 4.0, "t_center": 4.2, "t_end": 4.5,
      "type": "glitch",                         // 闭集 tag，见 §5 taxonomy
      "present": true, "confidence": 0.85,
      "description_cn": "...", "description_en": "...",
      "capcut_category": "Glitch",              // 剪映 12 大类之一
      "capcut_tags": ["故障", "glitch转场"],
      "visual_cues": "画面扭曲撕裂色彩偏移...",
      "src": "transnet+ffmpeg", "n_obs": 2,      // 聚合了几个候选
      "model": "doubao-seed-2.0-pro"             // 实际后端(可复现)
    }
  ],
  "effects": [                                   // best-effort，可能为 []
    {"t_start":0.0,"t_end":2.7,"type":"shake","description_cn":"...","confidence":0.6,"capcut_category":"Distortion"}
  ]
}
```
约定（沿用 bgm）：`present` 门控、`null` 表未计算、score 3 位小数、空结果用 `[]` 不省略键。

## §5 Key decisions（本会话确认，勿无新证据推翻）
1. **范围 = 转场为主 + 顺带特效。** 转场是验收主线；特效在同一份 JSON 里做 best-effort 第二遍 VLM 描述（同一个 VLM，边际成本低）。
2. **素材 = 先用 Lotus 跑通管线机制，真实抖音竖屏爆款留到 X3 做代表性评测**（用户提供）。Lotus 是 16:9 汽车广告，非抖音风格，仅验证机制。
3. **定位 = TransNetV2(渐变召回) ⊕ ffmpeg scene(硬切精度)。** 用户选择引入 TransNetV2：抖音内容里渐变转场(叠化/缩放/旋转)是多数，ffmpeg scene 只抓硬切会系统性漏掉它们。TransNetV2 是轻量 CNN，可跑 CPU/mps，符合「API 优先、不上强本地模型」的约束（它只做定位，描述仍走 API）。
4. **VLM = ICC Router `agent-vision`，Anthropic SSE 流式接口。** 端点 `http://115.190.62.224:8001/v1/messages`，base64 image block，必须解析 SSE（非 OpenAI JSON）。**已知坑见 §8。**
5. **闭集转场 taxonomy（prompt 用，→ 剪映 12 大类）**：
   `hard-cut, dissolve, fade-to-black, fade-to-white, flash, push, slide, wipe, zoom-in, zoom-out, spin, glitch, blur, whip-pan, mask, none`
   映射示例：dissolve→Overlay，fade→Basic，flash→Light Effect，push/slide/wipe→Slide，zoom/spin/whip-pan→Camera，glitch→Glitch，blur→Blur，mask→Mask。剪映官方 12 类：Overlay/Camera/Blur/Basic/Light Effect/Glitch/Distortion/Slide/Split/Mask/MG/Social Media。
6. **聚合 = 视频级投票去重。** TransNetV2 与 ffmpeg 在同一处各报一个候选 → 时间近邻(阈值待标定，初值 0.3s)合并，VLM 只对合并后的代表窗口跑一次（借鉴 font 的 group_events/best_obs，避免 per-候选 噪声 + 省 API）。

## §6 Milestones（de-risk-first，X0→X3）
| 里程碑 | 目标 | 交付 | 验收 |
|-|-|-|-|
| **X0** ✅ | 核心假设 de-risk | 探针验证 agent-vision 收图 + 产出结构化转场 JSON | 见 §9（已通过） |
| **X1** | foundation | 锁定 VLM 后端 + schema/taxonomy 定稿 + TransNetV2 装好并实测本机速度；`fx_common.py`+`fx_detect.py` 落地 | TransNetV2 在 15s 片上跑通并打印墙钟；fx_detect 在 Lotus 上输出候选窗口与 ffmpeg cut 基本吻合 |
| **X2** | full chain | `fx_describe`+`fx_extract` 全链路跑通 Lotus + 特效第二遍 + 聚合去重 | `outputs/fx/Lotus_*.json` 生成，transitions[] 非空且字段完整，人工抽查描述合理 |
| **X3** | eval + report | 真实抖音片评测 + spec 结果块 + known-limitations | 转场定位召回 & type 人工准确率达标（阈值此处标定）|

## §7 Directory & script layout
```
scripts/fx_common.py  fx_detect.py  fx_describe.py  fx_extract.py
outputs/fx/<stem>.json
docs/plan/2026-05-30-transition-fx-reverse/   ← 本计划
```
约定：`ROOT = Path(__file__).resolve().parent.parent`；`sys.path.insert(0, ...)`；若引入 torch+faiss 同时 import 则 `os.environ.setdefault("KMP_DUPLICATE_LIB_OK","TRUE")` 置顶（TransNetV2 用 torch，本管线无 faiss，但 detect 脚本仍置顶以防）。

## §8 Risks & open questions
| 风险/未知 | 缓解 / 如何解决 |
|-|-|
| **`agent-vision` 后端路由不固定**：X0 实测同一 alias 被负载均衡到 `kimi-k2.6` 和 `doubao-seed-2.0-code`，并非用户以为的固定 `doubao-seed-2.0-pro`。实验不可复现。 | **X1 第一件事**：在 icccut-agents 找能锁定 doubao-seed-2.0-pro 的别名/参数；若无法锁定，则在输出里记录每次实际 `model`，并在评测时分层统计。 |
| 静态帧丢失运动信息 → 运镜/缩放/甩镜 vs 叠化/闪/故障 易混淆 | N 帧密采样跨边界（已能区分 glitch）；X2/X3 视情况加光流提示图（cv2 Farneback）作为额外 VLM 输入。 |
| TransNetV2 本机 CPU/mps 速度未知；transition IoU 定位偏弱(~0.19)，但召回边界够用 | X1 实测墙钟；定位用「窗口」而非「精确帧」，对偏弱 IoU 不敏感。 |
| 剪映 v6+ draft 加密 | 只产出语义标签层；剪映特效 ID 映射作为独立查表，未来从 v5.9 导出增量补。 |
| VLM 成本/延迟未量化 | X3 估算 token / 调用次数 / 墙钟。 |

---

## §9 X0 结果块 — 核心假设 de-risk（✅ 通过，2026-05-30）

**目的**：在投入管线工程前，先证明最大未知——「VLM 看几帧能不能产出有用的结构化转场描述」+「agent-vision 端点到底能不能收图」。

**方法**：throwaway 探针 `/tmp/probe_doubao_vision.py`。ffmpeg 从 Lotus(1080p/25fps/15s) 抽帧 → base64 → POST `http://115.190.62.224:8001/v1/messages`，model=`agent-vision`。两测：(a) 单帧「描述这张图」；(b) 跨 4.2s cut 的 9 帧 [3.8,4.6]@0.1s + 闭集标签 prompt 要 JSON。

**Verdict：API 优先方向成立。** 端点能收 base64 图、返回视觉结果；9 帧喂入能正确产出结构化转场 JSON。

| 测试 | 结果 |
|-|-|
| 端点协议 | 返回 **Anthropic 格式 SSE 流**（`message_start`/`content_block_delta`），**非** OpenAI `choices[]`（修正了前期 recon 的判断）；带 `thinking` 块（扩展推理）。须解析 SSE。 |
| T0a 单帧 | HTTP 200，正确描述「女子透过圆形框架俯视，手指指向镜头」。后端实际 = `kimi-k2.6`。 |
| T0b 9 帧转场 | HTTP 200，输出 `{"type":"glitch","confidence":0.85,"description_cn":"画面故障扭曲撕裂色彩偏移,从车内过渡到高楼","capcut_tags":["故障","glitch转场"],...}`。后端实际 = `doubao-seed-2.0-code`。input_tokens≈1582。 |
| 人工核帧 | 抽 [3.8,4.6] 做 3×3 contact sheet 亲眼确认：确有「扭曲/撕裂 → 新镜头」的失真型转场。glitch 标签**实质正确**（glitch vs distortion vs dispersion 的精确归类属 taxonomy 标定，非可行性问题）。 |

**设计决策（由 X0 得出）**：(1) fx_common 的 VLM 客户端必须解析 SSE 流并分离 thinking/text；(2) thinking 块保留，作为 visual_cues 的来源/审计；(3) **后端路由不可复现是 X1 头号任务**（§8）。

**诚实局限**：仅在 1 条非抖音素材的 1 个 cut 上验证；标签精确度、渐变转场召回、抖音风格代表性均未测——这正是 X1–X3 的事。

---

## §10 X1 结果块 — foundation（✅ 通过，2026-05-30）

**目的**：把 de-risk 变成可复现地基——锁后端、定位器、契约层。

**1. 后端可复现性解决。** `agent-vision` 路由不固定（X0 落到 kimi-k2.6 / doubao-seed-2.0-code）。改走**直连 Ark `https://ark.cn-beijing.volces.com/api/coding` + model=`doubao-seed-2.0-pro` + `VOLC_ARK_API_KEY`**（凭据已在 icccut-agents/.env，原是注释掉的蓝图）。实测：确定性返回 `doubao-seed-2.0-pro` 且**支持图片视觉**。Ark `/api/coding` 仅放行 coding-plan 模型——`doubao-1.5-vision-pro` / `doubao-vision-pro-32k` 均 404 UnsupportedModel。协议 = Anthropic Messages SSE；**Ark 不声明 charset → 必须强制 UTF-8**，否则中文 mojibake（已在 `fx_common.vlm` 里 `r.encoding="utf-8"` 修）。

**2. TransNetV2 定位器。** `transnetv2-pytorch` 1.0.5（权重内置 30MB，不依赖 transformers、无冲突）。本机基准（Lotus 15s）：

| device | load | infer | 15s 占比 | 镜头 | 结论 |
|-|-|-|-|-|-|
| **CPU** | 1.86s | **1.78s** | 0.12× | 15 | ✓ 一致 |
| mps | 0.06s | 2.23s | 0.15× | 9 | ✗ 更慢 + 数值不一致漏边界 |

→ **用 CPU**（180s 抖音片外推 ~21s，离线可接受）。`fx_detect.py`：TransNetV2(镜头边界) ⊕ ffmpeg scene(硬切)，近邻 0.3s 合并、按 gap 自适应窗宽。Lotus：15 镜头→**12 候选窗口/3.38s**，其中 2 个 transnet-only(10.94/12.22s) 是 ffmpeg 漏掉的——正是引入 TransNetV2 的价值。

**3. 契约层冒烟通过。** `fx_common.py`(VLM 客户端 + taxonomy + 剪映映射 + 采样) + `fx_describe.py`(stage)。Lotus 4.19 窗口跑 pro：JSON 解析 OK、中文无 mojibake、model 正确记录。

**⚠️ 关键发现（→ known-limitation）：转场 type 标签 model-dependent 且本身有歧义。** 同一个 4.19 转场，doubao-seed-2.0-**code**(X0) 判 `glitch`(扭曲撕裂)，doubao-seed-2.0-**pro**(X1) 判 `wipe`(白色竖条左→右擦除, conf 0.92)。人工看帧：确为「车内铬面 → 高楼」一次带视觉效果的切换，但低分辨率下 wipe/glitch/distortion 难铁定区分。**定位 + "此处有带效果的转场" 跨模型稳健；精确 type 是软的。** 应对：(a) 输出永远记录实际 `model`；(b) X3 固定用确定性的 pro，主指标 = 「转场是否检出 + type 家族是否合理」，精确 tag 命中为辅；(c) tag 命中口径在 X3 标定。

**设计决策**：schema 以 `fx_describe` 实际产出为准（比 §4 草案多 `type_cn`/`_parse_ok`/`_raw_type` 审计字段）；type 不在闭集时落 `"unknown"` 并保留 `_raw_type`。

**诚实局限**：仍只在 Lotus(非抖音)上验证；聚合去重、特效遍、真实抖音召回/准确率属 X2/X3。
