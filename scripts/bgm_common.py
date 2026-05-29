#!/usr/bin/env python3
"""BGM 子模块共享件:CLAP 音频 embedding(M0 验证过的稳定口径)。

口径锁定(见 docs/BGM-反解-spec.md §4):
  - 模型 laion/larger_clap_music,transformers==4.46.3(get_audio_features 返回已投影向量)。
  - 每条取整首 3 个相对位置的 10s 窗口,均值池化 + L2 归一化。
  - 检索时减全库质心(mean-centering)再算 cosine。
"""
from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import torch
from transformers import ClapModel, ClapProcessor

MODEL_ID = "laion/larger_clap_music"        # 音频→音频检索(M0 验证:音乐相似度强)
TAG_MODEL_ID = "laion/larger_clap_general"  # 零样本文字打标签(music 版文字塔对单词标签几乎失效)
SR = 48_000
WIN_SEC = 10
WIN_POS = (0.25, 0.50, 0.75)


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_clap(device: str | None = None, model_id: str = MODEL_ID):
    device = device or pick_device()
    model = ClapModel.from_pretrained(model_id).to(device).eval()
    processor = ClapProcessor.from_pretrained(model_id)
    return model, processor, device


def load_windows(path: Path) -> tuple[list[np.ndarray], float]:
    """返回 (窗口列表, 时长秒)。解码失败返回 ([], 0.0),不静默吞——上层记录后跳过。"""
    try:
        y, _ = librosa.load(path, sr=SR, mono=True)
    except Exception as e:
        print(f"  [decode-fail] {Path(path).name}: {e}")
        return [], 0.0
    n = len(y)
    if n == 0:
        return [], 0.0
    dur = n / SR
    win = WIN_SEC * SR
    if n <= win:
        return [y], dur
    out = []
    for pos in WIN_POS:
        start = max(0, min(int(pos * n) - win // 2, n - win))
        out.append(y[start : start + win])
    return out, dur


@torch.no_grad()
def embed_windows(wins: list[np.ndarray], model, processor, device) -> np.ndarray:
    """一条曲的多个窗口 → 单个 L2 归一化向量(均值池化)。"""
    inputs = processor(audios=wins, sampling_rate=SR, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    feats = model.get_audio_features(**inputs)  # [num_win, D] 已投影
    v = feats.mean(dim=0)
    v = v / v.norm()
    return v.cpu().numpy()


def embed_file(path: Path, model, processor, device) -> tuple[np.ndarray | None, float]:
    wins, dur = load_windows(path)
    if not wins:
        return None, 0.0
    return embed_windows(wins, model, processor, device), dur


@torch.no_grad()
def embed_texts(texts: list[str], model, processor, device) -> np.ndarray:
    """文字 → 与音频同空间的 L2 归一化向量(零样本打标签用)。返回 [N,D]。"""
    inputs = processor(text=texts, return_tensors="pt", padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    feats = model.get_text_features(**inputs)
    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.cpu().numpy()


def center(emb: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    """减质心再 L2 归一化。emb 可为 [N,D] 或 [D]。"""
    out = emb - centroid
    norms = np.linalg.norm(out, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return out / norms
