# Todo: 字体 + 样式识别

## Current State  ← 这是 resume 游标，开工/收尾/交接前必须更新
- **Phase**: F0 — 验证闭集字体匹配可行性
- **Status**: todo (计划刚立，preflight 未跑)
- **Branch**: dev-plan-2026-05-29-font-style-recognition
- **Last done**: 立项 — goal/spec/preflight/todo 已写；worktree 已建（从本地 HEAD，含研究文档+BGM 脚本）
- **Next**: 跑 preflight（建 `.venv-font`、装依赖、验证能从 TTF 渲染字形、ffmpeg/OCR 可用、拉一小批 CJK 字体），然后开 F0
- **Blockers**: none（真实抖音样本采集是 F3 才需要，不阻塞 F0/F1）

## Phases

### F0 — 验证假设：闭集字形渲染-比对能否区分 ~1300 CJK 字体  [todo]  ⭐最关键
- [ ] 从库里拉 100~200 款 CJK 命名字体（带 preview 的那批优先）到 `assets/fonts/`
- [ ] 写 `font_match_smoke.py`：合成集 = 用已知字体渲染若干短语 → 跑匹配器 → 算 top-1/top-5 找回率
- [ ] 横评相似度口径：二值掩码 IoU/Chamfer（基线） vs DINOv2/open_clip 形状 embedding
- [ ] 退化鲁棒性探针：对渲染图加 JPEG 压缩 / 降采样 / 重上色 / 半透明底，复测找回率
- [ ] 落 `outputs/font_smoke/`：metrics.json + 可视对比 html（query vs top-k 渲染图）
- **Acceptance**: 合成集 top-5 找回率**显著超随机**（随机≈k/N）；退化后仍可用；明确选定相似度口径与是否需要粗类预过滤
- **Verify**: `uv run --python .venv-font scripts/font_match_smoke.py` → 打印 top-1/top-5 + 退化曲线  → **Result**: pending
- **决策门**: 通过 → F1；不通过 → 在 spec §3/§8 记录并调整方案（降级粒度 / 上专训 / 加 VLM 粗类），不硬上

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
- **Verify**: `uv run --python .venv-font scripts/font_extract.py <video>` → 产 `outputs/font/<name>.json`，逐字段核对  → **Result**: pending

### F3 — eval + 报告（POC done-line）  [todo]
- [ ] 采集/获取 3–5 条真实抖音样本（agent 先试下载，被挡则向 vito 要链接/文件）到 `assets/eval_videos/`
- [ ] 批量跑 `font_extract.py` 出每条 JSON；样式属性对眼标核对；字体匹配视觉合理性判定
- [ ] 合成集精度表（top-1/top-5、退化曲线）作为字体精度量化依据
- [ ] 写结论：闭集匹配行不行 / 精度 / 成本 / 推荐生产方案 / 降级路径（落 spec §9 或独立 findings 段）
- **Acceptance**: 每条真实样本有 JSON + 结果表；有一段可引用的「推荐方案」结论
- **Verify**: 产物齐全（JSON×N + metrics 表 + 结论段），vito 过目  → **Result**: pending
