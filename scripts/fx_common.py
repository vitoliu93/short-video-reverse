#!/usr/bin/env python3
"""fx_common — 转场/特效反解管线的契约层（口径集中在这里）。

内容：
- VLM 客户端：直连火山引擎 Ark `/api/coding` + `doubao-seed-2.0-pro`（确定性后端，
  X1 实测唯一既能锁定又支持视觉的组合），Anthropic Messages 流式(SSE)，强制 UTF-8。
- 帧采样：ffmpeg 抽帧 + 跨窗口均匀采样。
- 闭集 taxonomy：转场/特效标签 + 剪映 12 大类映射。
- prompt 模板：转场分类 / 特效描述。

为何不用 ICC Router 的 `agent-vision`：该 alias 负载均衡到不确定后端
（实测落到 kimi-k2.6 / doubao-seed-2.0-code），实验不可复现。见 spec §8 / preflight。
"""
import base64
import json
import os
import re
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT.parent / "icccut-agents"          # monorepo 兄弟项目，存放 Ark 凭据
ENV_FILES = [AGENTS_DIR / ".env.test", AGENTS_DIR / ".env"]

ARK_BASE_DEFAULT = "https://ark.cn-beijing.volces.com/api/coding"
ARK_MODEL_DEFAULT = "doubao-seed-2.0-pro"

# ── 闭集 taxonomy（转场） ─────────────────────────────────────────────
# 给 VLM 的 type 只能从这里选；映射到剪映官方 12 大转场类目。
TRANSITION_TAGS = [
    "hard-cut", "dissolve", "fade-to-black", "fade-to-white", "flash",
    "push", "slide", "wipe", "zoom-in", "zoom-out", "spin", "glitch",
    "blur", "whip-pan", "mask", "none",
]
# 剪映 12 类: Overlay / Camera / Blur / Basic / Light Effect / Glitch /
#            Distortion / Slide / Split / Mask / MG / Social Media
TRANSITION_CAPCUT = {
    "hard-cut": "",            # 直接硬切，无转场效果
    "dissolve": "Overlay",
    "fade-to-black": "Basic",
    "fade-to-white": "Basic",
    "flash": "Light Effect",
    "push": "Slide",
    "slide": "Slide",
    "wipe": "Slide",
    "zoom-in": "Camera",
    "zoom-out": "Camera",
    "spin": "Camera",
    "whip-pan": "Camera",
    "glitch": "Glitch",
    "blur": "Blur",
    "mask": "Mask",
    "none": "",
}
TRANSITION_CN = {
    "hard-cut": "硬切", "dissolve": "叠化", "fade-to-black": "淡入黑场",
    "fade-to-white": "淡入白场", "flash": "闪白/闪黑", "push": "推移",
    "slide": "滑动", "wipe": "擦除", "zoom-in": "推近", "zoom-out": "拉远",
    "spin": "旋转", "glitch": "故障", "blur": "模糊转场", "whip-pan": "甩镜",
    "mask": "蒙版/遮罩", "none": "无转场",
}

# ── 闭集 taxonomy（镜头内特效，best-effort） ─────────────────────────
EFFECT_TAGS = [
    "shake", "zoom-pulse", "rgb-split", "light-leak", "particles",
    "blur-pulse", "color-filter", "vignette", "film-grain", "speed-ramp",
    "freeze-frame", "none",
]
EFFECT_CN = {
    "shake": "抖动", "zoom-pulse": "卡点缩放", "rgb-split": "RGB错位",
    "light-leak": "漏光", "particles": "粒子", "blur-pulse": "模糊脉冲",
    "color-filter": "调色滤镜", "vignette": "暗角", "film-grain": "颗粒/胶片",
    "speed-ramp": "变速", "freeze-frame": "定格", "none": "无明显特效",
}


# ── 凭据 ──────────────────────────────────────────────────────────────
def _parse_env(paths):
    env = {}
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def load_creds():
    """返回 {base_url, key, model}。os.environ 优先，其次 icccut-agents/.env(.test)。"""
    fenv = _parse_env(ENV_FILES)
    key = os.environ.get("VOLC_ARK_API_KEY") or fenv.get("VOLC_ARK_API_KEY")
    if not key:
        raise SystemExit(
            "缺少 VOLC_ARK_API_KEY（在 icccut-agents/.env 或环境变量里设置）。")
    return {
        "base_url": (os.environ.get("VOLC_ARK_BASE_URL")
                     or fenv.get("VOLC_ARK_BASE_URL") or ARK_BASE_DEFAULT).rstrip("/"),
        "key": key,
        "model": (os.environ.get("VOLC_ARK_MODEL")
                  or fenv.get("VOLC_ARK_MODEL") or ARK_MODEL_DEFAULT),
    }


# ── 帧采样 ────────────────────────────────────────────────────────────
def extract_frame(video, t, width=640):
    """ffmpeg 抽单帧 → JPEG bytes，缩到 width 宽。"""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{float(t):.3f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={width}:-1", "-q:v", "4",
         # -strict unofficial: 部分抖音片是 full-range YUV，mjpeg 默认拒绝（X3 实测 hair 末帧报错）
         "-strict", "unofficial",
         "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        capture_output=True,
    )
    if out.returncode != 0 or not out.stdout:
        raise RuntimeError(f"ffmpeg 抽帧失败 t={t}: {out.stderr.decode()[:200]}")
    return out.stdout


