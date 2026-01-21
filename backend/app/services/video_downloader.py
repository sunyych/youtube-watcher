"""Video download service using yt-dlp"""
import yt_dlp
import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Download YouTube videos using yt-dlp"""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def download(self, url: str, progress_callback=None) -> Dict[str, Any]:
        """
        Download video from URL
        
        Args:
            url: YouTube video URL
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dict with video info including file path
        """
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(self.storage_dir / '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            # Add options to bypass YouTube restrictions
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                    'player_skip': ['webpage'],
                }
            },
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'cookiefile': None,  # Can be set to a cookies file path if needed
            # Retry options
            'retries': 10,
            'fragment_retries': 10,
            'ignoreerrors': False,
            # Additional headers
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
        }
        
        if progress_callback:
            def hook(d):
                if d['status'] == 'downloading':
                    if 'total_bytes' in d:
                        percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                        progress_callback(percent)
                    elif 'total_bytes_estimate' in d:
                        percent = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
                        progress_callback(percent)
            
            ydl_opts['progress_hooks'] = [hook]
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # Find the downloaded file
                video_id = info.get('id', '')
                ext = info.get('ext', 'mp4')
                video_file = self.storage_dir / f"{video_id}.{ext}"
                
                if not video_file.exists():
                    # Try to find any file with the video ID
                    for file in self.storage_dir.glob(f"{video_id}.*"):
                        video_file = file
                        break
                
                return {
                    'id': video_id,
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'file_path': str(video_file),
                    'thumbnail': info.get('thumbnail'),
                    'description': info.get('description', ''),
                }
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            raise Exception(f"Failed to download video: {str(e)}")
