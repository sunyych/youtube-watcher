"""Audio conversion service using ffmpeg"""
import subprocess
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AudioConverter:
    """Convert video to audio using ffmpeg"""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def convert_to_audio(self, video_path: str, output_format: str = "wav") -> str:
        """
        Convert video file to audio
        
        Args:
            video_path: Path to video file
            output_format: Output audio format (wav, mp3, etc.)
            
        Returns:
            Path to converted audio file
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Generate output path
        audio_path = self.storage_dir / f"{video_path.stem}.{output_format}"
        
        try:
            # Use ffmpeg to convert video to audio
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-vn',  # No video
                '-acodec', 'pcm_s16le' if output_format == 'wav' else 'libmp3lame',
                '-ar', '16000',  # 16kHz sample rate (Whisper standard)
                '-ac', '1',  # Mono
                '-y',  # Overwrite output file
                str(audio_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            if not audio_path.exists():
                raise Exception("Audio conversion failed: output file not created")
            
            return str(audio_path)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise Exception(f"Audio conversion failed: {e.stderr}")
        except Exception as e:
            logger.error(f"Error converting audio: {e}")
            raise
