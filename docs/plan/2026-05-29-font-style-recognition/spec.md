# Spec: 字体 + 样式识别 — 工程规格

> 沿用 BGM 子项目的工作法（见 `docs/BGM-反解-spec.md`）：**先 de-risk 最大未知（F0），再建地基（F1），再串全链路（F2），最后 eval+报告（F3）**。
> 状态：**F0/F1/F2/F3 ✅ 全过（见 §9/§10/§11），POC 完成**。更新：2026-05-29。

---

## 1. 目标与范围

输入视频里的一块**文字区域** → 输出该文字的结构化「字体+样式」描述。核心洞察：**我们拥有全部 TTF**，
所以「字体识别」= **闭集匹配**（render-and-compare），而非开放识别。schema：

```jsonc
"texts": [
  {
    "text": "字幕内容",
    "appear": { "first": 1.2, "last": 4.8 },     // 出现时间窗(秒)
    "bbox_px": [211, 1312, 661, 56],               // 像素 [左上x, 左上y, 宽, 高](最清晰帧 OCR 检测框)
    "bbox": [x, y, w, h],                          // 归一化 0~1(相对画面,分辨率无关)
    "position": "bottom-center",                   // 粗标签(由 bbox 推导, 便于规则)
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
| ~~**F0 验证假设**~~ ✅ | `font_match_smoke.py` | 148 款 CJK 合成集 + 退化探针 | **已通过**（见 §9）。combo 退化下 NCC top-1=0.97/top-5=0.99（随机 0.034）。**模板法(NCC)够用，不需专训/embedding** |
| ~~**F1 地基**~~ ✅ | 字体参考索引 + OCR 前端 | 索引 739 款；OCR 合成帧读回 score0.97 | **已完成**（见 §10） |
| ~~**F2 全链路**~~ ✅ | `font_extract.py` | 2 条合成视频(已知 GT) 端到端 **12/12 属性全对** | **已完成**（见 §10）。真实抖音验证留 F3 |
| ~~**F3 eval + 报告**~~ ✅ | 2 条真实抖音样本结果 + 推荐方案 | 见 §11。v1 投票定 点字玄真宋(65%)、v2 汉仪咪咪体简；视频级投票可用 | **POC 完成**。结论：闭集匹配是正确路线，真实数据需视频级投票聚合 |

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

---

## 9. F0 验证结果（2026-05-29）

**目的：** 戳破最大未知 —— 闭集字形渲染-比对能否在大量近似 CJK 字体里区分出正确字体。
**做法：** 抽样库内 148 款 CJK 命名字体（每 5 款取 1，覆盖全表）。对每款 q：渲染测试字 `我的中国字永三和` →
**施加退化**（模拟视频）→ 当 query；参考 = 每款的**干净**渲染。query 归一化（Otsu 二值→裁 ink bbox→resize 96²）后跟全部 148 款比，看真字体 q 排第几。
脚本 `scripts/font_match_smoke.py` + `font_common.py`，产物 `outputs/font_smoke/`（metrics.json + gallery.html/png）。

### 结论：✅ 通过，闭集 render-and-compare 路线确认，**模板法即可，不需专训/embedding**

**量化（找回率，随机基线 top-5 = 5/148 = 0.034）：**

| 退化 | iou top-1 | iou top-5 | ncc top-1 | ncc top-5 |
|-|-|-|-|-|
| clean | 1.00 | 1.00 | 1.00 | 1.00 |
| downscale(低分辨率) | 0.97 | 0.98 | 0.99 | 1.00 |
| jpeg(q=18) | 1.00 | 1.00 | 1.00 | 1.00 |
| recolor_bg(白字暗彩底) | 1.00 | 1.00 | 1.00 | 1.00 |
| affine(±6°旋转+剪切) | 0.99 | 1.00 | 0.99 | 1.00 |
| **combo(全叠加)** | 0.95 | 0.97 | **0.97** | **0.99** |

combo top-5 是随机基线的 ~29×。gallery.png 肉眼核对：#1 命中真字体，#2~5 是**风格确实相近**的字体（粗配粗、细配细、描边配描边）——是真形状判别，非平凡 bug。

**口径决策（落地到 font_common.py）：**
- 相似度用 **NCC**（归一化互相关）为主、**IoU** 为备；两者都接近天花板，NCC 在 combo 下略胜。
- 归一化：灰度 → Otsu 二值（自动判墨色极性，兼容黑底白字）→ 裁 ink bbox → 等比 resize 96²。
- 逐字比对后按字平均（不是整句比，避免字距污染）。
- **不需要** DeepFont 式专训 CNN、也不需要 DINOv2 embedding 来做核心匹配；~1300 款全库暴力逐字 NCC 算量仍 trivial（1300×8 字×9216 维点积），**粗类预过滤对精度非必需**（留作提速选项）。

**诚实的局限（合成集的「天花板」性质，真实差距留 F2/F3 测）：**
1. **同渲染器假设**：query 与参考都用 Pillow/freetype 渲染。真实视频字来自剪映/抖音的渲染器（hinting、次像素 AA、字形版本可能不同）。affine+recolor+downscale+jpeg 模拟了**成像管线**退化，但没模拟**渲染引擎字形差异**。真正的渲染器-gap 只能在 F3 用真实帧（虽无精确 ground-truth，看视觉合理性）验证。
2. 测的是单字干净渲染再退化；真实 OCR crop 有邻字渗透、基线抖动、非平整背景。F2/F3 会压这些。
3. → 据此为真实帧留两条后手：(a) 若 NCC 在真实帧掉点，上 DINOv2 形状 embedding（对渲染器差异更鲁棒）；(b) 对每条字幕挑最清晰帧、多帧投票。

**附带发现：** 148 款里全部覆盖测试字、全部渲染成功；说明 CJK 命名子集字符覆盖良好，适合做参考库。

---

## 10. F1 + F2 验证结果（2026-05-29）

### F1 地基 ✅
- **索引**（`font_build_index.py`）：扫描本地 CJK 字体 → `outputs/font_index/manifest.jsonl`（739 款，name/file/n_glyphs/common_cover/has_preview）。
  「索引」= 清单 + 本地 TTF + cmap，**不预渲染字形图集**：F0 证明现渲染+NCC 暴力比对算量 trivial，且现渲染能比对查询里实际出现的字符（图集会被固定字表局限）。
- **OCR 前端**（`font_ocr.py`）：ffmpeg 抽帧 + RapidOCR(onnx) → text + bbox + char_crops（CJK 近似等宽，按字数等分 line crop）。
  合成字幕帧读回「今天教你一个小技巧」score 0.97、框位 bottom-center 正确。
- **合成器**（`font_synth.py`）：渲染已知 font/style/animation 的帧/视频（gradient+色块背景 + 描边 + fade/pop/typewriter/scroll + h264 编码），给端到端**有 ground-truth** 的验证。

### F2 全链路 ✅
`font_extract.py`：video → 抽帧 → OCR → **事件聚合**（跨帧同字幕按「文本前缀相容 + 框水平接近」归并，记 appear 窗）→ 每事件挑最清晰帧 → [字体匹配 ‖ 颜色/修饰 ‖ 字重字号 ‖ 位置 ‖ 动画] → `texts[]` JSON。

**验证：2 条合成视频（已知 ground-truth）端到端 12/12 属性全对**

| 属性 | synthA（台北黑体_Bold / 白 / 黑描边 / 底部居中 / typewriter / bold） | synthB（字语叙黑体_常规 / 黄 / 无描边 / 居中大 / pop / regular） |
|-|-|-|
| 字体 | ✅ 台北黑体_Bold (0.91) | ✅ 字语叙黑体_常规 (0.52) |
| 填充色 | ✅ #FEFFFF | ✅ #ECE327(黄) |
| 描边 | ✅ 有(#000,3px) | ✅ 无（假阳性已修） |
| 位置 | ✅ bottom-center | ✅ center-big |
| 字重 | ✅ bold | ✅ regular |
| 动画 | ✅ typewriter | ✅ pop |

**两个关键工程决策（这次验证逼出来的）：**
1. **字重从「匹配到的字体」测，不从退化像素测**：闭集匹配定到字体后，字重是该字体固有属性 → 用 `intrinsic_weight()` 对**干净渲染**测笔宽/字高。阈值由库内名字带「粗/常规/细」的字体标定（bold≈0.115 / regular≈0.068 / thin≈0.049）。先前直接量退化 crop，bold/regular 都误判 thin。**这是闭集框架白送的红利**——识别出字体就免费拿到它的属性。
2. **字号用事件内框高 p75**，不是单帧：pop/zoom 动画下逐帧大小变，单帧会被早期小帧带偏（synthB 一度 size_rel 0.04 → 误判 center 而非 center-big）。

**修掉的 bug / 局限：**
- 描边假阳性：抗锯齿边被当描边。改判据为「连续≥2px、颜色稳定、既不像字也不像背景的色带」，单层渐变边被排除。
- 描边宽度略有偏差（synthA 估 3px vs 真 4px），POC 可接受。
- 字重在**纹理/分段字体**（如全息黑体的横线纹理）上仍会偏 thin —— 那类字「笔画」本就是细线，是已知歧义。
- char_crops 等分假设全角等宽，标点/拉丁混排会错位（spec §8 局限）。
- **合成验证仍是同渲染器**（query 与参考都 Pillow）；叠加了真实 h264 编码/解码 + OCR 切分，比 F0 更接近真实，但**渲染器-gap 的终极验证仍需 F3 真实抖音帧**。

### 进入 F3
全库索引 + 全管线就位。F3 需 3–5 条**真实抖音样本**——自动下载受抖音登录/反爬限制，需 vito 给链接或文件。样本一到即可批量跑 `font_extract.py` + 合成精度表 → 写推荐方案结论。

---

## 11. F3 验证结果 + 推荐方案（2026-05-29）

**素材：** 2 条真实抖音车评竖屏视频（1080×1920，178s / 135s，剪映字幕），vito 提供。全库 737 款候选。
脚本 `font_extract.py`（fps=2）+ `font_eval_gallery.py`（视觉合理性对比图）。产物 `outputs/font/v*.json` + `outputs/font_eval/*_gallery.png`。

### 核心发现：单帧 top-1 在真实数据上有噪声，但**视频级投票**能稳定还原字体

| | v1 老潘说车 | v2 极速马力 |
|-|-|-|
| 主字幕条数（bottom-center, ≥4字） | 84 | 92 |
| top-1 score 中位 | **0.53** | 0.29 |
| top-1 plurality 赢家 | **点字玄真宋 (55/84, 65%)** | 汉仪咪咪体简 (23) / 字由卡酷 (18) |
| top-3 加权投票赢家 | 点字玄真宋 (压倒性) | 汉仪咪咪体简 (82+51 双变体, 压倒性) |
| 填充色 | ✅ 黄 #F6EA17（稳定一致） | ⚠️ 半数 #010102（锁到黑描边，见下） |

**结论：**
1. **闭集匹配在真实抖音上「可用但需聚合」**：单条字幕的 top-1 抖动（尤其 v2，同一视频不同字幕匹配到不同字体），但同一视频用同一款字幕字体 → **按整段视频做 top-K plurality / 加权投票**，赢家干净且一致（v1 点字玄真宋 65%、v2 汉仪咪咪体简）。gallery 肉眼核对：匹配字体与 query 同风格族（v1 重显示体、v2 圆润萌体）。
2. **真实分数显著低于合成**（0.29~0.53 vs 合成 0.5~0.9）—— 渲染器-gap 真实存在（剪映渲染器 ≠ Pillow）。v1(0.53) > v2(0.29)：字体越独特/渲染越接近，分越高。
3. **粗类（黑/宋/圆/手写）比精确字体更稳**：即便 exact top-1 错，候选也都落在正确风格族 → 粗类几乎总对。

### 推荐生产方案
- **字体**：每条字幕 top-K（NCC，免训练）→ **视频级加权投票**定一款 + 给「粗类 + 置信度（投票集中度 × 分数分布）」。不要信单帧 top-1。
- **想再提真实精度**（可选，按 ROI）：~~上 DINOv2 形状 embedding~~ —— **§12 实验已证伪**（DINOv2 在低分辨率/退化下显著更差）。真正路径：视频级投票(已采纳)、字体专训编码器(DeepFont 式)、或选更高清帧。
- **样式**：位置 ✅、动画 ✅、字重（从匹配字体干净渲染测）✅、描边有无 ✅；**颜色**在「文字与背景清晰对比」时 ✅，在「粗描边 + 亮背景」时会锁到描边色（v2 #010102 bug，见局限）。

### 已知局限（诚实记录）
- **颜色极性 bug**：白字/亮底/粗黑描边时，Otsu 把黑描边当少数派墨 → fill 误报黑。修法：fill 从字形掩码**腐蚀后的核心**采样（内部=填充，外环=描边），非简单取少数派。POC 未修，留 v2。
- 单帧 top-1 噪声大（需投票兜底，已给方案）。
- OCR 在 logo/运动图形/水印上有误检（"EMEVA" 之类）；用 position+持续性+分数过滤主字幕。
- 渲染器-gap 拉低绝对分；投票/粗类/embedding 是应对路径。

### POC 结论（done-line）
**闭集「渲染-比对」是 KOX 字体反解的正确路线**：合成集证明上限很高（top-5 0.99），真实抖音上经**视频级投票**能稳定还原字体到「具体字体或同族 + 粗类 + 置信度」，四维样式大部分可用。研究问题（§goal）已回答，POC 可跑、已在真实样本验证。生产化 = 接投票聚合 + 按需上 embedding，不在本 POC 范围。

---

## 12. DINOv2 embedding 实验（2026-05-29）+ 颜色 bug 修复

### 颜色极性 bug 已修
`font_style.extract_style` 重写:不再取「Otsu 少数派墨」(白字+粗黑描边+亮底时会锁到黑描边),
改成「离背景色远 = 字形区,距离变换高 dt = 内部 = 填充」。极性无关。
实测 v2 `哥们喜欢燃油车` fill `#020202`→`#FFFFFF`;synth 12/12 不回归;描边/字重不变。

### DINOv2 实验结论:❌ 不采纳 —— 不如 NCC,且更贵

动机:像素 NCC 在真实抖音分数低(渲染器-gap),试 DINOv2 语义形状特征是否更鲁棒。脚本 `font_embed.py` / `font_match_smoke.py --embed` / `font_rerank_eval.py`。

**合成集(735 款,同渲染器 + 退化)—— DINOv2 在退化下崩:**

| 退化 | ncc t1/t5 | dino t1/t5 |
|-|-|-|
| clean / jpeg / recolor | 0.82/1.00 | 0.82/1.00（持平） |
| **downscale(低分辨率)** | 0.80/1.00 | **0.39/0.65** |
| **combo(全叠加)** | 0.76/0.99 | **0.32/0.53** |

**真实数据(DINOv2 重排 NCC top-12,比视频级投票集中度):**

| 视频 | NCC 集中度 | DINOv2 集中度 |
|-|-|-|
| v1 老潘 | **0.75** (点字玄真宋 12/16) | 0.62 (点字玄真宋 10/16) |
| v2 极速 | 0.24 | 0.29（都很低,样本噪声内） |

**结论:** DINOv2 **不可靠地提升、且在低分辨率下显著更差**。原因:DINOv2 是语义/物体特征,字形被压糊后它眼里「都是个汉字」失去区分力;像素 NCC 还保留笔画结构。真实抖音字幕正是压缩+低分辨率 → DINOv2 在这恰好最弱。**保留 NCC,不上 DINOv2。**

> **修正 §11 的推荐**:§11 曾把「DINOv2 embedding」列为提精度后手 —— **实验证伪了这条**。真正提真实精度的路径应是:(a) 视频级投票(已采纳,有效);(b) 若要更强,做**字体专训编码器**(DeepFont 式、在字体上训练,而非通用 DINOv2);(c) 选更高清的帧 / 超分后再比。通用预训练视觉模型对「细粒度字形 + 低分辨率」这组合不适配。

### 净结论(POC 最终)
闭集 NCC「渲染-比对」+ **视频级投票** 是这个任务的最优性价比方案:免训练、CPU 毫秒级、真实数据上靠投票稳定还原字体到「具体字体/同族 + 粗类 + 置信度」。四维样式可用(颜色 bug 已修)。DINOv2 经实验排除。
