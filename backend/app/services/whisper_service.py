"""Whisper transcription service using faster-whisper"""
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    WhisperModel = None

from typing import Optional, List, Dict, Any
import logging
import os
import platform

logger = logging.getLogger(__name__)


class WhisperService:
    """Whisper transcription service"""
    
    def __init__(self, model_size: str = "medium", device: Optional[str] = None, compute_type: Optional[str] = None):
        """
        Initialize Whisper model
        
        Args:
            model_size: Model size (tiny, base, small, medium, large-v2, large-v3)
            device: Device to use (cuda, cpu, auto)
            compute_type: Compute type (int8, int8_float16, int16, float16, float32)
        """
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError("faster-whisper is not installed. Please install it to use transcription.")
        
        self.model_size = model_size
        
        # Auto-detect device and compute type if not specified
        if device is None:
            device = self._detect_device()
        
        if compute_type is None:
            compute_type = self._detect_compute_type(device)
        
        logger.info(f"Initializing Whisper model: {model_size} on {device} with {compute_type}")
        
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
            self.device = device
            self.compute_type = compute_type
        except Exception as e:
            logger.error(f"Failed to initialize Whisper model: {e}")
            # Fallback to CPU
            logger.info("Falling back to CPU")
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            self.device = "cpu"
            self.compute_type = "int8"
    
    def _detect_device(self) -> str:
        """Detect available device"""
        # Check for CUDA
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        
        # Check for MLX (Apple Silicon)
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            try:
                import mlx.core as mx
                return "cpu"  # MLX uses CPU device in faster-whisper
            except ImportError:
                pass
        
        return "cpu"
    
    def _detect_compute_type(self, device: str) -> str:
        """Detect appropriate compute type"""
        if device == "cuda":
            return "float16"  # Use float16 for CUDA
        elif device == "cpu":
            return "int8"  # Use int8 for CPU (faster)
        else:
            return "int8"
    
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
        beam_size: int = 5,
        best_of: int = 5,
        temperature: float = 0.0,
        vad_filter: bool = True,
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Transcribe audio file
        
        Args:
            audio_path: Path to audio file
            language: Language code (e.g., 'zh', 'en'). If None, auto-detect
            task: Task type ('transcribe' or 'translate')
            beam_size: Beam size for beam search
            best_of: Number of candidates
            temperature: Temperature for sampling
            vad_filter: Enable VAD filter
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dict with transcription results
        """
        try:
            # Transcribe with progress callback
            segments, info = self.model.transcribe(
                audio_path,
                language=language,
                task=task,
                beam_size=beam_size,
                best_of=best_of,
                temperature=temperature,
                vad_filter=vad_filter,
            )
            
            detected_language = info.language
            language_probability = info.language_probability
            
            # Collect segments
            full_text = ""
            segments_list = []
            
            for segment in segments:
                segment_text = segment.text.strip()
                if segment_text:
                    full_text += segment_text + " "
                    segments_list.append({
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment_text,
                    })
                    
                    # Call progress callback if provided
                    if progress_callback:
                        # Estimate progress based on segment end time
                        # This is approximate since we don't know total duration
                        progress_callback(segment.end)
            
            full_text = full_text.strip()
            
            return {
                'text': full_text,
                'language': detected_language,
                'language_probability': language_probability,
                'segments': segments_list,
            }
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise Exception(f"Transcription failed: {str(e)}")
