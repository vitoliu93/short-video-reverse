#!/usr/bin/env python3
"""compose_common — 反解结果 → KOX icccut_draft 映射的共享契约/口径(第6条能力 compose_)。

集中处:① 映射表(反解闭集→剪映闭集,均过 validate_params --list-values 校验)
       ② 坐标/单位换算器  ③ action builders + draft 信封  ④ 统一反解 JSON 合并  ⑤ 缓存载入
校验靠兄弟仓 icccut-agents 的 validate_action(见 compose_validate.py)。改映射口径改这里一处。

设计依据见 docs/plan/2026-05-30-compose-reverse-to-draft/spec.md(§映射契约 + §9 C0)。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
ICC = Path("/Users/liujiaxi/codebase/icc/kox-base/icccut-agents")   # 兄弟仓(校验器+枚举源)

# ===================== 映射表:反解闭集 → 剪映闭集 =====================
# 取值均已过 `validate_params.py --param X --list-values`(见 spec §9 / C1 自测)。
# None = 该 tag 不映射(故意省略,如硬切;或校验子集无忠实目标 → unmapped 诚实记录)。

# fx transitions[].type(16 闭集) → 剪映 transition 名
FX_TRANS_TO_JY: dict[str, Optional[str]] = {
    "hard-cut": None, "none": None,            # 硬切/无:不加转场(相邻镜头直接相接)
    "dissolve": "叠化", "fade-to-black": "闪黑", "fade-to-white": "闪白",
    "flash": "白光快闪", "push": "推近", "slide": "滑动", "wipe": "渐变擦除",
    "zoom-in": "模糊放大", "zoom-out": "模糊缩小", "spin": "中心旋转",
    "glitch": "信号故障", "blur": "模糊", "whip-pan": "横移模糊", "mask": "圆形遮罩",
}

# fx effects[].types(12 闭集) → (剪映名, 路由)。路由:scene→add_effect / filter→add_filter / speed→add_video.speed / None→不可映射
FX_EFFECT_TO_JY: dict[str, tuple[Optional[str], Optional[str]]] = {
    "none": (None, None),
    "shake": ("回弹摇摆", "scene"), "zoom-pulse": ("变焦推镜", "scene"),
    "rgb-split": ("RGB描边", "scene"),    # 注:描边≠色差,校验子集内唯一含 RGB 项,语义有损(见 spec §12)
    "light-leak": ("复古发光", "scene"),
    "particles": ("仙尘闪闪", "scene"), "blur-pulse": ("模糊", "scene"),
    "film-grain": ("噪点", "scene"),
    "vignette": (None, "scene"),        # 暗角 不在校验 scene 子集 → unmapped
    "freeze-frame": (None, "scene"),    # 故障定格 不在校验子集 → unmapped
    "color-filter": (None, "filter"),   # 调色 → add_filter(filter_type 当前不过枚举校验)
    "speed-ramp": (None, "speed"),      # 实为 speed 参数,无 ramp 数据 → unmapped-as-effect
}

# font texts[].animation(4) → 剪映 text intro_animation 名
FONT_ANIM_TO_JY: dict[str, Optional[str]] = {
    "none": None, "typewriter": "打字机_I", "scroll": "向上滑动", "pop": "弹入",
}

# 轨道层级约定(draft-manager §轨道)
TRACK = {
    "video": ("video", 0), "bgm": ("audio_bgm", 1000), "voice": ("audio_main", 1),
    "effect": ("effects", 8000), "filter": ("filter", 7000),
    "title": ("title", 14000), "subtitle": ("subtitle", 15000),
}

CJK_W_FACTOR = 5.2          # icccut: CJK 字宽 ≈ 5.2*font_size(px) → font_size ≈ 字高px/CJK_W_FACTOR
TRANS_ATTACH_TOL = 0.35     # |t_center − shot.end| ≤ 此值 → 转场挂该镜头 out 点。宽转场(如 glitch)的 center 可偏离切点约半个转场时长,0.25 太紧会漏挂,放宽到 0.35(< DEFAULT_TRANS_DUR/2 量级)。C3 修
DEFAULT_TRANS_DUR = 0.5     # 默认转场时长(s);gap 是 TransNet 帧级边界非视觉时长


# ===================== 映射 + 换算器 =====================
def map_transition(tag: str) -> Optional[str]:
    return FX_TRANS_TO_JY.get(tag, None)


def map_effect(tag: str) -> tuple[Optional[str], Optional[str]]:
    """→ (剪映名 或 None, 路由 scene/filter/speed/None)。未知 tag 视为不可映射。"""
    return FX_EFFECT_TO_JY.get(tag, (None, None))


def map_font_anim(tag: str) -> Optional[str]:
    return FONT_ANIM_TO_JY.get(tag, None)


def norm_font(name: Optional[str]) -> Optional[str]:
    """font_ 匹配名(常带连字符)→ 剪映 Font_type 标识名(下划线)。"""
    return name.replace("-", "_") if name else name


def bbox_to_transform(bbox: list[float]) -> tuple[float, float]:
    """bbox[x,y,w,h] 归一左上 → (transform_x, transform_y) 中心原点半画布单位。
    tx=(cx-0.5)*2(右正), ty=(0.5-cy)*2(上正)。C0 核:cy=0.84→ty=-0.68。"""
    x, y, w, h = bbox
    cx, cy = x + w / 2.0, y + h / 2.0
    return round((cx - 0.5) * 2.0, 4), round((0.5 - cy) * 2.0, 4)


def size_rel_to_font_size(size_rel: Optional[float], frame_h: int) -> Optional[float]:
    """size_rel(占帧高) → 剪映 font_size(近似)。字高px = size_rel*H;font_size≈字高/CJK_W_FACTOR。
    近似口径,未逐字标定(spec known-limitation)。"""
    if not size_rel:
        return None
    return round(size_rel * frame_h / CJK_W_FACTOR, 1)


# ===================== 转场挂载 =====================
def assign_transitions(shots: list[dict], transitions: list[dict]) -> dict[int, dict]:
    """每个 present 转场 → 唯一最近的镜头 out 点(argmin |t_center − shot.end|),一对一。

    一遍扫描而非「逐镜头找最近转场」:后者无消费标记 → 一个转场会挂到多个相邻短镜头
    (重复),离任何边界都略远的宽转场又会漏挂(C3 抓修的真 bug)。这里反过来:每个转场
    认领它最近的那个 out 点;若两个转场抢同一镜头,留更近的。保证 转场↔镜头 单射。
    """
    ends = [s["end"] for s in shots]
    claimed: dict[int, tuple[float, dict]] = {}   # shot_idx → (dist, transition)
    for t in transitions:
        if not t.get("present"):
            continue
        tc = t.get("t_center")
        if tc is None or not ends:
            continue
        i = min(range(len(ends)), key=lambda k: abs(ends[k] - tc))
        d = abs(ends[i] - tc)
        if d > TRANS_ATTACH_TOL:
            continue                              # 离任何 out 点都远 → 不挂(诚实丢弃)
        if i not in claimed or d < claimed[i][0]:
            claimed[i] = (d, t)
    return {i: t for i, (d, t) in claimed.items()}


# ===================== Draft 信封 + action builders =====================
ACTION_SKILL = {  # action_type → skill 分组名
    "add_video": "add-video", "add_image": "add-image", "add_text": "add-text",
    "add_audio": "add-audio", "add_effect": "add-effect", "add_filter": "add-filter",
}


@dataclass
class DraftBuilder:
    """累积 action、管理 id/index/占位符,finalize 出合法 icccut_draft 信封。"""
    width: int
    height: int
    draft_id: str = "reverse_compose"
    template_type: str = "reverse_compose"
    _actions: list[dict] = field(default_factory=list)
    _inputs: dict[str, dict] = field(default_factory=dict)
    _idx: int = 0
    _media_n: int = 0
    _audio_n: int = 0
    _lanes: dict[str, list[float]] = field(default_factory=dict)   # 轨道组 → 各 lane 当前末尾时间(防同轨重叠)
    unmapped: list[dict] = field(default_factory=list)   # 诚实记录映射不到的反解信号

    # --- 内部 ---
    def _act(self, action_type: str, params: dict) -> dict:
        self._idx += 1
        return {"type": "action", "action_type": action_type, "id": uuid.uuid4().hex[:12],
                "index": self._idx,
                "params": {**params, "draft_id": self.draft_id, "width": self.width, "height": self.height}}

    def _media_ph(self) -> str:
        self._media_n += 1
        k = f"media_{self._media_n}"
        self._inputs[k] = {"type": "video_url", "default": "", "protected": False}
        return f"${{{k}}}"

    def _audio_ph(self, default: str = "") -> str:
        self._audio_n += 1
        k = f"audio_{self._audio_n}"
        self._inputs[k] = {"type": "audio_url", "default": default, "protected": False}
        return f"${{{k}}}"

    def _note_unmapped(self, kind: str, tag: str, reason: str, t: Any = None):
        self.unmapped.append({"kind": kind, "tag": tag, "reason": reason, "at": t})

    def _alloc_lane(self, group: str, base_name: str, base_idx: int,
                    t_start: float, t_end: float) -> tuple[str, int]:
        """同轨时间重叠非法(icccut)→ 把同组并发片段分配到不同 lane(轨)。
        复用首个末尾<=t_start 的 lane,否则新开。返回 (track_name, track_render_index)。"""
        lanes = self._lanes.setdefault(group, [])
        for i, end in enumerate(lanes):
            if end <= t_start + 1e-6:
                lanes[i] = t_end
                return (base_name if i == 0 else f"{base_name}_{i}", base_idx + i)
        lanes.append(t_end)
        i = len(lanes) - 1
        return (base_name if i == 0 else f"{base_name}_{i}", base_idx + i)

    # --- builders ---
    def add_video_shot(self, shot: dict, tr: Optional[dict] = None) -> dict:
        """一个镜头 → 一段主轨 add_video(媒体占位)。tr=预先分配给该镜头 out 点的转场(或 None)。"""
        tname, tidx = TRACK["video"]
        p = {"video_url": self._media_ph(), "start": 0.0, "end": round(shot["dur"], 3),
             "target_start": round(shot["start"], 3), "track_name": tname, "track_render_index": tidx}
        if tr:
            jy = map_transition(tr["type"])
            if jy:
                p["transition"] = jy
                # 实测窗宽 t_end−t_start(TransNetV2⊕ffmpeg 候选窗),缺失退默认;
                # 仍 ≤ 0.8×镜头时长兜底(转场不该吃满镜头)。
                ts, te = tr.get("t_start"), tr.get("t_end")
                meas = round(te - ts, 3) if (ts is not None and te is not None and te > ts) else DEFAULT_TRANS_DUR
                p["transition_duration"] = min(meas, round(shot["dur"] * 0.8, 3))
            elif tr["type"] not in ("hard-cut", "none"):
                self._note_unmapped("transition", tr["type"], "no validated 剪映 transition", tr.get("t_center"))
        a = self._act("add_video", p)
        self._actions.append(a)
        return a

    def add_text_event(self, ev: dict, frame_h: int) -> dict:
        """font_ texts[] 一条 → add_text(坐标/颜色/描边/动画换算)。"""
        t0, t1 = round(ev["appear"]["first"], 3), round(ev["appear"]["last"], 3)
        base_n, base_i = TRACK["subtitle"]
        tname, tidx = self._alloc_lane("subtitle", base_n, base_i, t0, t1)   # 同时多条字幕→分轨
        tx, ty = bbox_to_transform(ev["bbox"])
        p: dict[str, Any] = {
            "text": ev["text"], "start": t0, "end": t1,
            "transform_x": tx, "transform_y": ty, "track_name": tname, "track_render_index": tidx,
        }
        font = norm_font((ev.get("font") or {}).get("match"))
        if font:
            p["font"] = font            # 未命中 Font_type 时校验会拒 → 由 compose_validate 兜
        col = (ev.get("color") or {}).get("fill")
        if col:
            p["font_color"] = col
        fs = size_rel_to_font_size(ev.get("size_rel"), frame_h)
        if fs:
            p["font_size"] = fs
        stroke = (ev.get("decoration") or {}).get("stroke")
        if stroke:
            p["border_width"] = stroke.get("width_px", 4)
            if stroke.get("color"):
                p["border_color"] = stroke["color"]
        if (ev.get("decoration") or {}).get("shadow"):
            p["shadow_enabled"] = True
        anim = map_font_anim(ev.get("animation", "none"))
        if anim:
            p["intro_animation"] = anim
        a = self._act("add_text", p)
        self._actions.append(a)
        return a

    def add_bgm(self, bgm: dict) -> Optional[dict]:
        """bgm{} → add_audio(媒体占位,default=检索到的相似 BGM url)。"""
        if not bgm.get("present"):
            return None
        tname, tidx = TRACK["bgm"]
        default_url = (bgm.get("match") or {}).get("audio_url", "")
        dur = round(bgm["end"] - bgm["start"], 3)
        p = {"audio_url": self._audio_ph(default_url), "target_start": round(bgm["start"], 3),
             "start": 0.0, "end": dur, "volume": 0.6, "track_name": tname, "track_render_index": tidx}
        a = self._act("add_audio", p)
        self._actions.append(a)
        return a

    def add_effect_window(self, tag: str, t_start: float, t_end: float) -> Optional[dict]:
        """fx effect tag → add_effect(scene) / add_filter(filter) / 记 unmapped。"""
        name, route = map_effect(tag)
        if route == "scene" and name:
            base_n, base_i = TRACK["effect"]
            tname, tidx = self._alloc_lane("effect", base_n, base_i, t_start, t_end)
            a = self._act("add_effect", {"effect_type": name, "effect_category": "scene", "params": [],
                                         "start": round(t_start, 3), "end": round(t_end, 3),
                                         "track_name": tname, "track_render_index": tidx})
            self._actions.append(a)
            return a
        if route == "filter" and name:
            return self.add_filter_window(name, t_start, t_end)
        # scene-无忠实目标 / speed / 未知 → 诚实记录
        if tag not in ("none",):
            self._note_unmapped("effect", tag, f"route={route} no validated target", round(t_start, 3))
        return None

    def add_filter_window(self, filter_name: str, t_start: float, t_end: float) -> dict:
        base_n, base_i = TRACK["filter"]
        tname, tidx = self._alloc_lane("filter", base_n, base_i, t_start, t_end)
        a = self._act("add_filter", {"filter_type": filter_name, "intensity": 80,
                                     "start": round(t_start, 3), "end": round(t_end, 3),
                                     "track_name": tname, "track_render_index": tidx})
        self._actions.append(a)
        return a

    # --- 出稿 ---
    def finalize(self, narrative: Optional[dict] = None, extra_meta: Optional[dict] = None) -> dict:
        """按 skill 分组 actions → 合法 icccut_draft 信封。"""
        groups: list[dict] = []
        for a in self._actions:
            skill = ACTION_SKILL.get(a["action_type"], a["action_type"])
            if not groups or groups[-1]["skill"] != skill:
                groups.append({"skill": skill, "skill_type": "core", "actions": []})
            groups[-1]["actions"].append(a)
        meta = {"template_type": self.template_type, "draft_id": self.draft_id,
                "canvas": {"width": self.width, "height": self.height}}
        if extra_meta:
            meta.update(extra_meta)
        draft = {"meta": meta, "inputs": dict(self._inputs), "script": groups}
        if narrative is not None:
            draft["reverse_narrative"] = narrative   # 叙事作 meta 注释,非时间线 action
        if self.unmapped:
            draft["_unmapped"] = self.unmapped
        return draft


# ===================== 统一反解 JSON 合并 =====================
def merge_reverse(stem: str, fx: Optional[dict], font: Optional[dict],
                  narr: Optional[dict], bgm: Optional[dict]) -> dict:
    """5 路反解输出 → 统一反解 JSON {shots,subtitles,bgm,transitions,effects,narrative,provenance}。
    缺哪路对应段落留空 + provenance 记 present=false。"""
    out: dict[str, Any] = {"video": stem, "shots": [], "subtitles": [], "bgm": None,
                           "transitions": [], "effects": [], "narrative": None,
                           "provenance": {}}
    # shots:优先 narr(有 summary);否则从 fx 不可得镜头线 → 留空
    if narr:
        out["shots"] = narr.get("shots", [])
        out["narrative"] = narr.get("narrative")
        out["frame_duration"] = narr.get("duration")
        for k in ("emotion_curve", "key_moments", "content_tags"):
            if k in narr:
                out[k] = narr[k]
    if fx:
        out["transitions"] = [t for t in fx.get("transitions", []) if t.get("present")]
        out["effects"] = [e for e in fx.get("effects", []) if e.get("present")]
        out["frame"] = fx.get("frame")
        out.setdefault("frame_duration", fx.get("duration"))
        if not out["shots"]:                      # 无 narr 时,至少从 fx 拿镜头数(无时间线)
            out["provenance"]["shots_note"] = f"narr absent; fx n_shots={fx.get('n_shots')}"
    if font:
        out["subtitles"] = font.get("texts", [])
        out.setdefault("frame", font.get("frame"))
    if bgm:
        out["bgm"] = bgm.get("bgm")
    out["provenance"]["present"] = {"fx": fx is not None, "font": font is not None,
                                    "narr": narr is not None, "bgm": bgm is not None}
    return out


# ===================== 缓存载入(编排第一步) =====================
PIPELINES = ("fx", "font", "narr", "bgm")


def load_cached(stem: str, outputs_dir: Path = ROOT / "outputs") -> dict[str, Optional[dict]]:
    """载入各管线已落盘的 outputs/<pfx>/<stem>.json;缺失→None(部分失败降级)。"""
    res: dict[str, Optional[dict]] = {}
    for pfx in PIPELINES:
        p = outputs_dir / pfx / f"{stem}.json"
        res[pfx] = json.loads(p.read_text()) if p.is_file() else None
    return res


def canvas_of(cached: dict[str, Optional[dict]]) -> tuple[int, int]:
    """从任一带 frame 的反解输出取画布 [W,H]。"""
    for pfx in ("fx", "font"):
        d = cached.get(pfx)
        if d and d.get("frame"):
            w, h = d["frame"]
            return int(w), int(h)
    n = cached.get("narr")
    return (1080, 1920)   # 兜底竖屏


def build_draft_from_cached(stem: str, cached: dict[str, Optional[dict]]) -> tuple[dict, dict]:
    """统一反解 JSON + icccut_draft。返回 (unified, draft)。"""
    fx, font, narr, bgm = (cached.get(k) for k in ("fx", "font", "narr", "bgm"))
    unified = merge_reverse(stem, fx, font, narr, bgm)
    W, H = canvas_of(cached)
    b = DraftBuilder(width=W, height=H)
    # 主轨镜头 + 转场(先一对一分配转场到镜头 out 点,再逐镜头建 add_video)
    assigned = assign_transitions(unified["shots"], unified["transitions"])
    for i, shot in enumerate(unified["shots"]):
        b.add_video_shot(shot, assigned.get(i))
    # 字幕
    for ev in unified["subtitles"]:
        b.add_text_event(ev, H)
    # BGM
    if unified["bgm"]:
        b.add_bgm(unified["bgm"])
    # 特效
    for e in unified["effects"]:
        for tag in e.get("types", []):
            b.add_effect_window(tag, e["t_start"], e["t_end"])
    draft = b.finalize(narrative=unified.get("narrative"),
                       extra_meta={"reverse_source": "pixels", "reverse_stem": stem})
    return unified, draft
