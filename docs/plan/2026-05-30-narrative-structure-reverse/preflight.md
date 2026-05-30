# Preflight: narrative-structure reverse (`narr_`)

> 开工前的环境/凭据/复用核对。沿用 fx/font/bgm 的 preflight 习惯。

## 环境
- 单 venv（`uv run`），无需新依赖：narr 只用 `requests`（ARC HTTP）+ 复用 `fx_detect`(transnetv2-pytorch) + `fx_common`(doubao Ark)。**未加任何 dependency**，`pyproject.toml` 不变。
- macOS libomp：narr_common / narr_extract 经 fx_detect 引入 torch → 两文件首行 `os.environ.setdefault("KMP_DUPLICATE_LIB_OK","TRUE")`（仓库约定）。

## 凭据（两套，分别复用现有管线）
| 用途 | 变量 | 来源 | 状态 |
|-|-|-|-|
| ARC-Hunyuan 理解 | `ARC_TOKEN` | 本仓库 `.env`（与 test_arc_api 同源） | ✅ 实测有效（len 225, eyJhbG…），免费额度 ~100 |
| doubao 合成 | `VOLC_ARK_API_KEY` | 兄弟项目 `../icccut-agents/.env(.test)`（fx_common.load_creds） | ✅ fx_ 已验证可用 |

## 复用清单（不重造）
- `fx_detect.build_windows(video)` → 确定性镜头线 `shots[]` + `duration`（叙事骨架）。
- `fx_common.vlm / parse_json / load_creds` → doubao(Ark) SSE 客户端（合成层）。
- `test_arc_api` 的请求结构 / 缓存命名 `outputs/arc/<stem>_<task>.json`（narr_common.arc_call 复用并加缓存读取）。

## 素材
- `assets/Lotus_*.mp4`（16:9 汽车广告，跑通机制 + 非抖音对照）。
- `assets/douyin_{drama_16s, ai_19s, hair_17s, kid_10s, car_135s}.mp4`（真实抖音竖屏，N3 评测；car_135s 较长，本轮先用 5 条短的）。

## 额度纪律
- 每片 4 个 ARC 任务；**全部磁盘缓存**，re-run 命中即不烧额度。
- 预算：N0 探针 3（drama）+ Lotus Summary 1（已存）+ N2/N3 各片补齐 → 总用量目标 ≤25。`--tasks` 支持子集，`--no-cache` 才会重打。

## 风险点（开工已知，详见 spec §8）
- ARC 自由文本非 JSON → 靠 doubao 合成收敛（已在 N0 验证素材充足）。
- 叙事主观、无 GT → N3 用「人工判定多数合理」+ 闭集 + 可选 k 投票，而非精确率。
- 单镜头相册类（ai/kid）镜头线 = 1 → pacing 退化为 slow/0；acts 仍可由 ARC 语义 Segment 给（设计预期，N3 记录）。
