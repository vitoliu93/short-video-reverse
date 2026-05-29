#!/usr/bin/env python3
"""模块 A:BGM 分离(Demucs / HTDemucs)。

抖音音轨是「旁白人声 + 背景乐 + 音效」混合,直接做 DSP/embedding 都会被人声污染。
本模块把伴奏(music stem)抠出来,作为模块 C 与 B2 的共同输入(见 spec §2)。

  video.mp4 ──ffmpeg──> audio.wav ──Demucs──> music.wav (= drums+bass+other), vocals.wav

库内建库不需要本模块(库本身是纯乐曲);只有视频反解侧用。
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import soundfile as sf
import torch

MUSIC_STEMS = ("drums", "bass", "other")  # 非人声 = 伴奏


def extract_audio(video: Path, out_wav: Path, sr: int = 44100) -> Path:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "2", "-ar", str(sr), str(out_wav)],
        check=True, capture_output=True,
    )
    return out_wav


def separate(audio: Path, out_dir: Path, model_name: str = "htdemucs") -> dict[str, Path]:
    """返回 {'music': music.wav, 'vocals': vocals.wav}。music = 非人声 stem 之和。"""
    import soundfile as sf
    from demucs.apply import apply_model
    from demucs.audio import AudioFile
    from demucs.pretrained import get_model

    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    model = get_model(model_name)
    model.to(device).eval()

    wav = AudioFile(audio).read(streams=0, samplerate=model.samplerate, channels=model.audio_channels)
    ref = wav.mean(0)                              # demucs 期望的标准化
    wav_n = (wav - ref.mean()) / ref.std()
    sources = apply_model(model, wav_n[None], device=device, split=True, overlap=0.25)[0]
    sources = sources * ref.std() + ref.mean()
    stems = dict(zip(model.sources, sources))      # e.g. drums/bass/other/vocals

    out_dir.mkdir(parents=True, exist_ok=True)
    music = sum(stems[s] for s in MUSIC_STEMS)
    paths = {"music": out_dir / "music.wav", "vocals": out_dir / "vocals.wav"}
    # torchaudio 2.11 的 save 走 torchcodec(未装),直接用 soundfile 写([ch,n]→[n,ch])
    sf.write(str(paths["music"]), music.T.cpu().numpy(), model.samplerate)
    sf.write(str(paths["vocals"]), stems["vocals"].T.cpu().numpy(), model.samplerate)
    return paths


def run(src: Path, out_dir: Path) -> dict[str, Path]:
    """src 可为视频或音频;视频先抽音。"""
    if src.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        with tempfile.TemporaryDirectory() as td:
            wav = extract_audio(src, Path(td) / "audio.wav")
            return separate(wav, out_dir)
    return separate(src, out_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="视频或音频文件")
    ap.add_argument("--out", type=Path, required=True, help="输出目录")
    args = ap.parse_args()
    paths = run(args.src, args.out)
    for k, p in paths.items():
        print(f"  {k}: {p} ({sf.info(p).duration:.1f}s)")


if __name__ == "__main__":
    main()
