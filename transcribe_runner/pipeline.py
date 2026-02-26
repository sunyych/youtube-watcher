"""Audio pipeline: load WAV -> resample -> optional denoise -> VAD -> slice. Standalone for runner."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple, Any, Dict

import numpy as np

from config import (
    AUDIO_TARGET_SAMPLE_RATE,
    AUDIO_ENABLE_DENOISE,
    VAD_THRESHOLD,
    VAD_MIN_SILENCE_DURATION_MS,
    VAD_SPEECH_PAD_MS,
    VAD_MAX_SPEECH_DURATION_S,
)

logger = logging.getLogger(__name__)

try:
    from scipy.io import wavfile
    from scipy.signal import resample
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    NOISEREDUCE_AVAILABLE = False

try:
    from faster_whisper.vad import get_speech_timestamps, collect_chunks, VadOptions
    VAD_AVAILABLE = True
except ImportError:
    get_speech_timestamps = None
    collect_chunks = None
    VadOptions = None
    VAD_AVAILABLE = False


def _load_wav(path: str) -> Tuple[np.ndarray, int]:
    if not SCIPY_AVAILABLE:
        raise RuntimeError("scipy is required for audio pipeline")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")
    rate, data = wavfile.read(str(path))
    if data.ndim == 2:
        data = data.mean(axis=1)
    if data.dtype != np.float32:
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        else:
            data = data.astype(np.float32) / (np.iinfo(data.dtype).max + 1)
    return data, rate


def _resample_if_needed(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return audio
    if not SCIPY_AVAILABLE:
        return audio
    num_samples = int(len(audio) * target_sr / orig_sr)
    return resample(audio, num_samples).astype(np.float32)


def _denoise(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    if not AUDIO_ENABLE_DENOISE or not NOISEREDUCE_AVAILABLE:
        return audio
    try:
        return nr.reduce_noise(y=audio, sr=sample_rate, prop_decrease=1.0)
    except Exception as e:
        logger.warning("Denoising failed, using original audio: %s", e)
        return audio


def run_pipeline(audio_path: str) -> Tuple[List[np.ndarray], List[Dict[str, Any]]]:
    """
    Run full pipeline: load WAV -> resample -> optional denoise -> VAD -> slice.
    Returns (audio_chunks, chunk_metadata_list). Same contract as backend audio_pipeline.
    """
    target_sr = AUDIO_TARGET_SAMPLE_RATE
    if not SCIPY_AVAILABLE:
        raise RuntimeError("scipy is required for audio pipeline")

    audio, orig_sr = _load_wav(audio_path)
    if len(audio) == 0:
        logger.warning("Empty audio file: %s", audio_path)
        return [], []

    audio = _resample_if_needed(audio, orig_sr, target_sr)
    audio = _denoise(audio, target_sr)

    if not VAD_AVAILABLE or get_speech_timestamps is None or collect_chunks is None:
        raise RuntimeError("faster_whisper.vad is required")

    vad_options = VadOptions(
        threshold=VAD_THRESHOLD,
        min_silence_duration_ms=VAD_MIN_SILENCE_DURATION_MS,
        speech_pad_ms=VAD_SPEECH_PAD_MS,
        max_speech_duration_s=VAD_MAX_SPEECH_DURATION_S,
    )
    speeches = get_speech_timestamps(audio, vad_options, sampling_rate=target_sr)
    if not speeches:
        logger.info("No speech segments detected in %s", audio_path)
        return [], []

    audio_chunks, chunks_metadata = collect_chunks(
        audio, speeches, sampling_rate=target_sr, max_duration=VAD_MAX_SPEECH_DURATION_S
    )
    non_empty = []
    non_empty_meta = []
    for ch, meta in zip(audio_chunks, chunks_metadata):
        if ch is not None and len(ch) > 0:
            non_empty.append(ch)
            non_empty_meta.append(meta)
    return non_empty, non_empty_meta
