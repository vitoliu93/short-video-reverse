# Todo: 字体 + 样式识别

## Current State  ← 这是 resume 游标，开工/收尾/交接前必须更新
- **Phase**: ✅ POC 完成（F0/F1/F2/F3 全过）
- **Status**: DONE — 待 vito 过目 + 可选 /dev-plan review 复盘
- **Branch**: dev-plan-2026-05-29-font-style-recognition
- **Last done**: F3 真实抖音 eval —— 2 条真实视频跑通。**核心结论：闭集匹配是正确路线；真实数据单帧 top-1 有噪声，视频级投票稳定还原**（v1 点字玄真宋 65%、v2 汉仪咪咪体简）。结果+推荐落 spec §11，gallery 已出
- **Next**: 无必做项。可选：(a) 修颜色极性 bug；(b) 上 DINOv2 提真实精度；(c) /dev-plan review 复盘
- **Blockers**: none

## Phases

### F0 — 验证假设：闭集字形渲染-比对能否区分 ~1300 CJK 字体  [done]  ⭐最关键
- [x] 拉 148 款 CJK 命名字体（每 5 款取 1）到 `assets/fonts/`
- [x] 写 `font_match_smoke.py` + `font_common.py`：合成集 top-1/top-5 找回率
- [x] 横评 IoU vs NCC（两者都接近天花板，NCC 略胜；模板法即可，未上 embedding）
- [x] 退化探针：downscale / jpeg / recolor_bg / affine / combo 全测
- [x] 落 `outputs/font_smoke/`：metrics.json + gallery.html + gallery.png
- **Acceptance**: ✅ combo 退化 NCC top-1=0.97/top-5=0.99（随机 0.034，~29×）；gallery.png 确认真形状判别
- **Verify**: `.venv-font/bin/python scripts/font_match_smoke.py`  → **Result**: ✅ 见 spec §9
- **决策门**: ✅ 通过 → F1。口径锁 NCC，不需专训/embedding；粗类预过滤对精度非必需(留作提速)

### F1 — 地基：字体参考索引 + OCR 前端  [done]
- [x] `font_build_index.py`：扫描本地字体 → manifest.jsonl（索引=清单+本地TTF+cmap；不预渲染图集，因现渲染暴力比对算量 trivial）
- [x] `font_common.py`：锁定渲染/归一化/相似度口径（+ intrinsic_weight 干净渲染测字重）
- [x] OCR 前端 `font_ocr.py`：ffmpeg 抽帧 + RapidOCR → text + bbox + char_crops（按字等分）
- [x] `font_synth.py`：合成已知 font/style/anim 的帧/视频，给端到端有 ground-truth 验证
- **Acceptance**: ✅ 索引建成（739 款）；OCR 在合成字幕帧读回文本(score 0.97) + 框位正确(bottom-center)
- **Verify**: `font_build_index.py` + `font_ocr.py synth_frame.png`  → **Result**: ✅

### F2 — 全链路：font_extract.py  [done]
- [x] `font_extract.py`：video → 抽帧 → OCR → 事件聚合(跨帧同字幕) → [字体 ‖ 颜色/修饰 ‖ 字重字号 ‖ 位置 ‖ 动画] → texts[] JSON
- [x] 四维样式 `font_style.py`（颜色/渐变/描边/阴影/字重/字号/位置）+ 动画检测(typewriter/scroll/pop/fade)
- [x] 关键设计：字重从**匹配到的字体**测(非退化像素)；字号用 obs 框高 p75(避 pop 带偏)
- **Acceptance**: ✅ 2 条合成视频(已知 ground-truth)端到端 **12/12 属性全对**；texts[] JSON schema(spec §1) 完整
- **Verify**: `font_extract.py outputs/font/_synthA.mp4` 等 → 逐字段对答案  → **Result**: ✅ 12/12

> 注:F2 用合成视频验证(有 ground-truth);真实抖音验证在 F3。font 匹配 2/2 命中,但通用黑体(字语叙)score 0.52 << 独特字体(全息黑)0.91,预示真实数据上通用字体置信/间距更薄。

### F3 — eval + 报告（POC done-line）  [done]
- [x] 获取真实抖音样本（vito 提供 2 条车评竖屏）→ `assets/eval_videos/`
- [x] 批量跑 `font_extract.py` 出每条 JSON（v1 84 主字幕 / v2 92）
- [x] `font_eval_gallery.py` 视觉合理性对比图（query crop vs top-3 渲染）→ 匹配同风格族
- [x] 视频级 plurality/加权投票 → 稳定字体（v1 点字玄真宋 65%、v2 汉仪咪咪体简）
- [x] 写结论：行不行/精度/成本/推荐/降级（spec §11）
- **Acceptance**: ✅ 2 样本 JSON + gallery + 投票表 + 推荐方案结论齐全
- **Verify**: `font_extract.py` + `font_eval_gallery.py`，结果落 spec §11  → **Result**: ✅ 待 vito 过目

> F3 关键结论：单帧 top-1 在真实抖音上有噪声（中位分 0.29~0.53 << 合成 0.5~0.9，渲染器-gap），但**视频级投票**赢家干净一致、且都落正确风格族。推荐生产 = top-K + 视频级投票 + 粗类/置信度；想再提精度上 DINOv2 embedding。
