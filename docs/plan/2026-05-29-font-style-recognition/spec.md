# Spec: 字体 + 样式识别 — 工程规格

> 沿用 BGM 子项目的工作法（见 `docs/BGM-反解-spec.md`）：**先 de-risk 最大未知（F0），再建地基（F1），再串全链路（F2），最后 eval+报告（F3）**。
> 状态：**F0 待开工**。更新：2026-05-29。

---

## 1. 目标与范围

输入视频里的一块**文字区域** → 输出该文字的结构化「字体+样式」描述。核心洞察：**我们拥有全部 TTF**，
所以「字体识别」= **闭集匹配**（render-and-compare），而非开放识别。schema：

```jsonc
"texts": [
  {
    "text": "字幕内容",
    "appear": { "first": 1.2, "last": 4.8 },     // 出现时间窗(秒)
    "bbox": [x, y, w, h],                          // 归一化 0~1(相对画面)
    "position": "bottom-center",                   // 由 bbox 推导
    "font": {
      "match": "Aa锐甲黑",                          // top-1 库内字体名(文件 stem)
      "score": 0.78,                               // 归一化相似度
      "topk": [ {"name": "...", "score": 0.7}, ... ],
      "coarse_class": "黑体"                        // 粗类(可选, 见 §5.1)
    },
    "color": { "fill": "#FFFFFF", "gradient": false },
    "decoration": { "stroke": {"color": "#000000", "width_px": 3}, "shadow": true },
    "weight": "bold",                              // bold | regular | thin
    "size_rel": 0.052,                             // 文字高 / 画面高
    "animation": "pop"                             // none | fade | pop | scroll | typewriter
  }
]
```

**范围内**：字体闭集匹配（核心研究）+ 四维样式抽取 + 借用 OCR 的 POC 前端 + 合成/真实双轨验证。
**范围外**：见 goal.md「out of scope」（不集成管线、不自研 OCR、不开放集、动画只分类）。

---

## 2. 模块与 IO 契约

```
视频.mp4
  │ ffmpeg 抽帧(字幕变化点附近多帧)
  ▼
frames[]
  │ OCR(RapidOCR) ── 文字检测+识别
  ▼
每条文字: { text, bbox, char_boxes, best_frame_crop }
  ├──────────────┬───────────────┬──────────────┐
  │              │               │              │
(模块 F: 字体)  (模块 S: 样式)  (模块 P: 位置)  (模块 M: 动画)
  │              │               │              │
render-compare  颜色/描边/字重   bbox→对齐位     多帧→入场类型
  │              │               │              │
  └──────────────┴───────┬───────┴──────────────┘
                          ▼
                    texts[] JSON
```

| 模块 | 输入 | 输出 | 工具 | 跑在 |
|-|-|-|-|-|
| **抽帧** | video.mp4 | frames[] | ffmpeg | CPU |
| **OCR**（借用） | frame | text + bbox + char_boxes + crop | RapidOCR(onnx) | CPU |
| **F 字体** | crop + 检测到的字符 | match/topk/coarse_class | 渲染(freetype) + 相似度/embedding | CPU(+GPU 可选) |
| **S 样式** | crop + 字形掩码 | fill/gradient/stroke/shadow/weight/size_rel | opencv + 笔画宽度变换 | CPU |
| **P 位置** | bbox + 画面尺寸 | position | 规则 | CPU |
| **M 动画** | 出现窗内多帧 | animation 类型 | 跨帧跟踪 + 规则 | CPU |
| **离线建库** | tos://.../fonts_effect/* | 字体参考索引(渲染图/embedding) | tos-cli + freetype(+embedder) | CPU(+GPU 可选) |

**契约要点**
- F 模块的输入是 OCR 给出的「字符串 + 裁剪图」；渲染参考时**用查询里实际出现的字符**，比对同字异体最可靠。
- 字体库 14GB/~1300+ 款，离线建库**沿用 BGM 的流式做法**：逐款「下载→渲染/embedding→立即删除」，峰值磁盘≈单文件。
- 真实抖音视频**无可知字体 ground-truth** → 字体精度数字只能由合成集给（§6 F0/F3）。

---

## 3. 核心算法：闭集字体匹配（render-and-compare）

这是研究重点，也是最大不确定性（CJK 字体大量近似：无数黑体/宋体变体）。

