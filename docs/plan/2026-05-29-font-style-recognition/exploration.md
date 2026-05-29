# Exploration

关于**代码/任务**的事实笔记（不是感想）。追加，不重写历史。

## [2026-05-29 立项]
1. **字体库构成**（`tosutil ls/du tos://kox-statics/fonts_effect/`）：~2660 对象 / 14.05GB。混合 `.ttf`、`.otf`、约半数字体配 `<名>.preview.png`（一张渲染样图）。命名分两类：策展中文名（`Aa锐甲黑.ttf`、`A1明朝.ttf`）与 UUID 式 `<hash>_font.ttf`（疑似用户上传）。→ preview.png 可当**粗排**现成参考；精排须现渲染查询字符。
2. **闭集是关键收敛**：我们有全部 TTF，所以可以「渲染参考字形 → 与查询比对」，把开放集字体识别降为闭集检索。这是整个方案能成立的支点。
3. **BGM 子项目是工作法模板**（`docs/BGM-反解-spec.md`）：M0 先 de-risk 最大未知（CLAP 检索行不行）→ M1 地基（流式建库 749 向量 + 视频侧模块）→ M2 全链路 `bgm_extract.py` → M3 eval。字体任务照搬为 F0→F3。
4. **流式建库范式**（`scripts/bgm_build_index.py`）：逐条「下载→embedding→立即删」，峰值磁盘≈单文件，可断点续跑。14GB 字体库照此处理，不全量落地。
5. **共享件范式**（`scripts/bgm_common.py`）：把「锁定口径」的函数集中（device 选择 mps/cuda/cpu、归一化、相似度）。字体侧建 `font_common.py` 对应。
6. **venv 教训**（BGM spec §4）：系统 Python 3.14 太新，torch/transformers 无 wheel → BGM 用专用 `.venv-bgm`(3.12)。字体侧同样建 `.venv-font`(3.12)。
7. **creds 现状**：`.env` 只有 `ARC_TOKEN`（ARC-Hunyuan 视频理解 API，见 `scripts/test_arc_api.py`），**不是**通用图像 VLM。要做 VLM 字体粗类得另配 Doubao 视觉 creds。
8. **OCR 选型**：研究文档点名 PaddleOCR(reading-list #24)，但 PaddlePaddle 安装重。POC 倾向 RapidOCR(onnxruntime)，不行再回退 Paddle。
9. **git 拓扑**（立项时）：本地 `main` 比 `origin/main` **超前 4 个 commit**，且研究文档+BGM 脚本只在这 4 个本地 commit 里、未推 origin。所以本计划 worktree 从**本地 HEAD** 建（不是默认的 `fresh`=origin/main），否则会缺研究文档。

## [2026-05-29 preflight]
10. **`uv run --python <venv>` 在本仓是坑**：有 `pyproject.toml` 时 `uv run` 会无视 `--python` 指的现成 venv，另建空 `.venv` 装依赖 → ModuleNotFoundError。**统一 `.venv-font/bin/python scripts/x.py` 直调**（deps 用 `uv pip install --python .venv-font` 装）。
11. **渲染保真**：`Aa全息黑体.ttf` 经 Pillow `ImageFont.truetype(path, 96)` 渲染，字体的横线纹理风格**完整保留**（不是退化成系统默认）→ 闭集 render-and-compare 的判别信号确实存在（F0 前提验证）。截图 `outputs/font_smoke/preflight_render.png`。
12. **OCR 选型落地**：`rapidocr-onnxruntime==1.4.4` 装载零障碍（onnxruntime，无 Paddle 依赖地狱），中文读回 8/8。F0/F1 用它。
13. **字符覆盖查法**：`fontTools.ttLib.TTFont(path).getBestCmap()` 返回 {codepoint: glyphname}；`ord(c) in cmap` 判该字体是否有某字字形 —— 渲染查询字符前先过滤掉该字体缺字的情况。

## [2026-05-29 F1/F2]
14. **闭集框架白送字体属性**:识别出字体后,字重/粗细是该字体的**固有属性**,直接对干净渲染测(`font_common.intrinsic_weight`),比从退化视频像素量稳得多。先前量退化 crop,bold/regular 都误判 thin;改后 12/12。库内名字带「粗/常规/细」可直接当标定集(bold≈0.115/regular≈0.068/thin≈0.049 笔宽÷字高)。
15. **RapidOCR char-level**:RapidOCR 只给行级 box+text,不给单字框。CJK 字幕近似全角等宽 → 按 text 长度等分 line crop 当 char crops(POC 口径,标点/拉丁混排会错位)。
16. **字号要从事件级取**:pop/zoom 动画下逐帧大小变,单帧 size 会被早期小帧带偏 → 取事件内所有 obs 框高 p75(稳定后尺寸)。
17. **真实视频 plumbing 测**(Lotus 16:9 车广告,英文/logo):管线不崩,但 OCR 在 logo/运动图形上乱读("EMEVA"/"FSTETTETTTTS"),匹配分普遍 <0.4。→ **低分可当「非干净字幕」过滤信号**。但这不是 CJK 字幕视频,非公平测试。
18. **抖音样本是 F3 硬依赖**:自动下载受抖音登录/反爬限制,agent 无 URL 无法凭空获取。需 vito 给 3–5 个抖音链接或直接给视频文件。F0/F1/F2 都不依赖它(合成+库内字体),已全过。
19. **ffmpeg make_video 前置**:输出目录必须先存在,否则 libx264 退 254(被 -loglevel error 吞掉报错)。
