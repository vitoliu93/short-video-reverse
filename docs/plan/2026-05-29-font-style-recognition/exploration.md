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
