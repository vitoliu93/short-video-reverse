#!/usr/bin/env python3
"""narr_common — 叙事结构反解管线的契约层（口径集中在这里）。

三层 AVI 架构（见 spec §2/§5）：
- 确定性骨架：复用 fx_detect 的镜头线 → 纯计算 pacing（不让 VLM 编时间戳）。
- 语义素材：ARC-Hunyuan hosted API 多任务（Summary/Segment/QA/Grounding），带磁盘缓存省额度。
- 合成收敛：复用 fx_common 的 doubao(Ark) 客户端，把 ARC 自由文本 + 镜头线 → 闭集 narrative JSON。

内容：
- ARC 客户端：multipart 上传 + THINK/ANSWER 解析 + outputs/arc/ 缓存（命名同 test_arc_api）。
- 闭集 taxonomy：hook_type / narrative_structure / act_role / pacing label。
- pacing 计算：avg/std 镜头时长、cuts_per_min、fastest_window、label（确定性）。
- doubao 合成：prompt 模板 + 调用 + JSON 解析（复用 fx_common.vlm/parse_json/load_creds）。
"""
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # fx_detect 经 transnet 引入 torch

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx_common as fc  # 复用 doubao(Ark) 客户端 + parse_json

ARC_OUT = ROOT / "outputs" / "arc"

# ── ARC hosted API ────────────────────────────────────────────────────
ARC_BASE = "https://arc.tencent.com"
ARC_SHORT = f"{ARC_BASE}/cvc_function/arc_hunyuan_short_video/"
ARC_LONG = f"{ARC_BASE}/cvc_function/arc_hunyuan_long_video/"
ARC_TASKS = {"MCQ", "Segment", "Grounding", "QA", "Summary"}

# 叙事反解用的 4 个任务 + 默认中文 prompt（N0 实测有效，见 spec §9）
NARR_TASKS = ["Summary", "Segment", "QA", "Grounding"]
NARR_PROMPTS = {
    "Summary": "详细描述这个视频：画面内容、音频、想传达的核心信息与主题。",
    "Segment": "把这个视频按叙事/情节切分成几个段落，每段给出时间范围(HH:MM:SS)和一句话内容。",
    # 中性问法：不预设叙事框架（旧版写「铺垫/冲突/反转/结尾之类」会诱导 ARC 套用该框架，
    # 污染下游 structure 判断，见 spec §11 审计）。
    "QA": ("分析这个视频的创作手法：开场用什么方式抓住观众(钩子)？"
           "整体是怎么组织和推进叙事的？有没有行动号召(CTA)？想传达什么？"),
    "Grounding": "定位视频里情绪最强烈或最关键的转折/高潮时刻，给出时间范围。",
}


def load_arc_token() -> str:
    """本仓库 .env / 环境变量里的 ARC_TOKEN（与 test_arc_api 同源）。"""
    tok = os.environ.get("ARC_TOKEN", "").strip()
    if tok:
        return tok
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ARC_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("缺少 ARC_TOKEN（设环境变量或写进本仓库 .env）。")


def hms_to_sec(s: str):
    """'HH:MM:SS' / 'MM:SS' / 'SS' → float 秒；解析不出返回 None。"""
    s = s.strip()
    if not re.match(r"^\d{1,2}(:\d{1,2}){0,2}$", s):
        return None
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts
    return float(h * 3600 + m * 60 + sec)


def parse_think_answer(text: str):
    """从 ARC 回答里分出 (think, answer)。无标签时整体当 answer。"""
    if not text:
        return "", ""
    think = ""
    mt = re.search(r"\[THINK\](.*?)\[/THINK\]", text, re.S)
    if mt:
        think = mt.group(1).strip()
    ma = re.search(r"\[ANSWER\](.*?)\[/ANSWER\]", text, re.S)
    answer = ma.group(1).strip() if ma else re.sub(
        r"\[/?THINK\].*?(\[/THINK\])?", "", text, flags=re.S).strip()
    return think, answer


