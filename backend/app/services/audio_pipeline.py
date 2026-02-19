"""Audio pipeline: load WAV → resample → optional denoise → VAD → slice (chunks)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple, Any, Dict

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Optional resampling
try:
    from scipy.io import wavfile
    from scipy.signal import resample
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Optional denoise
try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    NOISEREDUCE_AVAILABLE = False

# VAD from faster-whisper
try:
    from faster_whisper.vad import get_speech_timestamps, collect_chunks, VadOptions
    VAD_AVAILABLE = True
except ImportError:
    get_speech_timestamps = None
    collect_chunks = None
    VadOptions = None
    VAD_AVAILABLE = False


def _load_wav(path: str) -> Tuple[np.ndarray, int]:
    """Load WAV as float32 mono and return (samples, sample_rate)."""
    if not SCIPY_AVAILABLE:
        raise RuntimeError("scipy is required for audio pipeline (pip install scipy)")
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
    """Resample to target_sr if different."""
    if orig_sr == target_sr:
        return audio
    if not SCIPY_AVAILABLE:
        return audio
    num_samples = int(len(audio) * target_sr / orig_sr)
    return resample(audio, num_samples).astype(np.float32)


def _denoise(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Apply noisereduce if enabled."""
    if not getattr(settings, "audio_enable_denoise", False):
        return audio
    backend = getattr(settings, "audio_denoise_backend", "noisereduce")
    if backend != "noisereduce" or not NOISEREDUCE_AVAILABLE:
        return audio
    try:
        return nr.reduce_noise(y=audio, sr=sample_rate, prop_decrease=1.0)
    except Exception as e:
        logger.warning("Denoising failed, using original audio: %s", e)
        return audio


def _build_vad_options() -> VadOptions:
    """Build VadOptions from settings."""
    if VadOptions is None:
        raise RuntimeError("faster_whisper.vad is not available")
    return VadOptions(
        threshold=getattr(settings, "vad_threshold", 0.5),
        min_silence_duration_ms=getattr(settings, "vad_min_silence_duration_ms", 2000),
        speech_pad_ms=getattr(settings, "vad_speech_pad_ms", 400),
        max_speech_duration_s=getattr(settings, "vad_max_speech_duration_s", 30.0),
    )


def run_pipeline(audio_path: str) -> Tuple[List[np.ndarray], List[Dict[str, Any]]]:
    """
    Run full pipeline: load WAV → resample → optional denoise → VAD → slice.

    Returns:
        (audio_chunks, chunk_metadata_list)
        - audio_chunks: list of float32 mono numpy arrays (each chunk)
        - chunk_metadata_list: list of dicts with "offset" (sec), "duration" (sec), "segments"
    If no speech is detected, returns ([], []).
    """
    target_sr = getattr(settings, "audio_target_sample_rate", 16000)

    if not SCIPY_AVAILABLE:
        raise RuntimeError("scipy is required for audio pipeline")

    # 1. Load WAV
    audio, orig_sr = _load_wav(audio_path)
    if len(audio) == 0:
        logger.warning("Empty audio file: %s", audio_path)
        return [], []

    # 2. Resample to target_sr
    audio = _resample_if_needed(audio, orig_sr, target_sr)

    # 3. Optional denoise
    audio = _denoise(audio, target_sr)

    # 4. VAD
    if not VAD_AVAILABLE or get_speech_timestamps is None or collect_chunks is None:
        raise RuntimeError("faster_whisper.vad is required (get_speech_timestamps, collect_chunks)")

    vad_options = _build_vad_options()
    speeches = get_speech_timestamps(audio, vad_options, sampling_rate=target_sr)

    if not speeches:
        logger.info("No speech segments detected in %s", audio_path)
        return [], []

    # 5. Slice (collect chunks with max_duration)
    max_duration = getattr(settings, "vad_max_speech_duration_s", 30.0)
    audio_chunks, chunks_metadata = collect_chunks(audio, speeches, sampling_rate=target_sr, max_duration=max_duration)

    # Filter out empty chunks
    non_empty = []
    non_empty_meta = []
    for ch, meta in zip(audio_chunks, chunks_metadata):
        if ch is not None and len(ch) > 0:
            non_empty.append(ch)
            non_empty_meta.append(meta)

    return non_empty, non_empty_meta
