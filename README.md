# short-video-reverse

短视频结构化拆解与逆向分析。

## ARC API 文档

### [ARC-Hunyuan-Video-7B](https://arc.tencent.com/document/ARC-Hunyuan-Video-7B)

多模态短视频理解模型，支持视频 + 音频 + 文本联合推理。能力包括：

- 带时间戳的章节摘要与事件定位
- 开放问答（QA）、选择题（MCQ）
- 视频描述与总结（Summary）

适用于 5 分钟以内的短视频。接口可免费调用 100 次；如需商务合作、批量化调用等，请联系：

- kantzhang@tencent.com
- yingminluo@tencent.com
- yingsshan@tencent.com

本地测试脚本：`scripts/test_arc_api.py`  
结果保存目录：`outputs/arc/`

### [ARC-OmniScript](https://arc.tencent.com/document/ARC-OmniScript)

视频剧本解析与分析模型，能够自动识别视频中的关键场景、对话内容、情感变化等元素，生成结构化的脚本分析报告。

适用于 5 分钟以内的视频。接口可免费调用 100 次；如需商务合作、批量化调用等，请联系：

- kantzhang@tencent.com
- yingminluo@tencent.com
- yingsshan@tencent.com

## 相关资源

- [ARC-Hunyuan-Video 发布公告](https://tencentarc.github.io/posts/arc-video-announcement/)
- [ARC-Hunyuan-Video-7B 开源仓库](https://github.com/TencentARC/ARC-Hunyuan-Video-7B)
- [阅读清单](reading-list.md)
