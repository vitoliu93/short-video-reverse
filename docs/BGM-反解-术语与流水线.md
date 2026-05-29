# BGM 反解 — 术语与流水线说明

> 解释选型结论「Demucs 分离 → CLAP 标签 + 库内检索 → librosa DSP」中各术语的含义及在流水线中的位置。
> 工程规格见 [BGM-反解-spec.md](./BGM-反解-spec.md)，决策依据见 [BGM-反解-技术选型.md](./BGM-反解-技术选型.md)。
> 更新:2026-05-29

---

## 1. 整体在干什么

短视频音轨通常是 **人声 + 背景乐 + 音效** 的混合。BGM 反解不是「找一个识别 BGM 的模型」，而是一条小流水线，拆成三个相对独立的子问题（对应 spec 中的模块 A / B / C）：

| 阶段 | 工具 | 回答的问题 |
|------|------|------------|
| **A 分离** | Demucs | 先把「背景乐」从混音里抠出来 |
| **B 识别/检索** | CLAP + FAISS | 这段 BGM 什么风格？库里哪条最像？ |
| **C 用法刻画** | librosa DSP | 音量曲线、起止时间、节拍、是否卡点 |

选型里的 **「Demucs 分离 → CLAP 标签 + 库内检索 → librosa DSP」** 即按 **A → B → C** 顺序执行。

---

## 2. Demucs 分离（模块 A）

**Demucs** 是 Meta 开源的 **音源分离（source separation）** 模型：把一条混合音频拆成多个 **stem（音轨分量）**，例如人声、鼓、贝斯、伴奏等。

本方案使用 **HTDemucs**（`htdemucs`），输出中关键的是：

- **`music.wav`**：伴奏 / 背景乐 stem → 后续 CLAP 与 librosa 均消费此文件
- **`vocals.wav`**：人声 stem → 本 spec 不直接写入 `bgm{}`，但分离质量会影响 `music` 是否干净

**为何必须先做分离？**

- 不分离就算 RMS：旁白大声段会把 BGM 音量包络「顶歪」→ 模块 C 失真
- 不分离就算 embedding：向量里混进人声 → 模块 B 库内检索混乱

因此 Demucs 是 **B 与 C 的共同前提**，不是可选预处理。

---

## 3. CLAP 标签 + 库内检索（模块 B2）

**CLAP**（Contrastive Language-Audio Pretraining）将 **音频** 与 **文字** 映射到 **同一向量空间**：

- 一段音频 → 一个 embedding 向量
- 一句描述（如 `"upbeat electronic energetic"`）→ 同一空间中的向量

于是一个模型同时支撑 spec 中的 `style_tags` 与 `match` 两类输出。

### 3.1 CLAP 标签（零样本风格标签）

无需为「欢快 / 电子 / 动感」单独训练分类器。将若干英文风格短语作为 **文本 query**，与当前 `music.wav` 的音频向量计算相似度，取得分高的条目作为 **`style_tags`**。

这叫 **零样本（zero-shot）**：标签来自预训练阶段的音频–文本对齐能力，而非业务侧再标注的数据。

### 3.2 库内检索（audio-to-audio）

**离线**（`bgm_build_index.py`）：对 `tos://kox-statics/bgm/` 中每条曲

1. 必要时 Demucs 分离（纯 BGM 可跳过或抽样判断）
2. CLAP 计算 **audio embedding**
3. 写入 **FAISS** 索引 + `metadata.jsonl`（url、category 等）

**在线**（`bgm_extract.py`）：对输入视频的 `music.wav` 算同样向量，在索引中 **近邻搜索（top-k）**，得到听感/风格最接近的库内曲 → `match.audio_url`、`score`、`topk`。

与 **音频指纹（B1，未采用）** 的对比：

| | 指纹 B1 | CLAP B2（本方案） |
|--|---------|-------------------|
| 回答的问题 | 是否为 **同一段录音** | **听感/风格** 最接近哪条 |
| 同 mood、不同曲 | 通常匹配不上 | 向量仍可相近 |
| 与 eval 目标 | 抖音原曲多半不在 `kox-statics/bgm` | 需要 **库内可替换** 的 `audio_url` |

**FAISS** 是向量检索引擎（内积 + L2 归一化），不负责「理解音乐」；语义在 CLAP embedding 中。

检索时可 **先在同 `category` 内过滤** 再比对，降低跨类误召；同时保留跨类 topk 备查（见 spec §2）。

---

## 4. librosa DSP（模块 C）

**librosa** 是 Python 常用的 **音频分析库**；此处的 **DSP** 指 **数字信号处理**：用确定性算法从波形提取特征，**不依赖神经网络推理**。

模块 C 从 **`music.wav`**（及可选的镜头切点）产出 spec §1 中的用法字段：

| 输出字段 | 典型做法（概念） |
|----------|------------------|
| `volume_profile` | 短时能量（如 RMS）→ 下采样为音量包络序列 |
| `start` / `end` | 按能量阈值判断 BGM 在视频中何时明显出现/结束 |
| `beat.tempo` | beat tracking / BPM 估计 |
| `beat.aligned_with_cuts` | 节拍与 **TransNetV2 镜头切点** 是否对齐；切点模块未就绪时置 `null` |

选型文档强调：**eval 中许多硬指标来自 C，而非 B**。B 回答「像哪首 / 什么风格」；C 回答「剪辑上如何用 BGM」（音量、进出、卡点）——librosa 路径稳定、可复现、风险低。

---

## 5. 数据流（与 spec 图一致）

```
video.mp4
  │ ffmpeg
  ▼
audio.wav（混音）
  │ Demucs（模块 A）
  ▼
music.wav（伴奏 stem）──┬── librosa（模块 C）→ volume_profile, start/end, tempo, aligned…
                        └── CLAP + FAISS（模块 B2）→ style_tags, match(topk)
                               │
                               ▼
                          bgm{} JSON
```

**契约要点**：模块 B2 与 C **均只消费分离后的 music stem**，不直接对原始混音做检索或包络计算。

---

## 6. 与业务目标的关系

对 KOX eval Gold Case，本模块产出可写入 schema 的结构化 `bgm{}`：

- **Demucs**：保证后续分析的是「背景乐」，而非整轨混音
- **CLAP + 库**：风格标签 + 指向 `kox-statics/bgm` 的 **可替换** `audio_url`（重放或统计均可用）
- **librosa**：可量化的剪辑信号（音量、时机、节拍、卡点）

**M0** 优先验证 CLAP 检索质量（最大未知）；索引建库与 C 相对确定。若检索不足，可分叉为 audio-audio 换 **MERT**、文字标签仍用 CLAP——不改变「分离 → 检索/标签 → DSP」骨架（见 spec §5）。

---

## 7. `bgm{}` 字段与模块对照

| JSON 字段 | 模块 | 说明 |
|-----------|------|------|
| `present` | A + C | 分离后 music stem 能量阈值，过低则判无 BGM |
| `start`, `end` | C | BGM 在视频时间轴上的起止 |
| `volume_profile` | C | RMS 等下采样包络 |
| `beat.tempo` | C | BPM |
| `beat.aligned_with_cuts` | C + 镜头模块 | 需 TransNetV2 切点；未就绪为 `null` |
| `style_tags` | B2 (CLAP) | 零样本文本–音频相似度 |
| `match.*` | B2 (CLAP + FAISS) | 库内向量近邻 |
