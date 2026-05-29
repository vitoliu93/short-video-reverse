# BGM 反解 — 工程 Spec

> 把 [BGM-反解-技术选型.md](./BGM-反解-技术选型.md) 的决策落成可实现的工程规格。
> 选型结论(前提):Demucs 分离 → CLAP 标签 + 库内检索 → librosa DSP（术语说明见 [BGM-反解-术语与流水线.md](./BGM-反解-术语与流水线.md)）。
> 更新:2026-05-29 · 状态:**M1 已完成(见 §8)**——全库索引建成(749 向量)、A/C 模块跑通,进入 M2

---

## 1. 目标与范围

**目标:** 输入一个短视频文件,输出该视频 BGM 的结构化描述,供 KOX eval Gold Case 使用:

```jsonc
"bgm": {
  "present": true,                    // 是否有 BGM
  "start": 0.0, "end": 28.4,          // BGM 在视频中的起止(秒)
  "volume_profile": [...],            // 音量包络(下采样后的 RMS 序列 + 采样率)
  "beat": { "tempo": 124.0, "aligned_with_cuts": true },
  "style_tags": ["upbeat", "electronic", "energetic"],   // CLAP 零样本标签
  "match": {                          // 库内替换检索结果
    "audio_url": "tos://kox-statics/bgm/rhythm_bgm/xxx.mp3",
    "category": "rhythm_bgm",
    "score": 0.72,                      // 去均值后的 cosine(见 §7),非 raw cosine
    "topk": [ {url, category, score}, ... ]
  }
}
```

**范围内:** 单视频 BGM 子模块(A/B/C)+ 离线曲库索引。
**范围外:** 镜头/字幕/转场(由 TransNetV2/EVE/ARC 等其他模块负责);BGM 精确曲名识别(指纹,暂不做);eval 指标的最终定义(由评估方案文档决定,本模块只产数据)。

---

## 2. 模块与 IO 契约

```
视频.mp4
  │ ffmpeg
  ▼
audio.wav (单声道 16/44.1kHz)
  │ Demucs (模块 A)
  ▼
music.wav (伴奏 stem) ──┬──────────────┐
                        │               │
                  (模块 C: librosa)  (模块 B2: CLAP)
                        │               │
              volume_profile / beat   style_tags + match
                        └──────┬────────┘
                               ▼
                          bgm{} JSON
```

| 模块 | 输入 | 输出 | 工具 | 跑在 |
|-|-|-|-|-|
| **抽音** | video.mp4 | audio.wav | ffmpeg | CPU |
| **A 分离** | audio.wav | music.wav, vocals.wav | Demucs(htdemucs) | GPU 优先 |
| **C DSP** | music.wav (+ 镜头切点) | volume_profile, start/end, tempo, aligned | librosa | CPU |
| **B2 检索** | music.wav | style_tags, match(topk) | CLAP + faiss 索引 | GPU 优先 |
| **离线建库** | tos://kox-statics/bgm/* | faiss 索引 + 元数据 | tos-cli + Demucs + CLAP | GPU 优先 |

**契约要点:**
- B2 和 C 都消费**分离后的 music stem**,不消费原始混音(见选型文档 §1.A)。
- C 的「卡点对齐」需要镜头切点输入(来自 TransNetV2 模块);若该模块未就绪,先只产 tempo,`aligned_with_cuts` 置 null。
- 检索时优先**限定在同 category 内**比对,可显著降噪;同时保留跨类 topk 备查。

---

## 3. 离线曲库索引(B2 前提,一次性)

```
1. tosutil cp tos://kox-statics/bgm/ ./assets/bgm/ -r -f -j 10     # 拉全量 ~4.5GB
2. 对每条:Demucs 分离(若本身就是纯乐曲可跳过/抽样判断)→ CLAP audio embedding
3. 落盘:faiss 索引 + parallel 的 metadata.jsonl(url, category, duration, embedding_id)
4. 产物存 ./outputs/bgm_index/ : index.faiss + metadata.jsonl
```

- 索引规模 **749 向量**(M1 实测:库内 ~848 条**音频**——「1025/4.5GB」含 79 张 `.jpg` 封面图,非音频;848 经 ETag 字节去重→766,再经 embedding 近重→749),faiss `IndexFlatIP`(内积,配 L2 归一化向量)足够,无需量化。
- **检索口径:存原始 embedding,检索前减全库质心(mean-centering)再算 cosine**(M0 验证:不去均值分数全挤在 0.93~1.0 无法解读,见 §7)。质心随索引一起落盘。
- **必须按音频内容去重**:M0 发现同一首歌存在于多个 category 目录(互检 cosine=1.000)。`category` 因此是**软标签,不是互斥划分**——「限定同类检索」是漏的,只能当作 eval 的一维参考标签,不能当硬过滤。去重键用音频指纹/embedding 近重(非文件名,文件名有重复且带乱码)。
- 元数据保留全部所属 `category` 列表(一首可能多类)、duration、embedding_id。
- 重建触发:曲库新增 / 更换 embedder。脚本需幂等。

