"""Unit tests for audio pipeline: load WAV → resample → denoise → VAD → slice."""
import pytest
import numpy as np
from pathlib import Path

pytest.importorskip("scipy")

from app.services.audio_pipeline import run_pipeline, _load_wav, _resample_if_needed

# Skip run_pipeline tests when faster_whisper.vad is not available
vad_available = False
try:
    from faster_whisper.vad import get_speech_timestamps, collect_chunks, VadOptions
    vad_available = True
except ImportError:
    pass


def _write_wav(path: Path, rate: int, data: np.ndarray, dtype=np.int16) -> None:
    """Write WAV file; data will be scaled to dtype if float."""
    from scipy.io import wavfile
    if data.dtype == np.float32 or data.dtype == np.float64:
        data = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
    wavfile.write(str(path), rate, data)


def test_load_wav_returns_float32_mono(tmp_path):
    """_load_wav returns float32 mono and correct sample rate."""
    rate = 16000
    duration = 0.5
    n = int(rate * duration)
    data = (np.random.randn(n) * 10000).astype(np.int16)
    wav_path = tmp_path / "test.wav"
    _write_wav(wav_path, rate, data)
    loaded, sr = _load_wav(str(wav_path))
    assert loaded.dtype == np.float32
    assert loaded.ndim == 1
    assert len(loaded) == n
    assert sr == rate


def test_resample_if_needed_same_rate_unchanged():
    """_resample_if_needed with same rate returns unchanged array."""
    audio = np.random.randn(16000).astype(np.float32) * 0.1
    out = _resample_if_needed(audio, 16000, 16000)
    np.testing.assert_array_almost_equal(out, audio)


def test_resample_if_needed_changes_length():
    """_resample_if_needed with different rate changes length."""
    audio = np.random.randn(8000).astype(np.float32) * 0.1
    out = _resample_if_needed(audio, 8000, 16000)
    assert out.dtype == np.float32
    assert len(out) == 16000


@pytest.mark.skipif(not vad_available, reason="faster_whisper.vad not installed")
def test_run_pipeline_silence_returns_empty(tmp_path):
    """Full silence WAV returns empty chunks and no error."""
    rate = 16000
    data = np.zeros(rate * 2, dtype=np.int16)  # 2 seconds silence
    wav_path = tmp_path / "silence.wav"
    _write_wav(wav_path, rate, data)
    chunks, meta = run_pipeline(str(wav_path))
    assert chunks == []
    assert meta == []


def test_run_pipeline_nonexistent_raises():
    """run_pipeline on nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        run_pipeline("/nonexistent/path.wav")


@pytest.mark.skipif(not vad_available, reason="faster_whisper.vad not installed")
def test_run_pipeline_empty_wav_returns_empty(tmp_path):
    """Very short / empty WAV returns empty chunks."""
    rate = 16000
    data = np.zeros(100, dtype=np.int16)
    wav_path = tmp_path / "tiny.wav"
    _write_wav(wav_path, rate, data)
    chunks, meta = run_pipeline(str(wav_path))
    assert chunks == []
    assert meta == []


@pytest.mark.skipif(not vad_available, reason="faster_whisper.vad not installed")
def test_run_pipeline_with_speech_like_signal(tmp_path):
    """WAV with speech-like signal yields chunks and metadata with matching length and keys."""
    rate = 16000
    duration = 2.0
    n = int(rate * duration)
    # Simple tone + noise can sometimes be detected as speech by VAD
    t = np.arange(n) / rate
    data = (np.sin(2 * np.pi * 440 * t) * 8000 + np.random.randn(n) * 500).astype(np.int16)
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path, rate, data)
    chunks, meta = run_pipeline(str(wav_path))
    # Either no speech (empty) or some segments
    assert len(chunks) == len(meta)
    for m in meta:
        assert "offset" in m
        assert "duration" in m
    if chunks:
        total_duration = sum(m.get("duration", 0) for m in meta)
        assert total_duration <= duration + 1.0  # allow small padding
        for c in chunks:
            assert isinstance(c, np.ndarray)
            assert c.dtype == np.float32
