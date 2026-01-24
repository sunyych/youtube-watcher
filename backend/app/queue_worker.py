"""Independent queue worker service"""
import asyncio
import logging
import sys
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, SessionLocal
from app.models.database import VideoRecord, VideoStatus, PlaylistItem
from app.config import settings
from app.services.video_downloader import VideoDownloader
from app.services.audio_converter import AudioConverter
from app.services.whisper_service import WhisperService
from app.services.llm_service import LLMService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            
            video_info = video_downloader.download(str(record.url), progress_callback=download_progress)
            record.title = video_info['title']
            record.progress = 25.0
            db.commit()
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
                
                video_info = video_downloader.download(str(record.url), progress_callback=download_progress)
                record.title = video_info['title']
                record.progress = 25.0
                db.commit()
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
                    
                    video_info = video_downloader.download(str(record.url), progress_callback=download_progress)
                    record.title = video_info['title']
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
        
        # Step 2: Convert to audio (if not already done)
        if record.status in [VideoStatus.DOWNLOADING, VideoStatus.CONVERTING]:
            logger.info(f"Starting/Resuming audio conversion for record {record_id}")
            record.status = VideoStatus.CONVERTING
            if record.progress < 25.0:
                record.progress = 25.0
            db.commit()
            
            audio_path = audio_converter.convert_to_audio(video_info['file_path'])
            record.progress = 50.0
            db.commit()
        else:
            # Try to find existing audio file
            video_id = Path(video_info['file_path']).stem
            audio_path = Path(settings.video_storage_dir) / f"{video_id}.wav"
            if not audio_path.exists():
                logger.warning(f"Audio file not found for record {record_id}, re-converting")
                record.status = VideoStatus.CONVERTING
                record.progress = 25.0
                db.commit()
                
                audio_path = audio_converter.convert_to_audio(video_info['file_path'])
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
            
            if whisper_service is None:
                # Skip transcription if Whisper is not available
                logger.warning("Whisper service not available, skipping transcription")
                error_message = "Transcription unavailable: faster-whisper is not installed. Please install faster-whisper to enable transcription."
                record.transcript = error_message
                record.language = record.language or "unknown"
                
                # Save error message to file as well
                video_id = Path(audio_path).stem
                transcript_file_path = Path(settings.video_storage_dir) / f"{video_id}.txt"
                transcript_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(transcript_file_path, 'w', encoding='utf-8') as f:
                    f.write(error_message)
                record.transcript_file_path = str(transcript_file_path)
                
                record.progress = 90.0
                db.commit()
            else:
                # Get audio duration for better progress tracking using ffprobe
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
                    # Update updated_at to prevent stuck task detection
                    now = dt.now(tz.utc)
                    # Update more frequently (every 10 seconds) for long videos
                    update_interval = 10 if audio_duration and audio_duration > 3600 else 30
                    if (now - last_progress_update).total_seconds() > update_interval:
                        try:
                            # Refresh record from database to get latest state
                            db.refresh(record)
                            record.updated_at = now
                            last_progress_update = now
                            
                            # Calculate progress based on timestamp if we have duration
                            if audio_duration and audio_duration > 0:
                                progress_ratio = min(timestamp / audio_duration, 1.0)
                                record.progress = 50.0 + (progress_ratio * 40.0)  # 50-90%
                            else:
                                # Fallback: increment slowly
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
                
                logger.info(f"Starting transcription for record {record_id} (audio duration: {audio_duration/60:.2f} minutes)")
                try:
                    # Run transcription in a thread pool to avoid blocking the event loop
                    # This is important for long audio files
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        transcript_result = await loop.run_in_executor(
                            executor,
                            lambda: whisper_service.transcribe(
                                audio_path,
                                language=record.language,
                                progress_callback=transcribe_progress
                            )
                        )
                    logger.info(f"Transcription completed for record {record_id}, processing {len(transcript_result.get('segments', []))} segments")
                except Exception as e:
                    logger.error(f"Transcription failed for record {record_id}: {e}", exc_info=True)
                    raise
                
                transcript_text = transcript_result['text']
                record.language = transcript_result.get('language', record.language)
                
                # Format transcript with LLM (add punctuation and organize into paragraphs)
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
                    # If formatting fails, use original transcript
                    record.transcript = transcript_text
                
                # Save formatted transcript to file
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
        
        summary = await llm_service.generate_summary(
            summary_text,
            language=record.language or "中文"
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
    
    while True:
        db = SessionLocal()
        try:
            # First, check for stuck tasks (tasks in intermediate states that are too old)
            # Use timezone-aware datetime to match database timestamps
            now = datetime.now(timezone.utc)
            stuck_records = db.query(VideoRecord).filter(
                VideoRecord.status.in_([
                    VideoStatus.DOWNLOADING,
                    VideoStatus.CONVERTING,
                    VideoStatus.TRANSCRIBING,
                    VideoStatus.SUMMARIZING
                ]),
                VideoRecord.user_id.isnot(None)
            ).all()
            
            for stuck_record in stuck_records:
                # Check if task is stuck (no update for too long)
                # Get the timestamp, ensuring it's timezone-aware
                record_time = stuck_record.updated_at or stuck_record.created_at
                if record_time:
                    # If record_time is timezone-naive, assume it's UTC
                    if record_time.tzinfo is None:
                        record_time = record_time.replace(tzinfo=timezone.utc)
                    time_since_update = now - record_time
                    
                    # Use longer timeout for transcription tasks (which can take hours for long videos)
                    if stuck_record.status == VideoStatus.TRANSCRIBING:
                        # Try to get audio duration to calculate appropriate timeout
                        audio_duration_seconds = None
                        try:
                            # Extract video ID and find audio file
                            video_id = extract_video_id(stuck_record.url)
                            if video_id:
                                audio_path = Path(settings.video_storage_dir) / f"{video_id}.wav"
                                if audio_path.exists():
                                    # Get audio duration using ffprobe
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
                        
                        # Calculate timeout based on audio duration
                        if audio_duration_seconds:
                            # Transcription speed: medium model on CPU is ~0.1-0.3x realtime
                            # Use conservative estimate: 10x audio duration + buffer
                            audio_duration = timedelta(seconds=audio_duration_seconds)
                            estimated_timeout = audio_duration * TRANSCRIPTION_SPEED_FACTOR + TRANSCRIPTION_BUFFER_TIME
                            # Clamp between min and max
                            timeout = max(MIN_TRANSCRIPTION_TIMEOUT, min(estimated_timeout, MAX_TRANSCRIPTION_TIMEOUT))
                            logger.debug(
                                f"Calculated transcription timeout for record {stuck_record.id}: "
                                f"{timeout} (audio: {audio_duration}, estimated: {estimated_timeout})"
                            )
                        else:
                            # Fallback: use a generous fixed timeout if we can't get duration
                            timeout = timedelta(hours=6)  # 6 hours default for transcription
                            logger.debug(f"Using default transcription timeout for record {stuck_record.id}: {timeout}")
                    else:
                        timeout = BASE_STUCK_TASK_TIMEOUT
                    
                    if time_since_update > timeout:
                        logger.warning(
                            f"Found stuck task: record {stuck_record.id} "
                            f"in {stuck_record.status} state for {time_since_update} (timeout: {timeout}). Resetting to PENDING."
                        )
                        stuck_record.status = VideoStatus.PENDING
                        stuck_record.progress = 0.0
                        stuck_record.error_message = f"Task was stuck in {stuck_record.status} state for {time_since_update}, reset to pending"
                        db.commit()
            
            # Find pending tasks (only one at a time to avoid conflicts)
            # Only process records that have a user_id (migrated records)
            pending_record = db.query(VideoRecord).filter(
                VideoRecord.status == VideoStatus.PENDING,
                VideoRecord.user_id.isnot(None)  # Only process records with user_id
            ).order_by(VideoRecord.created_at.asc()).first()
            
            # If no pending tasks, check for stuck intermediate tasks to resume
            if not pending_record:
                stuck_intermediate = db.query(VideoRecord).filter(
                    VideoRecord.status.in_([
                        VideoStatus.DOWNLOADING,
                        VideoStatus.CONVERTING,
                        VideoStatus.TRANSCRIBING,
                        VideoStatus.SUMMARIZING
                    ]),
                    VideoRecord.user_id.isnot(None)
                ).order_by(VideoRecord.updated_at.asc()).first()
                
                if stuck_intermediate:
                    logger.info(
                        f"Found intermediate task to resume: record {stuck_intermediate.id} "
                        f"in {stuck_intermediate.status} state"
                    )
                    pending_record = stuck_intermediate
            
            if pending_record:
                # Update queue position before processing (for this user)
                if pending_record.status == VideoStatus.PENDING:
                    pending_count = db.query(VideoRecord).filter(
                        VideoRecord.status == VideoStatus.PENDING,
                        VideoRecord.user_id == pending_record.user_id,
                        VideoRecord.id < pending_record.id
                    ).count()
                    pending_record.queue_position = pending_count + 1
                    db.commit()
                
                logger.info(f"Processing task: record {pending_record.id} for user {pending_record.user_id}")
                await process_video_task(pending_record.id)
            else:
                # No pending tasks, wait a bit
                await asyncio.sleep(2)
                
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