def _unwrap_arc(res: dict) -> str:
    """response.data[0][0] = [prompt, answer_text] → answer_text。结构异常返回 ''。"""
    try:
        return res["data"][0][0][1]
    except (KeyError, IndexError, TypeError):
        return ""


def arc_call(video: Path, task: str, prompt=None, lang="chinese",
             use_cache=True, timeout=300) -> dict:
    """调 ARC short-video API 单任务，带磁盘缓存（outputs/arc/<stem>_<task>.json）。

    返回 {task, prompt, think, answer, model, cached, ok}。
    缓存格式沿用 test_arc_api：{meta, response}。命中即不再烧额度。
    """
    if task not in ARC_TASKS:
        raise ValueError(f"task 必须 ∈ {sorted(ARC_TASKS)}")
    prompt = prompt or NARR_PROMPTS.get(task, "请分析这个视频。")
    cache_path = ARC_OUT / f"{video.stem}_{task}.json"

    raw = None
    cached = False
    if use_cache and cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))["response"]
            cached = True
        except (json.JSONDecodeError, KeyError):
            raw = None

    if raw is None:
        headers = {"Authorization": load_arc_token()}
        data = {"prompt": prompt, "task_type": task, "lang": lang}
        with video.open("rb") as f:
            files = {"file": (video.name, f, "video/mp4")}
            r = requests.post(ARC_SHORT, headers=headers, data=data,
                              files=files, timeout=timeout)
        r.raise_for_status()
        raw = r.json()
        ARC_OUT.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "meta": {"video": str(video), "task_type": task,
                     "prompt": prompt, "lang": lang, "is_short_video": True},
            "response": raw,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    answer_text = _unwrap_arc(raw)
    think, answer = parse_think_answer(answer_text)
    return {"task": task, "prompt": prompt, "think": think, "answer": answer,
            "model": "ARC-Hunyuan-Video-7B", "cached": cached,
            "ok": raw.get("code") == 0}


def arc_all(video: Path, tasks=None, lang="chinese", use_cache=True) -> dict:
    """跑 narr 需要的全部 ARC 任务，返回 {task: result}。"""
    tasks = tasks or NARR_TASKS
    return {t: arc_call(video, t, lang=lang, use_cache=use_cache) for t in tasks}


# ── 闭集 taxonomy（合成层 prompt 用） ─────────────────────────────────
HOOK_TYPES = {
    "relatable-pain": "痛点共鸣", "suspense": "悬念设问", "conflict": "冲突对立",
    "visual-shock": "视觉冲击", "benefit-promise": "利益承诺", "contrast": "反差",
    "authority": "权威背书", "story-immersion": "剧情代入", "direct": "开门见山",
    "none": "无明显钩子",
}
NARRATIVE_STRUCTURES = {
    "setup-conflict-twist-end": "铺垫-冲突-反转-结尾", "parallel-escalation": "并列递进",
    "problem-solution": "问题-解答", "hook-proof-cta": "钩子-论证-号召",
    "qijichengzhuan": "起承转合", "chronological": "顺叙/流水账",
    "list": "清单罗列", "other": "其他",
}
ACT_ROLES = ["hook", "setup", "conflict", "escalation", "twist",
             "climax", "resolution", "cta"]
PACING_LABELS = ["slow", "medium", "medium-fast", "fast", "hyper-cut"]


def normalize_acts(acts, duration):
    """把合成层给的 acts 收敛成「按时间单调、互不重叠、落在[0,dur]」的序列。

    doubao 偶发把特殊节拍(hook/cta)嵌进相邻幕里导致重叠（N3 实测 kid 头部重叠、
    hair 尾部嵌套）。这里做确定性归一：排序→裁剪边界→丢零宽。属对外部非确定 API
    输出的规整，不是无中生有的防御代码。
    """
    clean = []
    for a in acts or []:
        if a.get("t_start") is None or a.get("t_end") is None:
            continue
        s = max(0.0, min(float(a["t_start"]), duration))
        e = max(0.0, min(float(a["t_end"]), duration))
        if e < s:
            s, e = e, s
        clean.append({**a, "t_start": round(s, 3), "t_end": round(e, 3)})
    clean.sort(key=lambda a: (a["t_start"], a["t_end"]))

    out = []
    for a in clean:
        if out and a["t_start"] < out[-1]["t_end"]:
            prev = out[-1]
            if a["t_start"] <= prev["t_start"]:   # 头部重叠 → 把本幕起点推到前一幕结尾
                a["t_start"] = prev["t_end"]
            else:                                  # 尾部嵌套 → 把前一幕结尾收到本幕起点
                prev["t_end"] = round(a["t_start"], 3)
        if a["t_end"] > a["t_start"]:              # 只保留正宽度幕
            out.append(a)
    return out