**主路线**：
1. **参考渲染**：对每款字体，用 freetype/Pillow 渲染字形。两档：
   - 粗排：每款渲染一组**固定常用字**（或直接用库里现成的 `.preview.png`）→ 全局 embedding/模板，查询无关，建一次。
   - 精排：对 top-K 候选，渲染**查询里实际出现的那几个字**，逐字精比。
2. **归一化**：查询字形裁剪 → 二值化(Otsu/笔画掩码) → 去色、去斜、裁到字形 bbox、缩放到统一尺寸(如 128×128/字)。参考同样处理。
3. **相似度**（F0 横评，从便宜到贵）：
   - 模板基线：二值掩码 IoU / Chamfer 距离 / 归一化互相关（零训练）。
   - 形状 embedding：通用视觉编码器（DINOv2 / open_clip 图像塔）embed 渲染字形 → 最近邻（零训练，先试）。
   - DeepFont 式专训 CNN：最后手段，需要训练。
4. **可选粗类预过滤**（§5.1）：先判黑/宋/手写/圆/书法 → 把 1300 候选剪到一类，再精比，降噪降算量。

**算量不是瓶颈**：渲染几个字 ×1300 款 freetype 毫秒级；1300 向量 NN 也 trivial。**瓶颈是区分度** → F0 先戳破。

---

## 4. 样式抽取（四维，全部在 goal 范围内）

- **颜色与修饰**：从 crop 取字形像素掩码（OCR 掩码 / 笔画宽度变换）。
  - 填充色：掩码内像素 k-means 主色 → HEX；渐变：沿字高的色相/明度方差。
  - 描边：掩码膨胀环（dilate−mask）采样到的对比色 → 描边色 + 宽度（由膨胀量估）。
  - 阴影：偏移方向上的低对比副本。
- **字重与字号**：笔画宽度变换(SWT) → 笔画中位宽；weight = 笔宽/字高比 → bold/regular/thin。size_rel = bbox 高 / 画面高。
- **位置**：bbox 中心相对画面 → {bottom-center, top, center-big, left, right…}。
- **动画**：在「出现窗」内采多帧，跟踪同一 bbox → fade(透明度/对比度斜坡) / pop(尺度斜坡) / scroll(平移) / typewriter(字数增长)。难度最高，噪声大时降级为「静态/动态」。

---

## 5. 关键决策

- **闭集而非开放集** — 我们有 TTF，渲染-比对把世界级难题降为可控检索；这是整个方案成立的前提。
- **OCR 选 RapidOCR(onnxruntime) 而非 PaddleOCR** — 避开 PaddlePaddle 安装地狱；ONNX 轻、跨平台。若中文检测召回不够再回退 PaddleOCR。
- **F0 先用零训练方案**（模板 + DINOv2 embedding） — 不引入训练成本就能判断闭集匹配是否可行；不够再上专训。
- **专用 venv `.venv-font`(Python 3.12)** — 沿用 BGM 教训（系统 3.14 无 torch wheel）。
- **流式建库** — 14GB 不全量落地，逐款下载→渲染→删，沿用 `bgm_build_index.py` 的断点续跑思路。
- **粗类预过滤可选** — VLM(Doubao) 或轻量分类器判大类。F0 **不依赖 VLM**（避免被 creds 阻塞），纯渲染-比对先跑通，VLM 作为后续提速/降噪增量。

### 5.1 字体粗类（可选增量）
若纯检索区分度不足，先判 {黑体, 宋体, 圆体, 手写, 书法, 艺术字} 把候选剪小。判别可走：库内字体按名字/形态预聚类 → 查询归到最近簇。VLM 描述是降级兜底（研究文档现有方案），非首选。

---

## 6. 里程碑（de-risk 优先，对齐 BGM M0→M3 工作法）

| 里程碑 | 交付 | 验收 | 备注 |
|-|-|-|-|
| **F0 验证假设** | `font_match_smoke.py` | 合成集：抽 ~100+ 库内字体渲染短语 → 匹配器 top-1/top-5 找回率**显著超随机**；并做退化鲁棒性探针（JPEG 压缩/降采样/重上色/半透底）后复测 | **最关键**。决定走模板 vs embedding vs 需专训/VLM。不通过则在此调整方案，不硬上 |
| **F1 地基** | 字体参考索引 + OCR 前端 | 全库(或先 CJK 命名子集)渲染索引建成；OCR 在真实帧上产出干净 crop + 字符串 | 流式建库；OCR 借用 |
| **F2 全链路** | `font_extract.py` | 真实抖音片段 → frames → OCR → 字体匹配 + 四维样式 → texts[] JSON(schema §1) | 复用 F0/F1 件，不重复实现 |
| **F3 eval + 报告** | 自采 3–5 真实样本结果 + 合成精度表 + 推荐方案 | 每条样本出 JSON；样式对眼标核对；字体匹配视觉合理性可接受；写「行不行/精度/成本/推荐」结论 | **POC done-line**，不再做管线集成 |

