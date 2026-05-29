# Reading List — 高质量视频结构化拆解

> 基于飞书文档：[方案调研](https://ospysvjnc0.feishu.cn/docx/WvYBdkKHMoyYlDxxGFUcvU74nFb) · [评估方案 v2](https://ospysvjnc0.feishu.cn/docx/ElswdqI9EoGlo6xksq2cQThvnPb) · [论文阅读清单](https://ospysvjnc0.feishu.cn/docx/UI9jdrIdRowmt5x4lXicfsr3nHS)
> 更新：2026-05-28

---

## 一、短视频整体理解（最优先）

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 1 | **ARC-Hunyuan-Video-7B** | 论文 + 模型 | [arXiv:2507.20939](https://arxiv.org/abs/2507.20939) · [HF](https://huggingface.co/papers/2507.20939) | 腾讯，专门为抖音/微信视频号短视频理解设计，74.3% 准确率，三模态 + 时间戳 |
| 2 | **EVE: End-to-End Video Text Extraction** | 论文 + 模型 | [arXiv:2503.04058](https://arxiv.org/abs/2503.04058) | 复旦+字节，端到端 VLM 提取字幕文本+时间戳，0.5B/7B 两版本 |
| 3 | **TransNetV2** | 工程工具 | [GitHub](https://github.com/soCzech/TransNetV2) | 镜头切分+基础转场分类，150+ FPS，生产级成熟 |

## 二、BGM / 音频识别

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 4 | **SeekTune** | 工程工具 | [GitHub](https://github.com/SeekTune/SeekTune) | Go 实现 Shazam 算法，经典音频指纹，已知曲库匹配 |
| 5 | **neural-music-fp** | 论文 + 工具 | [GitHub](https://github.com/spotify/neural-music-fp) | ISMIR 2025，Spotify，神经音频指纹，噪声/变速场景更鲁棒 |
| 6 | **CLAP Score** | 模型 | [LAION CLAP](https://github.com/LAION-AI/CLAP) | 文本-音频 embedding 匹配，无需精确曲名，只要风格分类 |

## 三、长视频 / 关键帧提取

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 7 | **VideoMiner** | 论文 | [arXiv](https://arxiv.org/abs/2503.xxxxx) (待确认) | ICCV 2025，树形 RL 从长视频逐层提取关键帧 |
| 8 | **ShotWeaver40K** | 数据集 | 公开数据集 | 镜头排列训练数据 |

## 四、视频评估 — 编辑决策评估 / Agent 架构（第一梯队）

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 9 | **EditDuet** | 论文 | [ACM DL](https://dl.acm.org/doi/10.1145/3721238.3730761) | SIGGRAPH 2025，Adobe Research，Editor + Critic 双 Agent，评估编辑时间线 |
| 10 | **EvalVerse** | 论文 | [arXiv:2605.23271](https://arxiv.org/abs/2605.23271) | May 2026，管线感知评估，26 位作者，"rightness → goodness" |
| 11 | **VideoGen-Eval** | 论文 | [arXiv:2503.23452](https://arxiv.org/abs/2503.23452) | Mar 2025，中科大/腾讯，VLM 二值判断（yes/no），checklist 式评估 |
| 12 | **VISTA** | 论文 | [HF Papers](https://huggingface.co/papers/2510.15831) | Oct 2025，Google Cloud AI / ETH Zurich，三裁判制 + 闭环自改进 |

## 五、视频评估 — 核心评估框架（第二梯队）

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 13 | **VEFX-Bench** | 论文 | [arXiv:2604.16272](https://arxiv.org/abs/2604.16272) | Apr 2026，3 维解耦：指令执行+渲染质量+编辑排他性 |
| 14 | **WorldJen** | 论文 | [arXiv:2605.03475](https://arxiv.org/abs/2605.03475) | May 2026，16 维度 Likert 量表，VLM 达 Spearman 1.0 人类水平 |
| 15 | **VideoJudge** | 论文 | [ICLR 2026](https://iclr.cc/virtual/2026/poster/11610085) | ICLR 2026，小模型 bootstrapping 做大模型评估者 |

## 六、视频评估 — 专项维度（第三梯队）

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 16 | **ETVA** | 论文 | [arXiv:2503.16867](https://arxiv.org/abs/2503.16867) | ICCV 2025，Apple+人大，场景图→原子 QA，Spearman 58.47 |
| 17 | **THEval** | 论文 | [arXiv:2511.04520](https://arxiv.org/abs/2511.04520) | Talking Head 专项，8 指标 85K 视频 |
| 18 | **AIGVE-MACS** | 论文 | [HF Papers](https://huggingface.co/papers/2507.01255) | ICCV 2025 Workshop，分数+自然语言评语 |
| 19 | **IVEBench** | 论文 | [arXiv:2510.11647](https://arxiv.org/abs/2510.11647) | 浙大+腾讯优图+上交，12 指标 |
| 20 | **VBench++** | 论文 | [PubMed](https://pubmed.ncbi.nlm.nih.gov/41247905) | IEEE TPAMI Mar 2026，16 维+T2V+I2V 双支持 |
| 21 | **VGA-Bench** | 论文 | [arXiv:2604.10127](https://arxiv.org/abs/2604.10127) | CVPR 2026，60K+ 视频，三维分类评估 |

## 七、通用方法论

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 22 | **Video-Bench** | 论文 | [GitHub](https://github.com/Video-Bench/Video-Bench) | CVPR 2025，Chain-of-Query，MLLM 统一评估 |
| 23 | **HF Evaluation Guidebook** | 指南 | [GitHub](https://github.com/huggingface/evaluation-guidebook) | LLM-as-Judge prompt 设计方法论 |

## 八、配套工具 & 基础设施

| # | 名称 | 类型 | 链接 | 备注 |
|---|------|------|------|------|
| 24 | **PaddleOCR** | 工程工具 | [GitHub](https://github.com/PaddlePaddle/PaddleOCR) | 字幕 bounding box 检测 → 位置+字号 |
| 25 | **ffmpeg** | 工程工具 | [官网](https://ffmpeg.org/) | 抽帧 + 提取音频 |
| 26 | **CLIP (openai/clip)** | 模型 | [GitHub](https://github.com/openai/CLIP) | 文本-图像 embedding 相似度计算 |
| 27 | **LAION CLAP** | 模型 | [GitHub](https://github.com/LAION-AI/CLAP) | 文本-音频 embedding 相似度计算 |

## 九、内部飞书文档（参考）

| # | 名称 | 链接 |
|---|------|------|
| 28 | 高质量视频结构化拆解 — 方案调研 | [链接](https://ospysvjnc0.feishu.cn/docx/WvYBdkKHMoyYlDxxGFUcvU74nFb) |
| 29 | KOX 视频生成质量评估方案 v2 | [链接](https://ospysvjnc0.feishu.cn/docx/ElswdqI9EoGlo6xksq2cQThvnPb) |
| 30 | 视频质量评估 — 论文阅读清单 | [链接](https://ospysvjnc0.feishu.cn/docx/UI9jdrIdRowmt5x4lXicfsr3nHS) |

---

## 阅读路线建议

```
Phase 1 — 理解问题域
  ├── 先读飞书文档（#28 → #29 → #30）
  └── 再读 ARC-Hunyuan-Video 论文（#1）

Phase 2 — 评估体系设计
  ├── EditDuet（#9）— 评估编辑时间线而非渲染帧
  ├── EvalVerse（#10）— 管线感知评估范式
  ├── VideoGen-Eval（#11）— 二值判断 checklist
  └── VISTA（#12）— Agent 闭环自改进

Phase 3 — 拆解管线实现
  ├── TransNetV2（#3）— 镜头切分
  ├── EVE（#2）— 字幕提取
  ├── SeekTune / neural-music-fp（#4, #5）— BGM 识别
  └── PaddleOCR（#24）+ CLIP（#26）+ CLAP（#27）

Phase 4 — 评估框架深入
  ├── VEFX-Bench（#13）→ WorldJen（#14）→ VideoJudge（#15）
  └── 按需查阅第三梯队专项论文（#16-#21）
```