# ── pacing 计算（确定性，来自镜头线） ────────────────────────────────
# cuts_per_min 阈值 → label（N1 初值，§10 标定）。
_PACING_BINS = [(12, "slow"), (24, "medium"), (40, "medium-fast"),
                (80, "fast"), (float("inf"), "hyper-cut")]


def _pacing_label(cuts_per_min: float) -> str:
    for hi, name in _PACING_BINS:
        if cuts_per_min < hi:
            return name
    return "hyper-cut"


def compute_pacing(det: dict, win: float = 3.0) -> dict:
    """det = fx_detect.build_windows 输出（含 duration, shots[]）→ 确定性节奏画像。

    cut = 相邻镜头边界（不含 0）。fastest_window = 长 win 秒滑窗内 cut 数最多的区间。
    """
    shots = det.get("shots", [])
    dur = float(det.get("duration") or 0.0)
    durs = [float(s["dur"]) for s in shots]
    n = len(durs)
    avg = sum(durs) / n if n else 0.0
    std = (sum((d - avg) ** 2 for d in durs) / n) ** 0.5 if n else 0.0
    cuts = [float(s["start"]) for s in shots[1:]]  # 镜头切点
    cuts_per_min = (len(cuts) / dur * 60.0) if dur > 0 else 0.0

    fastest = [0.0, round(min(win, dur), 3)]
    best = -1
    if cuts and dur > 0:
        step = 0.5
        t = 0.0
        while t + win <= dur + 1e-6:
            c = sum(1 for x in cuts if t <= x < t + win)
            if c > best:
                best, fastest = c, [round(t, 3), round(t + win, 3)]
            t += step
    return {
        "avg_shot_s": round(avg, 3),
        "std_shot_s": round(std, 3),
        "n_cuts": len(cuts),
        "cuts_per_min": round(cuts_per_min, 2),
        "label": _pacing_label(cuts_per_min),
        "fastest_window": fastest,
    }


