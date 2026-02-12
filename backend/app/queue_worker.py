"""Independent queue worker service"""
import asyncio
import logging
import sys
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, SessionLocal
from app.models.database import VideoRecord, VideoStatus, PlaylistItem, User
from app.config import settings
from app.services.video_downloader import VideoDownloader, VideoDownloadError
from app.services.audio_converter import AudioConverter
from app.services.audio_pipeline import run_pipeline
from app.services.whisper_service import WhisperService
from app.services.llm_service import LLMService
from app.services.thumbnail_generator import ThumbnailGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pipeline concurrency
# - Downloads are mostly network/disk bound, but we intentionally keep it low to avoid bans.
# - Transcription/summarization are CPU/GPU bound: keep low concurrency.
DOWNLOAD_CONCURRENCY = max(1, int(os.getenv("QUEUE_DOWNLOAD_CONCURRENCY", "1")))
PROCESS_CONCURRENCY = max(1, int(os.getenv("QUEUE_PROCESS_CONCURRENCY", "1")))
DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=DOWNLOAD_CONCURRENCY)

# Download pause state (shared across tasks in this worker process)
_download_pause_lock = asyncio.Lock()
_downloads_paused_until: Optional[datetime] = None
_blocked_download_failures: int = 0
_last_pause_log_at: Optional[datetime] = None

# Download pacing (global, shared across tasks)
_download_rate_lock = asyncio.Lock()
_last_download_started_at: Optional[datetime] = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _wait_for_download_spacing():
    """
    Ensure a minimum delay between download starts.
    This is a global rate limiter to avoid triggering YouTube anti-bot measures.
    """
    global _last_download_started_at

    # Default to 0 so unit tests and local runs don't sleep unexpectedly.
    # docker-compose/.env can (and should) set this to something like 60 to reduce bot-check risk.
    min_interval_s = max(0, int(os.getenv("QUEUE_DOWNLOAD_MIN_INTERVAL_SECONDS", "0")))
    if min_interval_s <= 0:
        return

    async with _download_rate_lock:
        now = _now_utc()
        if _last_download_started_at is None:
            _last_download_started_at = now
            return

        elapsed = (now - _last_download_started_at).total_seconds()
        remaining = min_interval_s - elapsed
        if remaining > 0:
            logger.info(f"[download] Rate limit: waiting {remaining:.0f}s before starting next download")
            await asyncio.sleep(remaining)

        _last_download_started_at = _now_utc()


async def _get_download_pause_remaining_seconds() -> int:
    """Returns remaining pause seconds; also clears expired pause."""
    global _downloads_paused_until, _blocked_download_failures
    async with _download_pause_lock:
        if _downloads_paused_until is None:
            return 0

        now = _now_utc()
        if now >= _downloads_paused_until:
            _downloads_paused_until = None
            # Reset counter when pause expires so we don't immediately pause again.
            _blocked_download_failures = 0
            return 0

        return max(0, int((_downloads_paused_until - now).total_seconds()))


async def _wait_if_downloads_paused():
    """Block until downloads are unpaused."""
    while True:
        remaining = await _get_download_pause_remaining_seconds()
        if remaining <= 0:
            return
        # Sleep in small intervals so we can resume promptly.
        await asyncio.sleep(min(5, remaining))


async def _register_blocked_download_failure(error_message: str):
    """Increment blocked counter; pause downloads when threshold reached."""
    global _downloads_paused_until, _blocked_download_failures, _last_pause_log_at

    threshold = max(1, int(getattr(settings, "queue_blocked_threshold", 3)))
    pause_seconds = int(getattr(settings, "queue_blocked_pause_seconds", 3600))

    async with _download_pause_lock:
        _blocked_download_failures += 1
        count = _blocked_download_failures

        if _downloads_paused_until is not None:
            return

        if count < threshold:
            logger.warning(f"[download] Blocked by YouTube ({count}/{threshold}): {error_message}")
            return

        now = _now_utc()
        if pause_seconds <= 0:
            # Effectively "forever" (until restart)
            _downloads_paused_until = now + timedelta(days=365 * 100)
        else:
            _downloads_paused_until = now + timedelta(seconds=pause_seconds)

        _last_pause_log_at = now
        logger.error(
            f"[download] Pausing ALL downloads due to blocked errors (count={count}, threshold={threshold}). "
            f"Paused until: {_downloads_paused_until.isoformat()}. Latest error: {error_message}"
        )


async def _reset_blocked_download_counter_on_success():
    global _blocked_download_failures
    async with _download_pause_lock:
        _blocked_download_failures = 0


