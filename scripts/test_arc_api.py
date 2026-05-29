#!/usr/bin/env python3
"""Test ARC-Hunyuan-Video-7B hosted API with a local video file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs" / "arc"

BASE_URL = "https://arc.tencent.com"
SHORT_VIDEO_ENDPOINT = f"{BASE_URL}/cvc_function/arc_hunyuan_short_video/"
LONG_VIDEO_ENDPOINT = f"{BASE_URL}/cvc_function/arc_hunyuan_long_video/"
VALID_TASK_TYPES = {"MCQ", "Segment", "Grounding", "QA", "Summary"}


def load_token() -> str:
    token = os.environ.get("ARC_TOKEN", "").strip()
    if token:
        return token

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ARC_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    raise SystemExit("Missing ARC_TOKEN. Set env var or add it to .env")


def analyze_video(
    video_path: Path,
    prompt: str,
    task_type: str = "Summary",
    *,
    lang: str = "english",
    is_short_video: bool = True,
    timeout: int = 300,
) -> dict:
    if task_type not in VALID_TASK_TYPES:
        raise ValueError(f"task_type must be one of {sorted(VALID_TASK_TYPES)}")

    endpoint = SHORT_VIDEO_ENDPOINT if is_short_video else LONG_VIDEO_ENDPOINT
    headers = {"Authorization": load_token()}
    data = {"prompt": prompt, "task_type": task_type, "lang": lang}

    with video_path.open("rb") as video_file:
        files = {"file": (video_path.name, video_file, "video/mp4")}
        response = requests.post(
            endpoint,
            headers=headers,
            data=data,
            files=files,
            timeout=timeout,
        )

    response.raise_for_status()
    return response.json()


def output_path(video_path: Path, task_type: str) -> Path:
    return OUTPUT_DIR / f"{video_path.stem}_{task_type}.json"


def save_result(
    video_path: Path,
    prompt: str,
    task_type: str,
    lang: str,
    is_short_video: bool,
    result: dict,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "video": str(video_path),
            "task_type": task_type,
            "prompt": prompt,
            "lang": lang,
            "is_short_video": is_short_video,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
        "response": result,
    }
    path = output_path(video_path, task_type)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Call ARC-Hunyuan-Video-7B API")
    parser.add_argument(
        "video",
        nargs="?",
        default="assets/Lotus_MY26_Combined-15s_16x9_CLEAN_Audio-250207_v016.mp4",
        help="Path to mp4/mov video",
    )
    parser.add_argument(
        "--task-type",
        default="Summary",
        choices=sorted(VALID_TASK_TYPES),
        help="Short-video task type",
    )
    parser.add_argument(
        "--prompt",
        default="Describe the video content in detail, including visual scenes, audio, and key messages.",
        help="Question or instruction for the model",
    )
    parser.add_argument("--lang", default="english", choices=["english", "chinese"])
    parser.add_argument("--long-video", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--output",
        type=Path,
        help="Override output JSON path (default: outputs/arc/<video>_<task>.json)",
    )
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_file():
        raise SystemExit(f"Video not found: {video_path}")

    print(f"Uploading: {video_path}")
    print(f"Task: {args.task_type}")
    print(f"Prompt: {args.prompt}")
    print("Calling API...")

    result = analyze_video(
        video_path,
        prompt=args.prompt,
        task_type=args.task_type,
        lang=args.lang,
        is_short_video=not args.long_video,
        timeout=args.timeout,
    )

    saved_path = save_result(
        video_path,
        prompt=args.prompt,
        task_type=args.task_type,
        lang=args.lang,
        is_short_video=not args.long_video,
        result=result,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(saved_path.read_text(encoding="utf-8"), encoding="utf-8")
        saved_path = args.output

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved to: {saved_path}")

    if result.get("code") != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
