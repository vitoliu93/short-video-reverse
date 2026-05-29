# Todo: 字体 + 样式识别

## Current State  ← 这是 resume 游标，开工/收尾/交接前必须更新
- **Phase**: F1 — 字体参考索引 + OCR 前端
- **Status**: in_progress (F0 ✅ 已通过并提交)
- **Branch**: dev-plan-2026-05-29-font-style-recognition
- **Last done**: F0 通过 —— 148 款 CJK 合成集 combo 退化 NCC top-1=0.97/top-5=0.99(随机 0.034)；gallery.png 肉眼确认是真形状判别。口径锁 NCC，**不需专训/embedding**。结果落 spec §9
- **Next**: F1 — (1) `font_build_index.py` 流式建全库参考索引；(2) OCR 前端 ffmpeg 抽帧+RapidOCR 在真实帧出 crop+字符串
- **Blockers**: none。踩坑：`.venv-font/bin/python` 直跑，别 `uv run --python`

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

### F1 — 地基：字体参考索引 + OCR 前端  [todo]
- [ ] `font_build_index.py`：流式（下载→渲染/embedding→删）建全库或 CJK 子集参考索引 → `outputs/font_index/`
- [ ] `font_common.py`：锁定渲染/归一化/相似度口径（类比 bgm_common.py）
- [ ] OCR 前端：ffmpeg 抽帧 + RapidOCR → 真实帧上产出 text + bbox + char_boxes + 干净 crop
- **Acceptance**: 索引覆盖 N 款字体可检索；OCR 在一张真实字幕帧上产出可用 crop 与字符串
- **Verify**: 建索引脚本跑完打印覆盖数；OCR 脚本对一帧输出 bbox+text，肉眼/可视核对 crop 正确  → **Result**: pending

### F2 — 全链路：font_extract.py  [todo]
- [ ] `font_extract.py`：video → 抽帧 → OCR → [字体匹配 ‖ 颜色/修饰 ‖ 字重/字号 ‖ 位置 ‖ 动画] → texts[] JSON
- [ ] 四维样式模块（颜色与修饰 / 字重字号 / 位置 / 动画），复用 F0/F1 件
- **Acceptance**: 一条真实抖音片段端到端跑出 schema(spec §1) 的 texts[] JSON，字段非空且自洽
- **Verify**: `.venv-font/bin/python scripts/font_extract.py <video>` → 产 `outputs/font/<name>.json`，逐字段核对  → **Result**: pending

### F3 — eval + 报告（POC done-line）  [todo]
- [ ] 采集/获取 3–5 条真实抖音样本（agent 先试下载，被挡则向 vito 要链接/文件）到 `assets/eval_videos/`
- [ ] 批量跑 `font_extract.py` 出每条 JSON；样式属性对眼标核对；字体匹配视觉合理性判定
- [ ] 合成集精度表（top-1/top-5、退化曲线）作为字体精度量化依据
- [ ] 写结论：闭集匹配行不行 / 精度 / 成本 / 推荐生产方案 / 降级路径（落 spec §9 或独立 findings 段）
- **Acceptance**: 每条真实样本有 JSON + 结果表；有一段可引用的「推荐方案」结论
- **Verify**: 产物齐全（JSON×N + metrics 表 + 结论段），vito 过目  → **Result**: pending