# Base timeout for stuck tasks (30 minutes)
# For transcription tasks, we'll use a longer timeout based on audio duration
BASE_STUCK_TASK_TIMEOUT = timedelta(minutes=30)
# Minimum timeout for transcription (2 hours)
MIN_TRANSCRIPTION_TIMEOUT = timedelta(hours=2)
# Maximum timeout for very long videos (24 hours)
MAX_TRANSCRIPTION_TIMEOUT = timedelta(hours=24)
# Transcription speed factor: medium model on CPU is ~0.1-0.3x realtime
# We use a conservative estimate: 10x audio duration + 1 hour buffer
TRANSCRIPTION_SPEED_FACTOR = 10
TRANSCRIPTION_BUFFER_TIME = timedelta(hours=1)


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats"""
    if not url:
        return None
    
    # Patterns for different YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # Fallback: try to extract from URL path
    # For youtu.be/VIDEO_ID format
    if 'youtu.be/' in url:
        parts = url.split('youtu.be/')
        if len(parts) > 1:
            video_id = parts[1].split('?')[0].split('&')[0]
            if len(video_id) == 11:
                return video_id
    
    logger.warning(f"Could not extract video ID from URL: {url}")
    return None


def find_existing_video_file(storage_dir: str, url: str) -> Optional[Path]:
    """Check if a video file already exists on disk for this URL."""
    video_id = extract_video_id(url)
    if not video_id:
        return None

    base = Path(storage_dir)
    # Prefer mp4, but accept common containers
    for ext in [".mp4", ".mkv", ".webm"]:
        p = base / f"{video_id}{ext}"
        if p.exists():
            return p

    # Fallback: any file with the id
    for f in base.glob(f"{video_id}.*"):
        if f.suffix.lower() in [".mp4", ".mkv", ".webm"]:
            return f
    return None


def get_whisper_service():
    """Get or initialize Whisper service"""
    try:
        whisper_service = WhisperService(
            model_size="medium",
            device=settings.acceleration if settings.acceleration != "mlx" else "cpu",
            compute_type=None
        )
        logger.info("Whisper service initialized successfully")
        return whisper_service
    except Exception as e:
        logger.warning(f"Whisper service initialization failed: {e}. Transcription will not be available.")
        return None


async def download_only_task(record_id: int):
    """
    Download stage only.
    - Sets status to DOWNLOADING, performs yt-dlp download, generates thumbnail.
    - Persists metadata (title/upload_date/etc.).
    - On success, sets status to CONVERTING (ready for later processing), or COMPLETED if item is in playlist.
    """
    db = SessionLocal()
    try:
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if not record:
            logger.error(f"[download] Record {record_id} not found")
            return

        # Skip if already past download stage
        if record.status in [VideoStatus.CONVERTING, VideoStatus.TRANSCRIBING, VideoStatus.SUMMARIZING, VideoStatus.COMPLETED, VideoStatus.FAILED]:
            return

        # Mark downloading
        record.status = VideoStatus.DOWNLOADING
        record.progress = max(record.progress or 0.0, 0.0)
        db.commit()

        # If the file already exists on disk, skip yt-dlp and mark as downloaded.
        existing_file = find_existing_video_file(settings.video_storage_dir, str(record.url))
        if existing_file:
            logger.info(f"[download] Found existing file for record {record_id}, skipping download: {existing_file}")
            record.downloaded_at = record.downloaded_at or datetime.now(timezone.utc)
            record.progress = max(float(record.progress or 0.0), 25.0)
            db.commit()

            # Best-effort thumbnail
            try:
                thumbnail_generator = ThumbnailGenerator(settings.video_storage_dir)
                video_id = extract_video_id(record.url)
                if video_id and not record.thumbnail_path:
                    loop = asyncio.get_event_loop()
                    thumb = await loop.run_in_executor(
                        DOWNLOAD_EXECUTOR,
                        lambda: thumbnail_generator.generate_thumbnail(str(existing_file), video_id),
                    )
                    if thumb:
                        record.thumbnail_path = thumb
                        db.commit()
            except Exception as e:
                logger.warning(f"[download] Failed to generate thumbnail for record {record_id}: {e}")

            is_in_playlist = db.query(PlaylistItem).filter(PlaylistItem.video_record_id == record_id).first() is not None
            if is_in_playlist:
                record.status = VideoStatus.COMPLETED
                record.progress = 100.0
                record.completed_at = datetime.now(timezone.utc)
            else:
                record.status = VideoStatus.CONVERTING
            db.commit()
            return

        video_downloader = VideoDownloader(settings.video_storage_dir)
        thumbnail_generator = ThumbnailGenerator(settings.video_storage_dir)

        def download_progress(p):
            # Keep download within 0-25%
            record.progress = min(float(p) * 0.25, 25.0)
            db.commit()

        loop = asyncio.get_event_loop()
        await _wait_if_downloads_paused()
        await _wait_for_download_spacing()
        try:
            video_info = await loop.run_in_executor(
                DOWNLOAD_EXECUTOR,
                lambda: video_downloader.download(str(record.url), progress_callback=download_progress),
            )
        except VideoDownloadError as e:
            if getattr(e, "blocked", False):
                await _register_blocked_download_failure(str(e))
            raise

        await _reset_blocked_download_counter_on_success()

        record.title = video_info.get('title') or record.title
        # Persist common metadata for future sorting/filtering
        try:
            record.source_video_id = video_info.get('id') or record.source_video_id
            record.thumbnail_url = video_info.get('thumbnail') or record.thumbnail_url
            record.duration_seconds = int(video_info.get('duration') or 0)
            record.channel_id = video_info.get('channel_id') or record.channel_id
            record.channel_title = video_info.get('channel') or record.channel_title
            record.uploader_id = video_info.get('uploader_id') or record.uploader_id
            record.uploader = video_info.get('uploader') or record.uploader
            record.view_count = int(video_info.get('view_count') or 0)
            record.like_count = int(video_info.get('like_count') or 0)
        except Exception as e:
            logger.warning(f"[download] Failed to persist metadata for record {record_id}: {e}")

        # Save upload date if available
        if video_info.get('upload_date'):
            upload_date = video_info['upload_date']
            if upload_date.tzinfo is None:
                upload_date = upload_date.replace(tzinfo=timezone.utc)
            record.upload_date = upload_date

        record.downloaded_at = datetime.now(timezone.utc)
        record.progress = 25.0
        db.commit()

        # Generate thumbnail (best-effort)
        try:
            video_id = extract_video_id(record.url)
            if video_id and video_info.get('file_path'):
                thumb = await loop.run_in_executor(
                    DOWNLOAD_EXECUTOR,
                    lambda: thumbnail_generator.generate_thumbnail(video_info['file_path'], video_id),
                )
                if thumb:
                    record.thumbnail_path = thumb
                    db.commit()
        except Exception as e:
            logger.warning(f"[download] Failed to generate thumbnail for record {record_id}: {e}")

        # If video is in playlist, we treat download as "done"
        is_in_playlist = db.query(PlaylistItem).filter(PlaylistItem.video_record_id == record_id).first() is not None
        if is_in_playlist:
            record.status = VideoStatus.COMPLETED
            record.progress = 100.0
            record.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        # Ready for later heavy processing
        record.status = VideoStatus.CONVERTING
        db.commit()

    except Exception as e:
        logger.error(f"[download] Error downloading record {record_id}: {e}", exc_info=True)
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if record:
            record.status = VideoStatus.FAILED
            record.error_message = str(e)
            db.commit()
    finally:
        db.close()


async def process_video_task(record_id: int):
    """Process video task - can resume from any intermediate state"""
    db = SessionLocal()
    
    try:
        # Get record
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if not record:
            logger.error(f"Record {record_id} not found")
            return
        
        # Skip if already completed or failed
        if record.status in [VideoStatus.COMPLETED, VideoStatus.FAILED]:
            logger.info(f"Record {record_id} is already {record.status}, skipping")
            return
        
        logger.info(f"Processing video record {record_id}: {record.url} (current status: {record.status})")
        
        # Initialize services
        video_downloader = VideoDownloader(settings.video_storage_dir)
        audio_converter = AudioConverter(settings.video_storage_dir)
        whisper_service = get_whisper_service()
        llm_service = LLMService()
        thumbnail_generator = ThumbnailGenerator(settings.video_storage_dir)
        
        # Determine where to resume processing based on current status
        video_info = None
        audio_path = None
        
        # Step 1: Download video (if not already done)
        if record.status in [VideoStatus.PENDING, VideoStatus.DOWNLOADING]:
            logger.info(f"Starting/Resuming download for record {record_id}")
            record.status = VideoStatus.DOWNLOADING
            record.progress = 0.0
            db.commit()
            
            def download_progress(p):
                record.progress = min(p * 0.25, 25.0)
                db.commit()
            
            loop = asyncio.get_event_loop()
            await _wait_if_downloads_paused()
            await _wait_for_download_spacing()
            try:
                video_info = await loop.run_in_executor(
                    DOWNLOAD_EXECUTOR,
                    lambda: video_downloader.download(str(record.url), progress_callback=download_progress),
                )
            except VideoDownloadError as e:
                if getattr(e, "blocked", False):
                    await _register_blocked_download_failure(str(e))
                raise

            await _reset_blocked_download_counter_on_success()
            record.title = video_info['title']
            # Persist common metadata for future sorting/filtering
            try:
                record.source_video_id = video_info.get('id') or record.source_video_id
                record.thumbnail_url = video_info.get('thumbnail') or record.thumbnail_url
                record.duration_seconds = int(video_info.get('duration') or 0)
                record.channel_id = video_info.get('channel_id') or record.channel_id
                record.channel_title = video_info.get('channel') or record.channel_title
                record.uploader_id = video_info.get('uploader_id') or record.uploader_id
                record.uploader = video_info.get('uploader') or record.uploader
                record.view_count = int(video_info.get('view_count') or 0)
                record.like_count = int(video_info.get('like_count') or 0)
            except Exception as e:
                logger.warning(f"Failed to persist metadata for record {record_id}: {e}")

            # Save upload date if available
            if 'upload_date' in video_info and video_info['upload_date']:
                upload_date = video_info['upload_date']
                # Make timezone-aware if not already
                if upload_date.tzinfo is None:
                    upload_date = upload_date.replace(tzinfo=timezone.utc)
                record.upload_date = upload_date
            # Mark download time
            record.downloaded_at = datetime.now(timezone.utc)
            record.progress = 25.0
            db.commit()
            
            # Generate thumbnail
            try:
                video_id = extract_video_id(record.url)
                if video_id and video_info.get('file_path'):
                    thumbnail_path = await loop.run_in_executor(
                        DOWNLOAD_EXECUTOR,
                        lambda: thumbnail_generator.generate_thumbnail(video_info['file_path'], video_id),
                    )
                    if thumbnail_path:
                        record.thumbnail_path = thumbnail_path
                        db.commit()
                        logger.info(f"Generated thumbnail for record {record_id}: {thumbnail_path}")
            except Exception as e:
                logger.warning(f"Failed to generate thumbnail for record {record_id}: {e}")
        else:
            # Try to find existing video file
            video_id = extract_video_id(record.url)
            if not video_id:
                logger.warning(f"Could not extract video ID from URL for record {record_id}: {record.url}, re-downloading")
                record.status = VideoStatus.DOWNLOADING
                record.progress = 0.0
                db.commit()
                
                def download_progress(p):
                    record.progress = min(p * 0.25, 25.0)
                    db.commit()
                
                loop = asyncio.get_event_loop()
                await _wait_if_downloads_paused()
                await _wait_for_download_spacing()
                try:
                    video_info = await loop.run_in_executor(
                        DOWNLOAD_EXECUTOR,
                        lambda: video_downloader.download(str(record.url), progress_callback=download_progress),
                    )
                except VideoDownloadError as e:
                    if getattr(e, "blocked", False):
                        await _register_blocked_download_failure(str(e))
                    raise

                await _reset_blocked_download_counter_on_success()
                record.title = video_info['title']
                # Persist common metadata for future sorting/filtering
                try:
                    record.source_video_id = video_info.get('id') or record.source_video_id
                    record.thumbnail_url = video_info.get('thumbnail') or record.thumbnail_url
                    record.duration_seconds = int(video_info.get('duration') or 0)
                    record.channel_id = video_info.get('channel_id') or record.channel_id
                    record.channel_title = video_info.get('channel') or record.channel_title
                    record.uploader_id = video_info.get('uploader_id') or record.uploader_id
                    record.uploader = video_info.get('uploader') or record.uploader
                    record.view_count = int(video_info.get('view_count') or 0)
                    record.like_count = int(video_info.get('like_count') or 0)
                except Exception as e:
                    logger.warning(f"Failed to persist metadata for record {record_id}: {e}")

                # Save upload date if available
                if 'upload_date' in video_info and video_info['upload_date']:
                    upload_date = video_info['upload_date']
                    # Make timezone-aware if not already
                    if upload_date.tzinfo is None:
                        upload_date = upload_date.replace(tzinfo=timezone.utc)
                    record.upload_date = upload_date
                # Mark download time
                record.downloaded_at = datetime.now(timezone.utc)
                record.progress = 25.0
                db.commit()
                
                # Generate thumbnail
                try:
                    video_id = extract_video_id(record.url)
                    if video_id and video_info.get('file_path'):
                        thumbnail_path = await loop.run_in_executor(
                            DOWNLOAD_EXECUTOR,
                            lambda: thumbnail_generator.generate_thumbnail(video_info['file_path'], video_id),
                        )
                        if thumbnail_path:
                            record.thumbnail_path = thumbnail_path
                            db.commit()
                            logger.info(f"Generated thumbnail for record {record_id}: {thumbnail_path}")
                except Exception as e:
                    logger.warning(f"Failed to generate thumbnail for record {record_id}: {e}")
            else:
                video_path = Path(settings.video_storage_dir) / f"{video_id}.mp4"
                if not video_path.exists():
                    # Try to find any file with the video ID
                    for file in Path(settings.video_storage_dir).glob(f"{video_id}.*"):
                        if file.suffix in ['.mp4', '.webm', '.mkv']:
                            video_path = file
                            break
                
                if video_path.exists():
                    video_info = {
                        'id': video_id,
                        'title': record.title or 'Unknown',
                        'file_path': str(video_path)
                    }
                else:
                    logger.warning(f"Video file not found for record {record_id}, re-downloading")
                    record.status = VideoStatus.DOWNLOADING
                    record.progress = 0.0
                    db.commit()
                    
                    def download_progress(p):
                        record.progress = min(p * 0.25, 25.0)
                        db.commit()
                    
                    loop = asyncio.get_event_loop()
                    await _wait_if_downloads_paused()
                    await _wait_for_download_spacing()
                    try:
                        video_info = await loop.run_in_executor(
                            DOWNLOAD_EXECUTOR,
                            lambda: video_downloader.download(str(record.url), progress_callback=download_progress),
                        )
                    except VideoDownloadError as e:
                        if getattr(e, "blocked", False):
                            await _register_blocked_download_failure(str(e))
                        raise

                    await _reset_blocked_download_counter_on_success()
                    record.title = video_info['title']
                    # Persist common metadata for future sorting/filtering
                    try:
                        record.source_video_id = video_info.get('id') or record.source_video_id
                        record.thumbnail_url = video_info.get('thumbnail') or record.thumbnail_url
                        record.duration_seconds = int(video_info.get('duration') or 0)
                        record.channel_id = video_info.get('channel_id') or record.channel_id
                        record.channel_title = video_info.get('channel') or record.channel_title
                        record.uploader_id = video_info.get('uploader_id') or record.uploader_id
                        record.uploader = video_info.get('uploader') or record.uploader
                        record.view_count = int(video_info.get('view_count') or 0)
                        record.like_count = int(video_info.get('like_count') or 0)
                    except Exception as e:
                        logger.warning(f"Failed to persist metadata for record {record_id}: {e}")

                    record.downloaded_at = datetime.now(timezone.utc)
                    record.progress = 25.0
                    db.commit()
        
        # Check if video is in playlist - if so, skip transcript processing
        is_in_playlist = db.query(PlaylistItem).filter(
            PlaylistItem.video_record_id == record_id
        ).first() is not None
        
        if is_in_playlist:
            logger.info(f"Video {record_id} is in playlist, skipping transcript processing")
            record.status = VideoStatus.COMPLETED
            record.progress = 100.0
            record.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
        
        # If we have downloaded subtitles, skip convert + transcribe; only format and summarize
        subtitle_text = video_info.get("subtitle_text") if video_info else None
        if subtitle_text and len(subtitle_text.strip()) > 20:
            logger.info(f"Record {record_id}: using downloaded subtitle, skipping transcription")
            record.status = VideoStatus.SUMMARIZING
            record.progress = 50.0
            db.commit()
            try:
                formatted_transcript = await llm_service.format_transcript(
                    subtitle_text.strip(),
                    language=record.language or "中文",
                )
                record.transcript = formatted_transcript
            except Exception as e:
                logger.warning(f"Failed to format subtitle for record {record_id}: {e}. Using raw subtitle.")
                record.transcript = subtitle_text.strip()
            video_id_sub = video_info.get("id") or Path(video_info["file_path"]).stem
            transcript_file_path = Path(settings.video_storage_dir) / f"{video_id_sub}.txt"
            transcript_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(transcript_file_path, "w", encoding="utf-8") as f:
                f.write(record.transcript)
            record.transcript_file_path = str(transcript_file_path)
            record.progress = 95.0
            db.commit()
            # Fall through to Step 4 (summarize); Step 2 and 3 will be skipped

        # Step 2: Convert to audio (if not already done)
        if record.status in [VideoStatus.DOWNLOADING, VideoStatus.CONVERTING]:
            logger.info(f"Starting/Resuming audio conversion for record {record_id}")
            record.status = VideoStatus.CONVERTING
            if record.progress < 25.0:
                record.progress = 25.0
            db.commit()

            loop = asyncio.get_event_loop()
            audio_path = await loop.run_in_executor(
                DOWNLOAD_EXECUTOR,
                lambda: audio_converter.convert_to_audio(video_info['file_path']),
            )
            record.progress = 50.0
            db.commit()
        else:
            # Try to find existing audio file (skip if we already have transcript e.g. from subtitle)
            video_id = Path(video_info['file_path']).stem
            audio_path = Path(settings.video_storage_dir) / f"{video_id}.wav"
            if record.transcript and record.transcript_file_path:
                # Transcript already set (e.g. from downloaded subtitle); no need for audio
                audio_path = str(audio_path)
            elif not audio_path.exists():
                logger.warning(f"Audio file not found for record {record_id}, re-converting")
                record.status = VideoStatus.CONVERTING
                record.progress = 25.0
                db.commit()
                
                loop = asyncio.get_event_loop()
                audio_path = await loop.run_in_executor(
                    DOWNLOAD_EXECUTOR,
                    lambda: audio_converter.convert_to_audio(video_info['file_path']),
                )
                record.progress = 50.0
                db.commit()
            else:
                audio_path = str(audio_path)
        
        # Step 3: Transcribe (50-90%)
        # Check if transcript already exists first
        transcript_exists = False
        if record.transcript and record.transcript_file_path:
            transcript_file = Path(record.transcript_file_path)
            if transcript_file.exists() and not record.transcript.startswith("Transcription unavailable"):
                logger.info(f"Transcript already exists for record {record_id}, skipping transcription")
                record.progress = 95.0
                transcript_exists = True
                db.commit()
        
        if not transcript_exists:
            # Need to transcribe
            if record.status in [VideoStatus.CONVERTING, VideoStatus.TRANSCRIBING]:
                logger.info(f"Starting/Resuming transcription for record {record_id}")
                record.status = VideoStatus.TRANSCRIBING
                if record.progress < 50.0:
                    record.progress = 50.0
                db.commit()

            # Get audio duration for better progress tracking using ffprobe (Whisper path uses it)
            audio_duration = None
            try:
                import subprocess
                import json
                result = subprocess.run(
                    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', audio_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    duration_str = data.get('format', {}).get('duration')
                    if duration_str:
                        audio_duration = float(duration_str)
                        logger.info(f"Audio duration for record {record_id}: {audio_duration:.2f} seconds ({audio_duration/60:.2f} minutes)")
            except Exception as e:
                logger.warning(f"Could not get audio duration: {e}, using estimated progress")
                audio_duration = None

            # Import datetime at function level to avoid scope issues
            from datetime import datetime as dt, timezone as tz
            last_progress_update = dt.now(tz.utc)

            def transcribe_progress(timestamp: float):
                nonlocal last_progress_update, audio_duration
                now = dt.now(tz.utc)
                update_interval = 10 if audio_duration and audio_duration > 3600 else 30
                if (now - last_progress_update).total_seconds() > update_interval:
                    try:
                        db.refresh(record)
                        record.updated_at = now
                        last_progress_update = now
                        if audio_duration and audio_duration > 0:
                            progress_ratio = min(timestamp / audio_duration, 1.0)
                            record.progress = 60.0 + (progress_ratio * 30.0)  # 60-90% during segment transcription
                        else:
                            if record.progress < 90.0:
                                record.progress = min(record.progress + 0.5, 90.0)
                        db.commit()
                        logger.info(
                            f"Transcription progress for record {record_id}: {record.progress:.1f}% "
                            f"(timestamp: {timestamp:.1f}s/{audio_duration:.1f}s)"
                            if audio_duration
                            else f"Transcription progress for record {record_id}: {record.progress:.1f}% (timestamp: {timestamp:.1f}s)"
                        )
                    except Exception as e:
                        logger.warning(f"Error updating transcription progress: {e}")

            try:
                if whisper_service is None:
                    raise RuntimeError("Whisper service is not available.")
            except Exception as e:
                logger.warning(f"Transcription unavailable: {e}")
                error_message = f"Transcription unavailable: {e}"
                record.transcript = error_message
                record.language = record.language or "unknown"
                video_id = Path(audio_path).stem
                transcript_file_path = Path(settings.video_storage_dir) / f"{video_id}.txt"
                transcript_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(transcript_file_path, 'w', encoding='utf-8') as f:
                    f.write(error_message)
                record.transcript_file_path = str(transcript_file_path)
                record.progress = 90.0
                db.commit()
            else:
                # Pipeline: resample → denoise → VAD → slice (50% → 55% → 60%)
                record.progress = 55.0
                db.commit()
                loop = asyncio.get_event_loop()
                try:
                    audio_chunks, chunk_metadata = await loop.run_in_executor(
                        DOWNLOAD_EXECUTOR,
                        lambda: run_pipeline(audio_path),
                    )
                except Exception as e:
                    logger.error(f"Audio pipeline failed for record {record_id}: {e}", exc_info=True)
                    raise
                record.progress = 60.0
                db.commit()

                if not audio_chunks or not chunk_metadata:
                    logger.info(f"No speech detected for record {record_id}, using placeholder transcript")
                    transcript_text = ""
                    record.language = record.language or "unknown"
                else:
                    logger.info(
                        f"Starting Whisper segment transcription for record {record_id} "
                        f"(chunks={len(audio_chunks)}, audio duration: {audio_duration/60:.2f} min)" if audio_duration
                        else f"Starting Whisper segment transcription for record {record_id} (chunks={len(audio_chunks)})"
                    )
                    try:
                        def _run_transcribe_segments():
                            return whisper_service.transcribe_segments(
                                audio_chunks,
                                chunk_metadata,
                                language=record.language,
                                progress_callback=transcribe_progress,
                                sample_rate=getattr(settings, "audio_target_sample_rate", 16000),
                            )
                        transcript_result = await loop.run_in_executor(
                            DOWNLOAD_EXECUTOR,
                            _run_transcribe_segments,
                        )
                        logger.info(f"Transcription completed for record {record_id}, segments={len(transcript_result.get('segments', []))}")
                    except Exception as e:
                        logger.error(f"Transcription failed for record {record_id}: {e}", exc_info=True)
                        raise
                    transcript_text = transcript_result.get('text') or ""
                    record.language = transcript_result.get('language', record.language)

                # Format transcript with LLM (Qwen3: punctuation and paragraphs)
                record.progress = 90.0
                db.commit()
                try:
                    logger.info(f"Formatting transcript for record {record_id}...")
                    formatted_transcript = await llm_service.format_transcript(
                        transcript_text,
                        language=record.language or "中文"
                    )
                    record.transcript = formatted_transcript
                    logger.info(f"Transcript formatted successfully for record {record_id}")
                except Exception as e:
                    logger.warning(f"Failed to format transcript for record {record_id}: {e}. Using original transcript.")
                    record.transcript = transcript_text

                video_id = Path(audio_path).stem
                transcript_file_path = Path(settings.video_storage_dir) / f"{video_id}.txt"
                transcript_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(transcript_file_path, 'w', encoding='utf-8') as f:
                    f.write(record.transcript)
                record.transcript_file_path = str(transcript_file_path)
                record.progress = 95.0
                db.commit()
        else:
            # Transcript already exists, just update progress
            if record.progress < 95.0:
                record.progress = 95.0
                db.commit()
        
        # Step 4: Summarize (95-100%)
        if record.status in [VideoStatus.TRANSCRIBING, VideoStatus.SUMMARIZING]:
            logger.info(f"Starting/Resuming summarization for record {record_id}")
            record.status = VideoStatus.SUMMARIZING
            if record.progress < 95.0:
                record.progress = 95.0
            db.commit()
        
        # Generate summary from transcript or video title/description
        if record.transcript and not record.transcript.startswith("Transcription unavailable"):
            summary_text = record.transcript
        else:
            # If no transcript, create a basic summary from video info
            summary_text = f"Video: {record.title or 'Untitled'}. Transcription is not available."
        
        # Use user's preferred summary language (default 中文)
        summary_language = "中文"
        if record.user_id:
            user = db.query(User).filter(User.id == record.user_id).first()
            if user and getattr(user, "summary_language", None):
                summary_language = user.summary_language
        summary = await llm_service.generate_summary(
            summary_text,
            language=summary_language
        )
        record.summary = summary
        
        # Generate keywords automatically using LLM
        try:
            logger.info(f"Generating keywords for record {record_id}...")
            keywords = await llm_service.generate_keywords(
                record.transcript or "",
                record.title or "",
                language=record.language or "中文"
            )
            if keywords:
                record.keywords = keywords
                logger.info(f"Generated keywords for record {record_id}: {keywords}")
            else:
                logger.warning(f"Failed to generate keywords for record {record_id}")
        except Exception as e:
            logger.warning(f"Error generating keywords for record {record_id}: {e}. Continuing without keywords.")
        
        record.progress = 100.0
        record.status = VideoStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info(f"Successfully processed video record {record_id}")
        
    except Exception as e:
        logger.error(f"Error processing video record {record_id}: {e}", exc_info=True)
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if record:
            record.status = VideoStatus.FAILED
            record.error_message = str(e)
            db.commit()
    finally:
        db.close()


async def worker_loop():
    """Main worker loop that polls for pending and stuck tasks"""
    logger.info("Queue worker started")

    download_sem = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    process_sem = asyncio.Semaphore(PROCESS_CONCURRENCY)
    running_downloads = set()
    running_processing = set()

    async def _run_download(rid: int):
        async with download_sem:
            try:
                await download_only_task(rid)
            finally:
                running_downloads.discard(rid)

    async def _run_processing(rid: int):
        async with process_sem:
            try:
                await process_video_task(rid)
            finally:
                running_processing.discard(rid)

    while True:
        db = SessionLocal()
        try:
            # First, check for stuck tasks (tasks in intermediate states that are too old)
            now = datetime.now(timezone.utc)
            stuck_records = db.query(VideoRecord).filter(
                VideoRecord.status.in_([
                    VideoStatus.DOWNLOADING,
                    # VideoStatus.CONVERTING,
                    VideoStatus.TRANSCRIBING,
                    VideoStatus.SUMMARIZING
                ]),
                VideoRecord.user_id.isnot(None)
            ).all()

            for stuck_record in stuck_records:
                record_time = stuck_record.updated_at or stuck_record.created_at
                if record_time and record_time.tzinfo is None:
                    record_time = record_time.replace(tzinfo=timezone.utc)
                if not record_time:
                    continue

                time_since_update = now - record_time
                if stuck_record.status == VideoStatus.TRANSCRIBING:
                    # transcription timeout calculation (same as before)
                    audio_duration_seconds = None
                    try:
                        video_id = extract_video_id(stuck_record.url)
                        if video_id:
                            audio_path = Path(settings.video_storage_dir) / f"{video_id}.wav"
                            if audio_path.exists():
                                import subprocess
                                import json
                                result = subprocess.run(
                                    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(audio_path)],
                                    capture_output=True,
                                    text=True,
                                    timeout=10
                                )
                                if result.returncode == 0:
                                    data = json.loads(result.stdout)
                                    duration_str = data.get('format', {}).get('duration')
                                    if duration_str:
                                        audio_duration_seconds = float(duration_str)
                    except Exception as e:
                        logger.debug(f"Could not get audio duration for timeout calculation: {e}")

                    if audio_duration_seconds:
                        audio_duration = timedelta(seconds=audio_duration_seconds)
                        estimated_timeout = audio_duration * TRANSCRIPTION_SPEED_FACTOR + TRANSCRIPTION_BUFFER_TIME
                        timeout = max(MIN_TRANSCRIPTION_TIMEOUT, min(estimated_timeout, MAX_TRANSCRIPTION_TIMEOUT))
                    else:
                        timeout = timedelta(hours=6)
                else:
                    timeout = BASE_STUCK_TASK_TIMEOUT

                if time_since_update > timeout:
                    # Important: do NOT automatically retry stuck downloads.
                    # If a download gets stuck, mark FAILED and require manual retry.
                    if stuck_record.status == VideoStatus.DOWNLOADING:
                        logger.warning(
                            f"Found stuck download: record {stuck_record.id} "
                            f"in {stuck_record.status} state for {time_since_update} (timeout: {timeout}). Marking FAILED."
                        )
                        stuck_record.status = VideoStatus.FAILED
                        stuck_record.error_message = (
                            f"Download stuck for {time_since_update} (timeout: {timeout}). "
                            f"Marked failed; manual retry required."
                        )
                        db.commit()
                        continue

                    # If it's CONVERTING, the video is already downloaded. Do NOT reset to PENDING.
                    # Instead, keep it in CONVERTING and bump updated_at so processing can pick it up again.
                    if stuck_record.status == VideoStatus.CONVERTING:
                        continue

                    logger.warning(
                        f"Found stuck task: record {stuck_record.id} "
                        f"in {stuck_record.status} state for {time_since_update} (timeout: {timeout}). Resetting to PENDING."
                    )
                    stuck_record.status = VideoStatus.PENDING
                    stuck_record.progress = 0.0
                    stuck_record.error_message = f"Task was stuck in {stuck_record.status} state for {time_since_update}, reset to pending"
                    db.commit()

            # Schedule downloads up to concurrency (unless paused)
            pause_remaining = await _get_download_pause_remaining_seconds()
            if pause_remaining > 0:
                global _last_pause_log_at
                now = _now_utc()
                if _last_pause_log_at is None or (now - _last_pause_log_at).total_seconds() >= 60:
                    _last_pause_log_at = now
                    logger.warning(
                        f"[download] Downloads are PAUSED for another ~{pause_remaining}s due to repeated blocked errors."
                    )
            else:
                download_slots = DOWNLOAD_CONCURRENCY - len(running_downloads)
                if download_slots > 0:
                    pending_downloads = db.query(VideoRecord).filter(
                        VideoRecord.status == VideoStatus.PENDING,
                        VideoRecord.user_id.isnot(None)
                    ).order_by(
                        # Newest videos first (LIFO): prioritize newly added items
                        VideoRecord.created_at.desc(),
                        VideoRecord.id.desc(),
                    ).limit(download_slots).all()

                    for rec in pending_downloads:
                        if rec.id in running_downloads:
                            continue
                        running_downloads.add(rec.id)
                        asyncio.create_task(_run_download(rec.id))

            # Schedule heavy processing (convert/transcribe/summarize) with limited concurrency
            process_slots = PROCESS_CONCURRENCY - len(running_processing)
            if process_slots > 0:
                ready_records = db.query(VideoRecord).filter(
                    VideoRecord.status.in_([VideoStatus.CONVERTING, VideoStatus.TRANSCRIBING, VideoStatus.SUMMARIZING]),
                    VideoRecord.user_id.isnot(None)
                ).order_by(
                    # Newest videos first across convert/transcribe/summarize as well
                    VideoRecord.created_at.desc(),
                    VideoRecord.updated_at.desc().nullslast(),
                    VideoRecord.id.desc(),
                ).limit(process_slots).all()

                for rec in ready_records:
                    if rec.id in running_processing or rec.id in running_downloads:
                        continue
                    running_processing.add(rec.id)
                    asyncio.create_task(_run_processing(rec.id))

            # When nothing is queued, back off a bit
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            await asyncio.sleep(5)
        finally:
            db.close()


async def main():
    """Main entry point"""
    logger.info("Initializing queue worker...")
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")
    
    logger.info("Starting queue worker loop...")
    await worker_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Queue worker stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
