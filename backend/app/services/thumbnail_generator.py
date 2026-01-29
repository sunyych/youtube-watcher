"""Thumbnail generation service"""
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """Generate thumbnails from video files"""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # Create thumbnails subdirectory
        self.thumbnails_dir = self.storage_dir / 'thumbnails'
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_thumbnail(self, video_path: str, video_id: str, time_offset: float = 5.0) -> Optional[str]:
        """
        Generate thumbnail from video file using ffmpeg
        
        Args:
            video_path: Path to video file
            video_id: Video ID for naming the thumbnail
            time_offset: Time offset in seconds to extract frame (default: 5 seconds)
            
        Returns:
            Path to generated thumbnail file, or None if failed
        """
        try:
            video_file = Path(video_path)
            if not video_file.exists():
                logger.error(f"Video file not found: {video_path}")
                return None
            
            # Output thumbnail path
            thumbnail_path = self.thumbnails_dir / f"{video_id}.jpg"
            
            # Use ffmpeg to extract frame at specified time
            # -ss: seek to time offset
            # -i: input file
            # -vframes 1: extract 1 frame
            # -q:v 2: high quality (scale 2-31, lower is better)
            # -vf scale: resize to 320x180 (16:9 aspect ratio)
            cmd = [
                'ffmpeg',
                '-ss', str(time_offset),
                '-i', str(video_file),
                '-vframes', '1',
                '-q:v', '2',
                '-vf', 'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2',
                '-y',  # Overwrite output file
                str(thumbnail_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and thumbnail_path.exists():
                logger.info(f"Generated thumbnail: {thumbnail_path}")
                return str(thumbnail_path)
            else:
                logger.error(f"Failed to generate thumbnail: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout generating thumbnail for {video_path}")
            return None
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}", exc_info=True)
            return None
