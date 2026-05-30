# Review: 短视频「整体叙事结构」反解 (`narr_`)

> 收尾复盘。日期 2026-05-30。状态：POC 完成（N0→N3 ✅），分支待用户决定是否并入 main。

## 做了什么
把调研文档 `docs/高质量视频结构化拆解-方案调研.md` 的**头号结论**（ARC-Hunyuan-Video-7B = 唯一专门面向抖音短视频的开源理解模型）从「只有一个 Summary smoke test」落地为**第 5 条真实反解管线** `narr_`：单视频 → `outputs/narr/<stem>.json`，含 `narrative{hook_type, structure, acts[], theme, cta, pacing_profile}` + `shots[]` + `emotion_curve[]` + `key_moments[]` + `provenance`。

**三层 AVI 架构**（Plan→Invoke→Synthesize）：
1. 确定性骨架：复用 `fx_detect`(TransNetV2⊕ffmpeg) 出镜头线 + `compute_pacing` 纯计算节奏。
2. ARC 语义：hosted API 4 任务(Summary/Segment/QA/Grounding)取带时间戳叙事素材，磁盘缓存省额度。
3. doubao 合成：复用 `fx_common` 的 Ark 客户端，把 ARC 自由文本+镜头线收敛进闭集 schema。

新增文件：`scripts/narr_common.py`、`scripts/narr_extract.py`。**零新依赖**（全复用现有 requests/fx_detect/fx_common）。

## 关键收获
1. **de-risk-first 又一次省时**：N0 先在真实抖音上验证 ARC 非 Summary 任务能产出带时间戳素材，再投工程。一次探针就锁定了「ARC 给料、doubao 收敛」的分工。
2. **修根因、不埋（CLAUDE.md #1）**：对抗审计发现 drama 的 structure 漂——根因是**我自己的 QA prompt 把「铺垫/冲突/反转/结尾」写进了提问**诱导 ARC。改的是 prompt（去框架化），不是给 drama 打补丁。去偏后 ARC 回答实测不再出现该词。
3. **对抗审计值钱**：15 个只读证据、看不到视频的裁判，精准挑出 kid 的 visual-shock 言过其实、ai 的情绪弧线是编的、acts 重叠真 bug。比我自己肉眼复核更狠。
4. **诚实记录残留漂移**：doubao 的高层标签(structure/cta)run-to-run 会变，drama 3× 探针证实 hook_type/acts 稳、structure 漂。没有假装修好——明确写进 spec §11.4 + known-limitations + CLAUDE.md，并给出 k 投票的缓解方向（同 fx_）。
5. **设计副产物**：单镜头相册类(ai/kid)证明 `pacing`(剪辑节奏) ≠ 叙事节奏——叙事节拍可在单一长镜头内靠 ARC 语义推进。这条口径写进 spec，避免下游误用 pacing。

## 做得不够 / 留给未来
- **structure/hook_type 未做 k 投票** → 高层标签仍漂。本 POC 范围是「证明可反解」，稳定性增强留作下一步（spec §11.7）。
- **样本仅 5 片、均 ≤19s** → 口播/带货/长片(car_135s, 需 long-video 端点)未测。
- **acts 时间 vs TransNetV2 物理边界吻合度未量化** → 目前靠 doubao「尽量对齐」+ normalize_acts 规整，没有 IoU 数字。
- **无客观 GT** → 叙事是主观的，评测靠「人工多数合理 + 视觉 hook 核帧 + 对抗忠实度」，非精确率。这是任务本质，不是偷懒。

## 复用提示（下次动 narr_ 前）
- **先读 spec §9–§11**（仓库铁律）。
- 两套凭据缺一不可：`ARC_TOKEN`(本仓库 .env) + `VOLC_ARK_API_KEY`(../icccut-agents/.env)。
- ARC 有免费额度，**默认吃缓存**；`--no-cache` 才烧额度。本 plan 已用 20/~100。
- 改「怎么问 ARC / 怎么收敛」的口径 → 改 `narr_common.py`（NARR_PROMPTS / synth_prompt / 闭集 taxonomy），一处生效。