def sample_window(video, t_start, t_end, n=8, width=640):
    """在 [t_start, t_end] 均匀采 n 帧，返回 [(t, jpeg_bytes), ...]。"""
    if n < 2:
        n = 2
    step = (t_end - t_start) / (n - 1)
    times = [round(t_start + step * i, 3) for i in range(n)]
    return [(t, extract_frame(video, t, width)) for t in times]


def img_block(jpg_bytes):
    return {"type": "image", "source": {
        "type": "base64", "media_type": "image/jpeg",
        "data": base64.b64encode(jpg_bytes).decode()}}


# ── VLM 客户端（Ark Anthropic SSE） ──────────────────────────────────
def vlm(blocks, creds=None, system=None, max_tokens=1500, temperature=0.0):
    """调用 Ark doubao-seed-2.0-pro（流式）。返回 {thinking, text, model, usage, stop_reason}。

    temperature 默认 0 以压低 run-to-run 漂移；但实测 Ark/doubao 即便 temp=0、请求逐字
    相同，模糊转场标签仍会漂（glitch↔wipe，见 spec §11，属服务端 token 级非确定）。
    彻底稳定需对 type 做 k 次多数投票（X3）。定位(TransNetV2+ffmpeg)不受影响、完全确定。
    """
    creds = creds or load_creds()
    payload = {
        "model": creds["model"], "max_tokens": max_tokens, "stream": True,
        "temperature": temperature,
        "messages": [{"role": "user", "content": blocks}],
    }
    if system:
        payload["system"] = system
    headers = {
        "Authorization": f"Bearer {creds['key']}", "x-api-key": creds["key"],
        "anthropic-version": "2023-06-01", "Content-Type": "application/json",
    }
    r = requests.post(f"{creds['base_url']}/v1/messages", json=payload,
                      headers=headers, timeout=180, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"VLM HTTP {r.status_code}: {r.text[:400]}")
    r.encoding = "utf-8"  # Ark 不声明 charset，强制 UTF-8 否则中文 mojibake
    thinking, text, model_seen, usage, stop = [], [], None, {}, None
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        chunk = raw[len("data:"):].strip()
        if chunk == "[DONE]":
            break
        try:
            ev = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "message_start":
            model_seen = ev.get("message", {}).get("model")
        elif t == "content_block_delta":
            d = ev.get("delta", {})
            if d.get("type") == "thinking_delta":
                thinking.append(d.get("thinking", ""))
            elif d.get("type") == "text_delta":
                text.append(d.get("text", ""))
        elif t == "message_delta":
            usage = ev.get("usage", usage) or usage
            stop = ev.get("delta", {}).get("stop_reason", stop)
    return {"thinking": "".join(thinking), "text": "".join(text),
            "model": model_seen, "usage": usage, "stop_reason": stop}


def parse_json(text):
    """从 VLM 回答里抠出 JSON（容忍 ```json 围栏和前后噪声）。失败返回 None。"""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        i, j = text.find("{"), text.rfind("}")
        blob = text[i:j + 1] if i != -1 and j > i else None
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


# ── prompt 模板 ───────────────────────────────────────────────────────
def transition_prompt(n_frames):
    tags = ", ".join(f"{t}（{TRANSITION_CN[t]}）" for t in TRANSITION_TAGS)
    return (
        f"下面是一个短视频里连续采样的 {n_frames} 帧画面，按时间先后排列，"
        f"横跨一个疑似镜头切换/转场的位置。请判断这里是否发生了转场，并分类。\n"
        f"闭集标签（type 只能从中选一个）：[{tags}]。\n"
        f"只输出 JSON，不要多余文字：\n"
        f'{{"transition_present": true/false, "type": <上面某个英文标签>, '
        f'"confidence": 0到1的小数, '
        f'"description_cn": "用自然语言描述这个转场是怎么发生的", '
        f'"description_en": "natural language description in english", '
        f'"capcut_tags": ["在剪映里可能对应的转场/特效名"], '
        f'"visual_cues": "你依据画面里的什么线索做出判断"}}'
    )


def effect_prompt(n_frames):
    tags = ", ".join(f"{t}（{EFFECT_CN[t]}）" for t in EFFECT_TAGS)
    return (
        f"下面是一个短视频【同一个镜头内部】连续采样的 {n_frames} 帧，按时间先后排列。"
        f"请判断这个镜头是否被加了明显的画面特效（不是转场，是镜头内的滤镜/动态效果）。\n"
        f"闭集标签（types 可多选）：[{tags}]。\n"
        f"只输出 JSON：\n"
        f'{{"effect_present": true/false, "types": [<英文标签...>], '
        f'"confidence": 0到1, "description_cn": "描述看到的特效", '
        f'"description_en": "...", "visual_cues": "判断依据"}}'
    )