---

## 4. 目录与脚本布局(沿用现有约定)

```
short-video-reverse/
├── docs/                BGM-反解-技术选型.md / BGM-反解-spec.md
├── scripts/
│   ├── bgm_build_index.py     # 离线:拉库→分离→CLAP→faiss
│   ├── bgm_extract.py         # 单视频:抽音→分离→C+B2→bgm{} JSON
│   └── bgm_retrieval_smoke.py # M0:几段 query 做 top-k,打印结果供人耳听
├── assets/bgm/          tos 拉下来的曲库(.gitignore)
├── outputs/
│   ├── bgm_index/             index.faiss + metadata.jsonl
│   └── bgm/                   单视频 bgm{} 结果 JSON
└── vendor/              (如需自托管 CLAP/Demucs 权重)
```

- 包管理:`uv`,**专用 venv `.venv-bgm`(Python 3.12)**——系统 3.14 太新,torch/transformers 无 wheel。
- 依赖(已锁定可用版本):`torch`、**`transformers==4.46.3`**(5.x 把 CLAP `get_audio_features` 重构成返回未投影输出且维度错位,4.46 是文档化稳定 API)、`librosa`、`soundfile`、`numpy`、`faiss-cpu`、`demucs==4.0.1`。**不用 `laion-clap` pip 包**(依赖地狱),CLAP 走 `transformers` 的 `laion/larger_clap_music`。
- 两个 M1 踩坑(已绕过):① PyPI 版 `demucs` 无 `demucs.api`,改用底层 `pretrained.get_model` + `apply.apply_model`;② `torchaudio 2.11` 的 `save` 走未安装的 `torchcodec`,stem 改用 `soundfile.write` 落盘(避免再引重依赖)。
- 拉库统一走 `tos-cli` skill(`.claude/skills/tos-cli/bin/tosutil`),凭证在 `~/.tosutilconfig`。
- GPU:Demucs / CLAP 推理优先 GPU,可复用 ARC 自托管那台(见 `scripts/setup-arc-hunyuan-gpu.sh`);CPU 也能跑,只是慢。

---

## 5. 里程碑(de-risk 优先)

| 里程碑 | 交付 | 验收 | 备注 |
|-|-|-|-|
| ~~**M0 验证假设**~~ ✅ | `bgm_retrieval_smoke.py` | 83 条样本 leave-one-out + 人耳试听 | **已通过**,见 §7。CLAP 确认,不切 MERT |
| ~~**M1 地基**~~ ✅ | `bgm_build_index.py` + A(`bgm_separate.py`)+ C(`bgm_dsp.py`) | 全库索引 749 向量(去均值+去重);Lotus 样本视频 A→C 跑通出 volume_profile/start/end/tempo | **已完成**,见 §8 |
| **M2 全链路** | `bgm_extract.py` | 输入视频 → 完整 bgm{} JSON(schema §1) | 整合 A→C→B2 |
| **M3 接入 eval** | 批量跑精选 gold 视频 | 产出 Gold Case 的 bgm{} 数据集 + 风格/用法统计基准 | 对接评估方案 v2 |

---

## 6. 风险与开放问题

| 风险/问题 | 处置 |
|-|-|
| ~~CLAP 音乐检索质量不足~~ | **M0 已验证通过**,同类命中 2.5× 随机基线,人耳认可排序。不切 MERT |
| ~~分数不可解读(全 0.9+)~~ | **M0 已解决**:检索前减全库质心(mean-centering),分数拉开到 0.3~1.0 且排序不变(§7) |
| 同一曲跨 category 重复 | 建库按音频近重去重;category 当软标签不当硬过滤(§3) |
| 绝对阈值卡「有没有合适 BGM」 | 即便去均值后,阈值仍需在标定集上校准;优先用排序 + top-1 与 top-2 间距,不硬编 0.x |
| 部分曲解码报错(libmpg123 非法比特分配)/ 文件名乱码 | 解码失败的轨跳过并记录;M0 中 librosa+ffmpeg 回退能恢复大部分;回写 url 前修 GBK 乱码 |
| Demucs 分离慢(长视频) | 短视频场景可接受;必要时只对检测到 BGM 的区间分离 |
| 「卡点对齐」依赖镜头切点模块 | 该模块未就绪时先产 tempo,aligned 置 null,不阻塞 |
| 多段不同 BGM / BGM 中途切换 | v1 先按「主 BGM」处理;多段切换留 v2(按能量突变分段后逐段检索) |
| 纯人声/清唱(无伴奏)误判 | A 之后用 music stem 能量阈值判 `present=false` |
| 版权:match 到的库内曲是否可商用 | 由库本身保证(kox-statics/bgm 即生成时取用源),反解只做映射不引入新版权 |

**待确认:**
1. eval 到底要不要「可重放」级别的 audio_url 映射,还是只要风格统计?(影响 match 字段权重,但不影响要建的东西)
2. ~~CLAP checkpoint 选哪个~~ → **已定:`laion/larger_clap_music`**(transformers 直接加载,M0 验证有效)。
3. 是否需要把 BGM 结果回写某个库表,还是只落 outputs/ JSON。

