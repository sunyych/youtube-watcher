"""Config from environment for transcribe_runner (no dependency on backend)."""
import os


def get_int(key: str, default: int) -> int:
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def get_float(key: str, default: float) -> float:
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def get_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return default


# Same defaults as backend/app/config.py for pipeline compatibility
AUDIO_TARGET_SAMPLE_RATE = get_int("AUDIO_TARGET_SAMPLE_RATE", 16000)
AUDIO_ENABLE_DENOISE = get_bool("AUDIO_ENABLE_DENOISE", False)
VAD_THRESHOLD = get_float("VAD_THRESHOLD", 0.5)
VAD_MIN_SILENCE_DURATION_MS = get_int("VAD_MIN_SILENCE_DURATION_MS", 2000)
VAD_SPEECH_PAD_MS = get_int("VAD_SPEECH_PAD_MS", 400)
VAD_MAX_SPEECH_DURATION_S = get_float("VAD_MAX_SPEECH_DURATION_S", 30.0)
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "medium")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
PORT = get_int("PORT", 8765)
# Max concurrent transcription jobs (e.g. one per GPU). Default 3.
MAX_CONCURRENT_JOBS = max(1, get_int("MAX_CONCURRENT_JOBS", 3))
# Number of GPUs to use (device ids 0..NUM_GPUS-1). Default same as MAX_CONCURRENT_JOBS.
NUM_GPUS = max(1, get_int("NUM_GPUS", MAX_CONCURRENT_JOBS))
