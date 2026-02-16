"""
ASR engine: uses Hugging Face pipeline for tarteel-ai/whisper-base-ar-quran.
Matches Tarteel's official usage - pass file path directly to pipe(), no preprocessing.
Uses repetition_penalty and no_repeat_ngram_size to suppress token repetition.
"""

import os
import tempfile

import numpy as np
import soundfile as sf
import torch
from transformers import pipeline

from config import DEFAULT_ASR_MODEL

# Single pipeline instance (same as Tarteel demo)
_pipe = None
_pipe_model_id = None


def get_device():
    """Return best available device: mps (Mac), cuda (NVIDIA), or cpu."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _get_pipe(model_id: str):
    """Lazy load ASR pipeline (official Tarteel usage)."""
    global _pipe, _pipe_model_id
    if _pipe is not None and _pipe_model_id == model_id:
        return _pipe
    # MPS fallback for compatibility on Mac
    if get_device() == "mps":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    # Optional HF token for gated models (tarteel is public, not gated)
    token = os.environ.get("HF_TARTEEL_TOKEN") or os.environ.get("HF_TOKEN")
    _pipe = pipeline(
        "automatic-speech-recognition",
        model=model_id,
        token=token if token else None,
        device=get_device(),
    )
    _pipe_model_id = model_id
    return _pipe


def transcribe(audio_path, model_id=None, return_timestamps=False):
    """
    Transcribe audio using the ASR pipeline (Tarteel exact usage).
    Pass file path directly to pipe() - no preprocessing.
    Uses repetition_penalty and no_repeat_ngram_size to suppress hallucinations.
    Returns {"text": str, "chunks": []}.
    """
    if model_id is None:
        model_id = DEFAULT_ASR_MODEL
    pipe = _get_pipe(model_id)

    # Guard: if Gradio passes tuple (sample_rate, array), save to temp file
    path_to_use = audio_path
    tmp_created = False
    if isinstance(audio_path, (tuple, list)) and len(audio_path) == 2:
        sample_rate, data = audio_path
        if isinstance(data, np.ndarray) and isinstance(sample_rate, (int, float)):
            fd, path_to_use = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            sf.write(path_to_use, data, int(sample_rate))
            tmp_created = True

    try:
        out = pipe(
            path_to_use,
            return_timestamps=False,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
        )
        text = (out.get("text") or "").strip()
        return {"text": text, "chunks": []}
    finally:
        if tmp_created and path_to_use and os.path.isfile(path_to_use):
            try:
                os.unlink(path_to_use)
            except OSError:
                pass
