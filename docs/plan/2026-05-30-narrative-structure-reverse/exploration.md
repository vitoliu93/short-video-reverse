# Exploration log: narrative-structure reverse (`narr_`)

> 时间顺序记录关键发现/试错。供 review + 未来复用。

## ARC 任务 I/O（vendor 仓库 + paper + 实测核对）
- 请求：multipart POST，字段 `{prompt, task_type∈{Summary,Segment,Grounding,QA,MCQ}, lang∈{english,chinese}, file}`。
- 响应封套：`response.data[0][0] = [prompt_echo, "[THINK]…[/THINK]\n\n[ANSWER]…[/ANSWER]"]`（API 用方括号标签；本地推理代码用 `<think>/<answer>`，同结构不同分隔）。
- `build_prompt`（vendor/video_inference.py）：**MCQ/Grounding** 在 prompt 内强约束输出（"only option index" / "only time range"）；**Summary/Segment/QA** 共享无约束模板，差异全在用户问题。
- 各任务交付物：
  - **Segment** = 按时间顺序的 `HH:MM:SS - HH:MM:SS 描述` 行（叙事分段骨架）。
  - **QA** = 自由文本，能显式答钩子/结构/意图（叙事最直接来源）。
  - **Grounding** = 单一时间范围（key_moments 来源）。
  - **Summary** = 整体主旨自由文本（含内联时间戳）。
  - **MCQ** = 单字母（评测用，生成不用）。
- ShortVid-Bench 6 维：时序推理定位 / 情感意图 / 创作者意图 / 叙事理解 / 幽默解构 / 创意创新——「叙事理解」正是本管线对口，且模型 THINK 块本就在内部做这套分析。
- 约束：short ≤5min；≤150s 用 1fps，>150s 取 150 帧均匀；max_new_tokens=1024；中文尤强。

## 三层架构（确定性骨架 / ARC 语义 / doubao 合成）选型
- **不让 VLM 编时间戳**：镜头线 + pacing 来自 fx_detect 纯计算（确定性）。ARC 的 Segment 时间是「场景级语义边界」，未必对齐 TransNetV2 镜头边界 → 两套时间都留：`shots[]` 用确定性边界，`acts[]` 用 ARC 语义范围，合成时让 doubao 把 act 往最近镜头边界靠。
- **闭集在 prompt**（沿用 fx 哲学）：hook_type(10)/structure(8)/act_role(8)/pacing_label(5)。doubao 只能从闭集里选，降低主观漂移。
- **缓存即省额度**：arc_call 命中 `outputs/arc/<stem>_<task>.json` 就不打 API。N0→N3 实际只打了真正新增的组合。

## 实测结果（5 片 5 类）
| 片 | 类型 | 镜头 | hook(预测) | structure | pacing | cta |
|-|-|-|-|-|-|-|
| drama_16s | 情景短剧 | 6 | relatable-pain ✅ | parallel-escalation | medium(19) | null ✅ |
| Lotus | 汽车广告(16:9) | 15 | visual-shock ✅ | setup-conflict-twist-end | fast(56) | 标识露出 ✅ |
| ai_19s | 静态AI二创 | 1 | visual-shock ✅ | other | slow(0) | null |
| hair_17s | 剪发改造 | 18 | relatable-pain ◐ | setup-conflict-twist-end | fast(58) | null |
| kid_10s | 六一相册 | 1 | visual-shock ◐ | qijichengzhuan | slow(0) | null |

- **单镜头相册类（ai/kid）**：fx_detect 只给 1 镜头 → pacing 退化 slow/0（正确，画面确实不切）；但 acts 仍由 ARC 语义 Segment 切出 4 段——证明「骨架 ≠ 叙事段落」的解耦是对的：叙事节拍可以在单一长镜头/相册里靠内容推进，而非靠剪辑点。这是设计预期，记入 known-limitations 作为「pacing 反映剪辑节奏，不反映叙事节奏」的口径说明。
- **hook 视觉核验**（开场 contact sheet）：drama/Lotus/ai 三片肉眼确认正确；hair(POV 文案「剪短发只有0次和无数次」)判 relatable-pain 可辩（suspense 也成立）；kid(六一可爱女孩)判 visual-shock 偏重（更接近 cute/aesthetic，闭集里无精确档→落 visual-shock，属闭集粒度局限）。

## 待审（workflow 进行中）
- doubao 合成层的「忠实度」对抗审计：15 agent（5 片 × 3 视角：忠实度/闭集贴合/时间戳一致）只读 ARC 证据+合成 JSON（看不到视频），查幻觉/误贴/时间不一致。结果写入 spec §11。
