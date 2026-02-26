"""Whisper transcription for transcribe_runner. Standalone, uses config from env."""
import logging
from typing import Optional, List, Dict, Any

import numpy as np

from config import WHISPER_MODEL_SIZE, WHISPER_DEVICE

logger = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    WhisperModel = None


def _detect_compute_type(device: str) -> str:
    if device == "cuda":
        return "float16"
    return "int8"


class WhisperService:
    def __init__(
        self,
        model_size: str = "medium",
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ):
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError("faster-whisper is not installed.")
        self.model_size = model_size
        device = device or WHISPER_DEVICE
        compute_type = compute_type or _detect_compute_type(device)
        logger.info("Initializing Whisper model: %s on %s with %s", model_size, device, compute_type)
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:
            logger.warning("CUDA init failed (%s), falling back to CPU", e)
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe_segments(
        self,
        audio_chunks: List[np.ndarray],
        chunk_metadata: List[Dict[str, Any]],
        language: Optional[str] = None,
        task: str = "transcribe",
        beam_size: int = 5,
        best_of: int = 5,
        temperature: float = 0.0,
        progress_callback=None,
        sample_rate: int = 16000,
    ) -> Dict[str, Any]:
        """Same contract as backend WhisperService.transcribe_segments."""
        if not audio_chunks or not chunk_metadata:
            return {
                "text": "",
                "language": language or "unknown",
                "language_probability": 0.0,
                "segments": [],
            }
        if len(audio_chunks) != len(chunk_metadata):
            raise ValueError("audio_chunks and chunk_metadata must have same length")

        full_text_parts = []
        all_segments = []
        detected_language = language
        language_probability = 0.0

        for idx, (chunk_audio, meta) in enumerate(zip(audio_chunks, chunk_metadata)):
            offset_sec = float(meta.get("offset", 0))
            segments_iter, info = self.model.transcribe(
                chunk_audio,
                language=language,
                task=task,
                beam_size=beam_size,
                best_of=best_of,
                temperature=temperature,
                vad_filter=False,
            )
            if idx == 0:
                detected_language = info.language
                language_probability = getattr(info, "language_probability", 0.0) or 0.0
            for segment in segments_iter:
                seg_text = segment.text.strip()
                if seg_text:
                    global_start = offset_sec + segment.start
                    global_end = offset_sec + segment.end
                    full_text_parts.append(seg_text)
                    all_segments.append({"start": global_start, "end": global_end, "text": seg_text})
                    if progress_callback:
                        progress_callback(global_end)

        full_text = " ".join(full_text_parts).strip()
        return {
            "text": full_text,
            "language": detected_language or language or "unknown",
            "language_probability": language_probability,
            "segments": all_segments,
        }