---

## 7. M0 验证结果(2026-05-29)

**目的:** 戳破最大不确定性 —— CLAP 音频→音频检索在 kox-statics/bgm 上到底行不行。
**做法:** 每类抽样(lyrics 24 / normal 30 / rhythm 29,共 83 条),`laion/larger_clap_music`
逐条 embedding(3 窗口均值池化),leave-one-out 检索 + 人耳试听。脚本 `scripts/bgm_retrieval_smoke.py`,
产物 `outputs/bgm_smoke/`(metrics.json + 带播放器的 index.html)。

### 结论:✅ 通过,CLAP 路线确认,不切 MERT

**量化(同类命中率,代理指标):**

| | top-1 同类 | top-5 同类 | 随机基线 |
|-|-|-|-|
| 命中率 | 0.59 | **0.831** | 0.336 |

top-5 同类命中是随机基线的 ~2.5×,说明 embedding 抓到了 lyrics/normal/rhythm 的功能性结构。
完全相同音频互检 cosine=1.000,管线正确。

**关键修正:分数压缩 → 去均值(mean-centering)**

raw cosine 全挤在 0.93~1.0,无法解读(人耳:精卫→Do It 该打 ~0.9,CLAP 打 0.982)。
减全库质心后再算 cosine:

| top-1 相似度分布 | min | p10 | median | p90 |
|-|-|-|-|-|
| raw | 0.933 | 0.982 | 0.994 | 1.0 |
| **去均值** | 0.319 | 0.475 | 0.738 | 1.0 |

排序几乎不变(同类命中 0.59→0.60 / 0.831→0.807),但分数被拉开到可解读区间;
精卫→Do It 降到 0.720,且白捡一个 raw 看不出的优质匹配:AC/DC Highway to Hell → AC/DC
Back In Black(同乐队,0.535)。**故采纳:检索一律用去均值后的 cosine。**

**附带发现(已并入 §3 / §6):**
1. 同一曲跨 category 目录重复(互检 1.000)→ category 是软标签,建库须按音频去重。
2. 真实检索质量比 0.83 更高(部分「跨类 miss」其实是另一目录同一首)。
3. 少量曲解码报错 + 文件名 GBK 乱码,需在建库/回写时处理。
4. 工程:Python 3.12 专用 venv + `transformers==4.46.3`(避开 5.x CLAP 重构 + 3.14 无 wheel)。

---

## 8. M1 验证结果(2026-05-29)

**目的:** 建成全库 faiss 索引 + 跑通视频侧 A(分离)/C(DSP)模块。

### 8.1 离线建库 `bgm_build_index.py`

**磁盘友好的流式建库**(回应「不要全部下载,内存/磁盘不够」):逐条「下载→CLAP embedding→立即删除」,
峰值磁盘 = 1 个文件(~7MB),全程不落地整库;embedding 增量缓存可断点续跑。

| 阶段 | 条数 |
|-|-|
| ls 清点(排除 79 张 `.jpg` 封面) | 848 音频 |
| ETag(MD5)字节级去重 | → 766 |
| embedding 近重去重(cosine>0.9995) | 合并 17 → **749** |

产物 `outputs/bgm_index/`:`index.faiss`(749×512)、`embeddings.npy`(原始向量,便于换质心重建)、
`centroid.npy`(全库质心)、`metadata.jsonl`(embedding_id / url / **categories 列表** / duration)。
类别分布(含多类归属)lyrics 85 / normal 311 / rhythm 389。

**检索口径落地:** faiss 索引建在「减质心后」的向量上,内积即去均值 cosine。query 时同样减质心再搜。
抽 3 条库内曲自检:self=1.000,top-2..5 落在 0.48~0.79 可解读区间(去均值生效);
精卫→Do It=0.730(与 M0 的 0.720 一致),并自动召回「精卫琵琶版」(同曲翻奏 0.693)。

### 8.2 视频侧模块 A + C

- **A `bgm_separate.py`(Demucs htdemucs):** ffmpeg 抽音 → 分离出 `music.wav`(=drums+bass+other)+ `vocals.wav`。
- **C `bgm_dsp.py`(librosa):** music stem → `volume_profile`(10Hz RMS 包络)、`start`/`end`(RMS 越噪声地板)、`beat.tempo`。

Lotus 15s 样本验证 A→C 跑通:start 0.6 / end 14.7 / 151 点包络。
**关键观察:分离后 tempo 110.0 vs 原始混音 147.7** —— 人声/瞬态污染会带偏 beat tracker,
印证「A 是 C 的前提」(选型文档 §1.A)。`aligned_with_cuts` 待 TransNetV2 切点接入,暂置 null。

### 8.3 进入 M2

A/C/B2 三块齐备,M2 把它们串成 `bgm_extract.py`:视频 → 抽音 → A → (C ‖ B2 检索) → 完整 `bgm{}` JSON(schema §1)。
