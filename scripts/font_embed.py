#!/usr/bin/env python3
"""DINOv2 字形形状 embedding(可选实验,F3 提精度)。

动机:像素 NCC 在真实抖音上分数低(渲染器-gap)。DINOv2 的语义形状特征**可能**比逐像素更
鲁棒于渲染器差异(hinting/AA/字重渲染)。这里把和 NCC **同样的归一化掩码**(font_common.to_mask 出的
96² 二值)渲成黑字白底图喂 DINOv2,取 CLS,L2 归一化 → 余弦比对。同输入对比才公平。
"""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image

_MODEL = None
_PROC = None
MODEL_ID = "facebook/dinov2-small"


def _load():
    global _MODEL, _PROC
    if _MODEL is None:
        from transformers import AutoImageProcessor, AutoModel
        _PROC = AutoImageProcessor.from_pretrained(MODEL_ID)
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        _MODEL = AutoModel.from_pretrained(MODEL_ID).to(dev).eval()
        _MODEL._dev = dev
    return _MODEL, _PROC


def mask_to_img(mask: np.ndarray) -> Image.Image:
    """归一化二值掩码(墨=True)→ 黑字白底 RGB,加边距(DINOv2 偏好有 context)。"""
    a = (~mask * 255).astype(np.uint8)
    img = Image.fromarray(a).convert("RGB")
    pad = Image.new("RGB", (mask.shape[1] + 24, mask.shape[0] + 24), "white")
    pad.paste(img, (12, 12))
    return pad


@torch.no_grad()
def embed_masks(masks: list[np.ndarray], batch: int = 64) -> np.ndarray:
    """[N 掩码] → [N, D] L2 归一化 embedding(CLS token)。"""
    model, proc = _load()
    imgs = [mask_to_img(m) for m in masks]
    feats = []
    for i in range(0, len(imgs), batch):
        inp = proc(images=imgs[i:i + batch], return_tensors="pt")
        inp = {k: v.to(model._dev) for k, v in inp.items()}
        out = model(**inp).last_hidden_state[:, 0]      # CLS
        out = out / out.norm(dim=-1, keepdim=True)
        feats.append(out.cpu().numpy())
    return np.concatenate(feats)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import font_common as fc
    p = Path("assets/fonts/Aa全息黑体.ttf")
    masks = [fc.to_mask(fc.render_char(p, c)) for c in "字体测试"]
    masks = [m for m in masks if m is not None]
    e = embed_masks(masks)
    print(f"[embed] {len(masks)} glyphs → {e.shape}  dtype={e.dtype}  norm={np.linalg.norm(e[0]):.3f}")
    # 自相似 sanity:同字不同渲染应高,不同字应低
    import numpy as np
    print("  glyph-glyph cosine matrix:\n", np.round(e @ e.T, 2))
