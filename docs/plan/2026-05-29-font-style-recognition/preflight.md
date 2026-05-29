# Preflight: 字体 + 样式识别

Checks derived from spec. Run before F0. [ ] = 未验证, [x] = 已验证, [!] = 坏了。

- [ ] `tosutil` 可用且能列字体库 — `.claude/skills/tos-cli/bin/tosutil ls tos://kox-statics/fonts_effect/ -d -limit 5`（已在立项时确认：2660 对象/14GB，ttf+otf+preview.png 混合）
- [ ] 能从一款 TTF 渲染出 CJK 字形 — 拉 1 款字体，Pillow+freetype 渲染「测试中文」并存 PNG，肉眼非空白
- [ ] `.venv-font`(Python 3.12) 建好，核心依赖装上 — `uv venv .venv-font --python 3.12` + pillow/fonttools/opencv-python/numpy/scikit-image/rapidocr-onnxruntime
- [ ] ffmpeg 可抽帧 — `ffmpeg -version` 且能从一个 mp4 抽出帧
- [ ] RapidOCR 能在一张含中文的图上出 bbox+text — 跑一次 demo
- [ ] (可选) torch + DINOv2/open_clip 可加载 — 仅 F0 判定模板不够时才需要，先不强求
- [ ] (F3 才需要) 真实抖音样本来源确认 — agent 试 yt-dlp/agent-browser 下载；被反爬挡则向 vito 要 3–5 个抖音链接或直接给文件

## Findings
<跑 preflight 时把坏掉的项和修法记这里，避免下个 agent 重复 debug>

## 已知上下文（立项时确认，免重查）
- 字体库 `tos://kox-statics/fonts_effect/`：~2660 对象 / 14.05GB；`<名>.ttf` / `<名>.otf` + 约半数有 `<名>.preview.png`；
  另有 UUID 式 `<hash>_font.ttf`（疑似用户上传，无策展名）。命名 CJK 字体如 `Aa锐甲黑.ttf`、`A1明朝.ttf`。
- `.env` 仅有 `ARC_TOKEN`（ARC-Hunyuan 视频理解，非通用图像 VLM）。若 F0 后要 VLM 粗类，需补 Doubao 视觉 creds。
- `.gitignore` 已忽略 `assets/`、`outputs/`、`models/`、`*.safetensors`、`.venv-*`、`.env` —— 大文件/权重/结果都不进 git。
