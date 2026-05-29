#!/usr/bin/env bash
# Run on a Linux machine with NVIDIA GPU (>= 40GB VRAM recommended).
# Example: A100 40GB, H20 96GB, RTX 4090 24GB (may OOM on long videos).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${ROOT}/vendor/ARC-Hunyuan-Video-7B"
PYTHON="${PYTHON:-python3.11}"
CUDA="${CUDA:-124}"  # 118 | 124 | 126

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "Error: nvidia-smi not found. This script requires an NVIDIA GPU Linux host."
  exit 1
fi

if [[ ! -d "${REPO}" ]]; then
  git clone --depth 1 https://github.com/TencentARC/ARC-Hunyuan-Video-7B.git "${REPO}"
fi

cd "${REPO}"

"${PYTHON}" -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel

case "${CUDA}" in
  118) TORCH_INDEX="https://download.pytorch.org/whl/cu118" ;;
  124) TORCH_INDEX="https://download.pytorch.org/whl/cu124" ;;
  126) TORCH_INDEX="https://download.pytorch.org/whl/cu126" ;;
  *) echo "Unsupported CUDA=${CUDA}"; exit 1 ;;
esac

pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url "${TORCH_INDEX}"
pip install -r requirements.txt
pip install "git+https://github.com/liyz15/transformers.git@arc_hunyuan_video"

PY_TAG="$("${PYTHON}" -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')"
pip install "https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1+cu12torch2.6cxx11abiFALSE-${PY_TAG}-${PY_TAG}-linux_x86_64.whl" || {
  echo "flash-attn wheel install failed; edit video_inference.py to use attn_implementation=\"sdpa\""
}

echo
echo "Download model weights (~17GB):"
echo "  huggingface-cli download TencentARC/ARC-Hunyuan-Video-7B --local-dir ./models/ARC-Hunyuan-Video-7B"
echo "  huggingface-cli download openai/whisper-large-v3 --local-dir ./models/whisper-large-v3"
echo
echo "Quick test:"
echo "  cd ${REPO} && source .venv/bin/activate && python3 video_inference.py"