---

## 7. 目录与脚本布局（沿用现有约定）

```
short-video-reverse/
├── docs/plan/2026-05-29-font-style-recognition/   # 本计划(goal/spec/todo/preflight/exploration)
├── scripts/
│   ├── font_common.py          # 共享件:渲染/归一化/相似度口径(类比 bgm_common.py)
│   ├── font_build_index.py     # 离线:拉库→渲染→(embedding)→索引(流式)
│   ├── font_match_smoke.py     # F0:合成集 + 退化探针,验证闭集匹配可行性
│   └── font_extract.py         # 单视频:抽帧→OCR→字体+样式→texts[] JSON
├── assets/fonts/         # tos 拉下来的字体(.gitignore,流式时几乎不留)
│   └── eval_videos/      # 自采真实抖音样本(.gitignore)
├── outputs/
│   ├── font_index/             # 字体参考索引(渲染图/embedding + metadata.jsonl)
│   ├── font_smoke/             # F0 合成集结果(metrics.json + 可视对比 html)
│   └── font/                   # 单视频 texts[] 结果 JSON
└── vendor/              # (如需自托管 OCR/embedder 权重)
```

- 包管理 `uv`；专用 `.venv-font`(3.12)。
- 依赖：`pillow` + `freetype`(渲染)、`fonttools`(字符覆盖/元数据)、`opencv-python`、`numpy`、`scikit-image`、`rapidocr-onnxruntime`(OCR)；`torch` + `open_clip`/DINOv2 仅在 F0 判定模板不够时引入。ffmpeg 抽帧。
- 拉字体走 `tos-cli`(`.claude/skills/tos-cli/bin/tosutil`，凭证 `~/.tosutilconfig`)。
- GPU 可选：embedding 推理可复用 ARC 那台(`scripts/setup-arc-hunyuan-gpu.sh`)，CPU 也能跑（字体场景算量小）。

---

## 8. 风险与开放问题

| 风险/问题 | 处置 |
|-|-|
| **CJK 字体近似度高，闭集区分度不足** | F0 先量化；不足则降级到「top-K + 粗类」粒度而非强求 top-1，或限定到「可区分字体族」粒度 |
| 视频压缩/低分辨率/半透明底毁字形细节 | F0 退化探针先测；F2 对每条字幕**挑最清晰帧**比对；记录质量下限 |
| 艺术字/重装饰字 OCR 切不准 | 记为已知局限；OCR 失败的文字块跳过并标记 |
| 真实抖音字体无 ground-truth | 已定：精度数字靠合成集，真实样本只看「视觉合理性 + 样式眼标」 |
| 库 14GB/~1300+ 款下载 | 流式渲染-删；F0 先用 CJK 命名子集(带 preview 的那批)起步 |
| 粗类预过滤需 VLM creds | `.env` 仅有 `ARC_TOKEN`(ARC-Hunyuan 视频，非通用图像 VLM)；F0 不依赖 VLM，需要时再补 Doubao 视觉 creds |
| 动画分类多帧跟踪噪声大 | 降级为「静态/动态」二分；完整 5 类留 v2 |
| `.preview.png` 仅约半数字体有，且渲染的是固定样字 | preview 只用于**粗排**；精排一律现渲染查询字符 |

**待确认**
1. 真实抖音样本由谁采集：选项写「I source」(本 agent 采)，但抖音下载有反爬/可能要登录。预案：agent 先尝试下载；若被挡，**向 vito 要 3–5 个抖音链接或直接给文件**。F0/F1 不依赖它（用合成集 + 库内字体），不阻塞。
2. 字体匹配「合理性」的人工判定由谁做（agent 自评 + 可选 VLM 交叉，还是 vito 过目）。
3. 字体名是否需回写某库表，还是只落 `outputs/` JSON（POC 阶段默认只落 JSON）。
