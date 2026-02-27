"""Whisper transcription for transcribe_runner. Standalone, uses config from env."""
import logging
import os
import subprocess
import traceback
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


def _log_cuda_diagnostics(exc: BaseException, device: str) -> None:
    """Log detailed CUDA/GPU info to help debug init failures (e.g. unsupported device cuda:0)."""
    lines = [
        "CUDA init failed — diagnostic info:",
        "  exception: %s" % type(exc).__name__,
        "  message: %s" % (exc,),
    ]
    # Environment
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cuda_visible is None:
        lines.append("  CUDA_VISIBLE_DEVICES: (not set)")
    else:
        lines.append("  CUDA_VISIBLE_DEVICES=%r" % cuda_visible)
    lines.append("  requested device: %s" % device)
    # CTranslate2 GPU count (faster_whisper backend)
    try:
        import ctranslate2
        count = getattr(ctranslate2, "get_cuda_device_count", None)
        if callable(count):
            lines.append("  ctranslate2.get_cuda_device_count(): %s" % count())
        else:
            lines.append("  ctranslate2.get_cuda_device_count: (not available)")
    except Exception as e:
        lines.append("  ctranslate2 check: %s" % e)
    # nvidia-smi if available (driver + GPU list)
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            lines.append("  nvidia-smi (this process):")
            for line in out.stdout.strip().splitlines():
                lines.append("    %s" % line.strip())
        elif out.returncode != 0:
            lines.append("  nvidia-smi: exit code %s, stderr=%r" % (out.returncode, (out.stderr or "").strip()[:200]))
        else:
            lines.append("  nvidia-smi: no GPUs listed")
    except FileNotFoundError:
        lines.append("  nvidia-smi: not found (container may not have GPU access or nvidia CLI)")
    except Exception as e:
        lines.append("  nvidia-smi: %s" % e)
    # Docker hint
    if os.path.exists("/.dockerenv"):
        lines.append("  running inside Docker — ensure run with --gpus all or deploy.resources.reservations.devices (nvidia)")
    # Full traceback at DEBUG
    logger.warning("\n".join(lines))
    logger.debug("CUDA init traceback:\n%s", traceback.format_exc())


def _detect_compute_type(device: str) -> str:
    if device == "cuda" or (isinstance(device, str) and device.startswith("cuda:")):
        return "float16"
    return "int8"


def _parse_device(device: str) -> tuple[str, Optional[int]]:
    """Convert device string to (device, device_index). WhisperModel expects device in {'cuda','cpu'} and optional device_index for CUDA."""
    if not device or device == "cpu":
        return ("cpu", None)
    if device == "cuda":
        return ("cuda", 0)
    if isinstance(device, str) and device.startswith("cuda:"):
        try:
            idx = int(device.split(":", 1)[1])
            return ("cuda", idx)
        except ValueError:
            return ("cuda", 0)
    return ("cpu", None)


def _normalize_language(lang: Optional[str]) -> Optional[str]:
    """Faster-whisper 只接受合法语言码，不接受 'unknown'。未指定或 unknown 时传 None 自动检测，默认支持中英文等."""
    if lang is None or (isinstance(lang, str) and lang.strip().lower() in ("", "unknown")):
        return None
    return lang.strip() if isinstance(lang, str) else lang


def _device_string(device_id: Optional[int] = None) -> str:
    """Return device string: cuda:0, cuda:1, ... or WHISPER_DEVICE if device_id is None."""
    if device_id is not None:
        return f"cuda:{device_id}"
    return WHISPER_DEVICE


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
        device_for_api, device_index = _parse_device(device)
        logger.info(
            "Initializing Whisper model: %s on %s with %s (device_index=%s)",
            model_size,
            device,
            compute_type,
            device_index,
        )
        self._device = device
        try:
            if device_for_api == "cuda":
                self.model = WhisperModel(
                    model_size,
                    device="cuda",
                    device_index=device_index,
                    compute_type=compute_type,
                )
            else:
                self.model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        except Exception as e:
            # 不再自动降级到 CPU，直接记录详细信息并抛出，让调用方看到真实错误
            _log_cuda_diagnostics(e, device)
            logger.error(
                "Whisper model init failed on device=%s (model_size=%s, compute_type=%s): %s",
                device,
                model_size,
                compute_type,
                e,
            )
            raise
        # 标记设备健康状态，供上层调度逻辑参考
        self._unhealthy = False

    @property
    def is_healthy(self) -> bool:
        """Return True if this WhisperService is considered healthy."""
        return not getattr(self, "_unhealthy", False)

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

        # faster_whisper 不接受 "unknown"，未指定或 unknown 时按英文处理
        language_for_api = _normalize_language(language)
        full_text_parts = []
        all_segments = []
        detected_language = language
        language_probability = 0.0

        for idx, (chunk_audio, meta) in enumerate(zip(audio_chunks, chunk_metadata)):
            offset_sec = float(meta.get("offset", 0))
            try:
                segments_iter, info = self.model.transcribe(
                    chunk_audio,
                    language=language_for_api,
                    task=task,
                    beam_size=beam_size,
                    best_of=best_of,
                    temperature=temperature,
                    vad_filter=False,
                )
            except RuntimeError as e:
                msg = str(e)
                is_cuda_device = self._device == "cuda" or (
                    isinstance(self._device, str) and self._device.startswith("cuda:")
                )
                logger.error(
                    "CUDA runtime error during transcribe (device=%s, is_cuda=%s, model_size=%s, "
                    "language=%r, chunk_index=%d, offset_sec=%.3f): %s",
                    self._device,
                    is_cuda_device,
                    self.model_size,
                    language_for_api,
                    idx,
                    offset_sec,
                    msg,
                )
                logger.debug("CUDA runtime traceback:\n%s", traceback.format_exc())
                # 在特定 CUDA 错误上标记设备为不健康，供上层停止向该 GPU 分配新任务
                if is_cuda_device and "invalid argument" in msg.lower():
                    logger.warning(
                        "Marking device %s as unhealthy due to CUDA invalid argument (chunk_index=%d, offset_sec=%.3f)",
                        self._device,
                        idx,
                        offset_sec,
                    )
                    self._unhealthy = True
                # 不做 CPU 降级，直接抛出，让上层感知 GPU 相关问题
                raise
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
