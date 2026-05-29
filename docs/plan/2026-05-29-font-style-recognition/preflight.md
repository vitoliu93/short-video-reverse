# Preflight: 字体 + 样式识别

Checks derived from spec. Run before F0. [ ] = 未验证, [x] = 已验证, [!] = 坏了。

- [x] `tosutil` 可用且能列字体库 — 立项时确认：2660 对象/14GB，ttf+otf+preview.png 混合；单款下载实测 ~1.4MB/s OK
- [x] 能从一款 TTF 渲染出 CJK 字形 — 下载 `Aa全息黑体.ttf`，Pillow+freetype 渲染「测试中文字体识别」→ 22074 ink px，肉眼字形+风格(横线纹理)都对（`outputs/font_smoke/preflight_render.png`）
- [x] `.venv-font`(Python 3.12) 建好，核心依赖装上 — pillow/fonttools/opencv-python-headless/numpy/scikit-image/rapidocr-onnxruntime 全装上
- [x] ffmpeg 可抽帧 — ffmpeg 8.1.1 present
- [x] RapidOCR 能在一张含中文的图上出 bbox+text — 读回「测试中文字体识别」8/8 字全对
- [ ] (可选) torch + DINOv2/open_clip 可加载 — 仅 F0 判定模板不够时才需要，先不装
- [ ] (F3 才需要) 真实抖音样本来源确认 — agent 试 yt-dlp/agent-browser 下载；被反爬挡则向 vito 要 3–5 个抖音链接或直接给文件

**Preflight 结论（2026-05-29）：✅ 全过（除 F0/F3-条件项）。整条工具链 TTF 下载→渲染→OCR 读回 全程跑通，可开 F0。**

## Findings
- **`uv run --python .venv-font` 是坑**：本仓有 `pyproject.toml`，`uv run` 会无视 `--python` 指的已装好的 venv，另建空 `.venv` 并往里装（结果 ModuleNotFoundError）。
  → **统一用 `.venv-font/bin/python scripts/xxx.py` 直接调解释器**（deps 是 `uv pip install --python .venv-font` 装进去的）。已把 spec/todo 的 verify 命令改成这个。
- `fonttools` 取字符覆盖用 `TTFont(path).getBestCmap()`（`ord(c) in cmap` 判某字是否有字形）；`Aa全息黑体` 有 7909 glyphs。
- 渲染图确认：库内字体的**独特风格被完整保留**（不是退化成默认黑体）→ render-and-compare 有真实判别信号，F0 假设成立的前提已具备。

## 已知上下文（立项时确认，免重查）
- 字体库 `tos://kox-statics/fonts_effect/`：~2660 对象 / 14.05GB；`<名>.ttf` / `<名>.otf` + 约半数有 `<名>.preview.png`；
  另有 UUID 式 `<hash>_font.ttf`（疑似用户上传，无策展名）。命名 CJK 字体如 `Aa锐甲黑.ttf`、`A1明朝.ttf`。
- `.env` 仅有 `ARC_TOKEN`（ARC-Hunyuan 视频理解，非通用图像 VLM）。若 F0 后要 VLM 粗类，需补 Doubao 视觉 creds。
- `.gitignore` 已忽略 `assets/`、`outputs/`、`models/`、`*.safetensors`、`.venv-*`、`.env` —— 大文件/权重/结果都不进 git。