# ── doubao 合成层 ─────────────────────────────────────────────────────
def synth_prompt(arc: dict, shots: list, pacing: dict, duration: float) -> str:
    """构造合成 prompt：ARC 四任务素材 + 确定性镜头线/节奏 → 闭集 narrative JSON。"""
    hooks = ", ".join(f"{k}（{v}）" for k, v in HOOK_TYPES.items())
    structs = ", ".join(f"{k}（{v}）" for k, v in NARRATIVE_STRUCTURES.items())
    roles = ", ".join(ACT_ROLES)
    shot_lines = "\n".join(
        f"  镜头{s['shot_id']}: {s['start']}s–{s['end']}s (时长{s['dur']}s)"
        for s in shots)

    def block(task):
        r = arc.get(task)
        return f"【{task}】\n{r['answer']}" if r and r.get("answer") else f"【{task}】(无)"

    return (
        f"你是短视频叙事结构分析师。下面给你一条 {duration:.1f}s 短视频的两类材料：\n"
        f"(A) 一个理解模型(ARC-Hunyuan)对该视频做的 4 项分析(自由文本，已含时间戳)；\n"
        f"(B) 确定性的镜头时间线与节奏指标(来自镜头检测，时间戳准确，请以此为准)。\n\n"
        f"=== (A) ARC 分析 ===\n"
        f"{block('Summary')}\n\n{block('Segment')}\n\n{block('QA')}\n\n{block('Grounding')}\n\n"
        f"=== (B) 确定性镜头线（共 {len(shots)} 个镜头）===\n{shot_lines}\n"
        f"节奏：平均镜头 {pacing['avg_shot_s']}s，每分钟切 {pacing['cuts_per_min']} 次，"
        f"最快段 {pacing['fastest_window']}s。\n\n"
        f"请把以上收敛成结构化叙事 JSON。**只能使用上面证据里出现过的内容，"
        f"不要引入证据中没有的具体名词或情节**。要求：\n"
        f"- hook_type 只能从闭集选一个：[{hooks}]"
        f"（visual-shock 仅指突兀/惊吓/强烈反差的开场；单纯可爱/好看/治愈但不惊吓的用 direct 或 story-immersion）。\n"
        f"- structure 只能从闭集选一个：[{structs}]"
        f"（依据画面与 Segment 的实际内容判断，不要被提问措辞带偏）。\n"
        f"- acts[] 每幕的 role 只能从 [{roles}] 选；t_start/t_end 用秒，"
        f"尽量对齐上面的镜头边界；summary_cn 一句话。"
        f"**acts 必须是按时间顺序、首尾相接、互不重叠的连续区间**"
        f"（前一幕 t_end = 后一幕 t_start，hook/cta 也各占独立区间，不要嵌套进相邻幕）。\n"
        f"- emotion_curve[] 给带时间戳(秒)的情绪点 {{t, emotion(中文短词), valence(-1~1)}}；"
        f"**严格按证据：若情绪全程平稳/无明显变化，只给 1~2 个点描述该稳定状态，不要编造起伏弧线**。\n"
        f"- key_moments[] 用 Grounding 的时间(转成秒)：{{t_start, t_end, label, src:\"grounding\"}}。\n"
        f"- cta 没有就填 null；content_tags 给 3~5 个中文标签。\n"
        f"只输出 JSON，不要多余文字：\n"
        f'{{"hook_type":"<闭集>","hook_desc_cn":"...","structure":"<闭集>",'
        f'"acts":[{{"role":"<闭集>","t_start":0.0,"t_end":3.0,"summary_cn":"..."}}],'
        f'"theme_cn":"...","cta":null,"content_tags":["..."],'
        f'"emotion_curve":[{{"t":1.5,"emotion":"无奈","valence":-0.3}}],'
        f'"key_moments":[{{"t_start":12.0,"t_end":15.0,"label":"高潮","src":"grounding"}}]}}'
    )


def synth_narrative(arc: dict, shots: list, pacing: dict, duration: float,
                    creds=None, max_tokens=2000, k=1) -> dict:
    """调 doubao 合成 → dict。解析失败返回 {"_raw": text, "_parse_error": True}。

    k>1：对 `structure`(run-to-run 最易漂的高层标签,spec §11)做多数投票稳住,
    代表解析取 structure 命中多数的那次(其余字段保持自洽,不跨次拼接)。ARC 仍走缓存,
    投票只重 doubao synth 这一调用 → +（k-1）次 doubao/每跑。
    """
    creds = creds or fc.load_creds()
    prompt = synth_prompt(arc, shots, pacing, duration)
    k = max(1, int(k))
    runs = []
    for _ in range(k):
        out = fc.vlm([{"type": "text", "text": prompt}], creds=creds,
                     max_tokens=max_tokens, temperature=0.0)
        runs.append((fc.parse_json(out["text"]), out.get("model"), out["text"]))
    good = [(p, m) for p, m, _ in runs if p is not None]
    if not good:
        first = runs[0]
        return {"_raw": first[2], "_parse_error": True, "_model": first[1]}
    from collections import Counter
    structure = Counter(p.get("structure") for p, _ in good).most_common(1)[0][0]
    parsed, model = next(((p, m) for p, m in good if p.get("structure") == structure), good[0])
    parsed["structure"] = structure
    parsed["acts"] = normalize_acts(parsed.get("acts"), duration)  # 规整外部非确定输出
    parsed["_model"] = model
    if k > 1:
        parsed["_k"] = k
        parsed["_structure_votes"] = [p.get("structure") for p, _ in good]
    return parsed
