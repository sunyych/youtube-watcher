"""Independent queue worker service. Orchestrates download, convert, transcribe, summarize via app.queue_lib."""
import asyncio
import json
import logging
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func
from app.database import init_db, SessionLocal
from app.models.database import VideoRecord, VideoStatus, PlaylistItem, User, ChannelSubscription
from app.config import settings
from app.services.channel_service import fetch_latest_video_urls, resolve_channel
from app.services.video_downloader import VideoDownloader, VideoDownloadError, looks_like_membership_only_error
from app.services.thumbnail_generator import ThumbnailGenerator
from app.services.llm_service import LLMService

from app.queue_lib import (
    DOWNLOAD_CONCURRENCY,
    DOWNLOAD_EXECUTOR,
    PROCESS_CONCURRENCY,
    BASE_STUCK_TASK_TIMEOUT,
    MIN_TRANSCRIPTION_TIMEOUT,
    MAX_TRANSCRIPTION_TIMEOUT,
    TRANSCRIPTION_SPEED_FACTOR,
    TRANSCRIPTION_BUFFER_TIME,
    PENDING_SUBSCRIPTIONS_INTERVAL_SECONDS,
    RESOLVE_CHANNEL_TIMEOUT_SECONDS,
    SUBSCRIPTION_CHECK_INTERVAL_HOURS,
    SUBSCRIPTION_MAX_VIDEOS_PER_CHANNEL,
    extract_video_id,
    find_existing_video_file,
    now_utc,
    download_only_task,
    get_download_pause_remaining_seconds,
    reset_blocked_download_counter_on_success,
    register_blocked_download_failure,
    wait_for_download_spacing,
    wait_if_downloads_paused,
    ensure_audio_for_record,
    get_whisper_service,
    run_transcribe_stage,
    run_summarize_stage,
    set_runner_queue_and_started,
    _runner_worker,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_last_subscription_check_at: Optional[datetime] = None
_last_pending_subscriptions_at: Optional[datetime] = None
_last_pause_log_at: Optional[datetime] = None


async def process_video_task(record_id: int):
    """Process video task - can resume from any intermediate state"""
    db = SessionLocal()
    
    try:
        # Get record
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if not record:
            logger.error(f"Record {record_id} not found")
            return
        
        # Skip if already completed, failed, or unavailable (e.g. member-only)
        if record.status in [VideoStatus.COMPLETED, VideoStatus.FAILED, VideoStatus.UNAVAILABLE]:
            logger.info(f"Record {record_id} is already {record.status}, skipping")
            return
        
        logger.info(f"Processing video record {record_id}: {record.url} (current status: {record.status})")
        
        # Initialize services
        video_downloader = VideoDownloader(settings.video_storage_dir)
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
            await wait_if_downloads_paused()
            await wait_for_download_spacing()
            try:
                video_info = await loop.run_in_executor(
                    DOWNLOAD_EXECUTOR,
                    lambda: video_downloader.download(str(record.url), progress_callback=download_progress),
                )
            except VideoDownloadError as e:
                if getattr(e, "blocked", False):
                    await register_blocked_download_failure(str(e))
                raise

            await reset_blocked_download_counter_on_success()
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
                await wait_if_downloads_paused()
                await wait_for_download_spacing()
                try:
                    video_info = await loop.run_in_executor(
                        DOWNLOAD_EXECUTOR,
                        lambda: video_downloader.download(str(record.url), progress_callback=download_progress),
                    )
                except VideoDownloadError as e:
                    if getattr(e, "blocked", False):
                        await register_blocked_download_failure(str(e))
                    raise

                await reset_blocked_download_counter_on_success()
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
                    await wait_if_downloads_paused()
                    await wait_for_download_spacing()
                    try:
                        video_info = await loop.run_in_executor(
                            DOWNLOAD_EXECUTOR,
                            lambda: video_downloader.download(str(record.url), progress_callback=download_progress),
                        )
                    except VideoDownloadError as e:
                        if getattr(e, "blocked", False):
                            await register_blocked_download_failure(str(e))
                        raise

                    await reset_blocked_download_counter_on_success()
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
        
        # # Check if video is in playlist - if so, skip transcript processing
        is_in_playlist = db.query(PlaylistItem).filter(
            PlaylistItem.video_record_id == record_id, 
            PlaylistItem.playlist_id == 2
        ).first() is not None
        
        if is_in_playlist:
            logger.info(f"Video {record_id} is in playlist, skipping transcript processing")
            record.status = VideoStatus.COMPLETED
            record.progress = 100.0
            record.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
        
        # Step 2: Convert to audio (queue_lib.convert)
        audio_path = await ensure_audio_for_record(record_id, db, record, video_info)
        if not audio_path:
            return

        # Step 3: Transcribe (queue_lib.transcribe)
        transcribe_ok = await run_transcribe_stage(
            record_id, db, record, audio_path,
            whisper_service=whisper_service,
            llm_service=llm_service,
        )
        if not transcribe_ok:
            logger.warning(
                f"Transcription did not succeed for record {record_id}, skipping summarize (will retry later)"
            )
            return

        # Step 4: Summarize (queue_lib.summarize) — only when transcribe succeeded
        await run_summarize_stage(record_id, db, record, llm_service)
        logger.info(f"Successfully processed video record {record_id}")

    except Exception as e:
        logger.error(f"Error processing video record {record_id}: {e}", exc_info=True)
        record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
        if record:
            err_msg = str(e)
            if "LLM请求失败" in err_msg or "生成总结失败" in err_msg:
                logger.warning(
                    f"LLM error while processing record {record_id}, keeping status for retry: {err_msg}"
                )
                if record.status not in [VideoStatus.COMPLETED, VideoStatus.UNAVAILABLE]:
                    record.status = VideoStatus.SUMMARIZING
                record.error_message = err_msg
            elif looks_like_membership_only_error(err_msg):
                record.status = VideoStatus.UNAVAILABLE
                record.error_message = err_msg
            else:
                record.status = VideoStatus.FAILED
                record.error_message = err_msg
            db.commit()
    finally:
        db.close()


async def _process_pending_subscriptions_task():
    """Resolve pending subscriptions (channel_url -> channel_id, channel_title) in the background."""
    db = SessionLocal()
    resolved_any = False
    try:
        pending = (
            db.query(ChannelSubscription)
            .filter(ChannelSubscription.status == "pending", ChannelSubscription.channel_id.is_(None))
            .all()
        )
        if not pending:
            return
        logger.info("Processing %d pending subscription(s)", len(pending))
        loop = asyncio.get_event_loop()
        for idx, sub in enumerate(pending, 1):
            try:
                logger.info(
                    "Resolving subscription %s (%d/%d): %s",
                    sub.id, idx, len(pending), sub.channel_url[:80] + ("..." if len(sub.channel_url) > 80 else ""),
                )
                try:
                    channel_id, channel_title = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda s=sub: resolve_channel(s.channel_url),
                        ),
                        timeout=RESOLVE_CHANNEL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Resolving subscription %s timed out after %ds, will retry later",
                        sub.id, RESOLVE_CHANNEL_TIMEOUT_SECONDS,
                    )
                    continue
                if not channel_id:
                    logger.warning("Could not resolve channel for subscription %s URL %s", sub.id, sub.channel_url)
                    continue
                existing = (
                    db.query(ChannelSubscription)
                    .filter(
                        ChannelSubscription.user_id == sub.user_id,
                        ChannelSubscription.channel_id == channel_id,
                        ChannelSubscription.id != sub.id,
                    )
                    .first()
                )
                if existing:
                    db.delete(sub)
                    logger.info("Subscription %s merged into existing %s (channel %s)", sub.id, existing.id, channel_id)
                    resolved_any = True
                else:
                    sub.channel_id = channel_id
                    sub.channel_title = channel_title
                    sub.status = "resolved"
                    logger.info(
                        "Subscription %s resolved to channel %s (%s)",
                        sub.id, channel_id, (channel_title or "")[:50],
                    )
                    resolved_any = True
            except Exception as e:
                logger.warning("Failed to resolve subscription %s: %s", sub.id, e, exc_info=True)
        db.commit()
        if resolved_any:
            asyncio.create_task(_subscription_check_task())
            logger.info("Triggered subscription check for newly resolved channel(s)")
    except Exception as e:
        logger.error("Process pending subscriptions failed: %s", e, exc_info=True)
        db.rollback()
    finally:
        db.close()


async def _subscription_check_task():
    """Fetch latest videos from every subscription (pending or resolved) and enqueue new URLs."""
    global _last_subscription_check_at
    _last_subscription_check_at = now_utc()
    db = SessionLocal()
    try:
        subs = db.query(ChannelSubscription).filter(ChannelSubscription.channel_url.isnot(None)).all()
        if not subs:
            return
        logger.info("Running subscription check for %d channel(s)", len(subs))
        loop = asyncio.get_event_loop()
        for idx, sub in enumerate(subs, 1):
            try:
                if sub.channel_id:
                    linked = db.query(VideoRecord).filter(
                        VideoRecord.user_id == sub.user_id,
                        VideoRecord.channel_id == sub.channel_id,
                        VideoRecord.subscription_id.is_(None),
                    ).update({VideoRecord.subscription_id: sub.id}, synchronize_session=False)
                    if linked:
                        logger.info("Subscription %s: linked %d existing video(s) from this channel", sub.id, linked)
                logger.info("Fetching videos for subscription %s (%d/%d): %s", sub.id, idx, len(subs), (sub.channel_url or "")[:60])
                urls = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda s=sub: fetch_latest_video_urls(s.channel_url, max_items=SUBSCRIPTION_MAX_VIDEOS_PER_CHANNEL),
                    ),
                    timeout=RESOLVE_CHANNEL_TIMEOUT_SECONDS,
                )
                auto_playlist_id = getattr(sub, "auto_playlist_id", None)
                next_position = None
                if auto_playlist_id:
                    max_pos = db.query(func.max(PlaylistItem.position)).filter(
                        PlaylistItem.playlist_id == auto_playlist_id
                    ).scalar() or 0
                    next_position = max_pos + 1
                added = 0
                for url in urls:
                    existing = (
                        db.query(VideoRecord)
                        .filter(VideoRecord.user_id == sub.user_id, VideoRecord.url == url)
                        .first()
                    )
                    if not existing:
                        record = VideoRecord(
                            url=url,
                            user_id=sub.user_id,
                            subscription_id=sub.id,
                            status=VideoStatus.PENDING,
                            progress=0.0,
                        )
                        db.add(record)
                        db.flush()
                        if auto_playlist_id and next_position is not None:
                            db.add(PlaylistItem(
                                playlist_id=auto_playlist_id,
                                video_record_id=record.id,
                                position=next_position,
                            ))
                            next_position += 1
                        added += 1
                if added:
                    logger.info("Subscription %s: enqueued %d new video(s) for download", sub.id, added)
                sub.last_check_at = now_utc()
            except asyncio.TimeoutError:
                logger.warning("Fetch videos for subscription %s timed out after %ds", sub.id, RESOLVE_CHANNEL_TIMEOUT_SECONDS)
            except Exception as e:
                logger.warning("Subscription check failed for subscription %s: %s", sub.id, e, exc_info=True)
        db.commit()
    except Exception as e:
        logger.error("Subscription check failed: %s", e, exc_info=True)
        db.rollback()
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
            now = datetime.now(timezone.utc)
            stuck_records = db.query(VideoRecord).filter(
                VideoRecord.status.in_([
                    VideoStatus.DOWNLOADING,
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
                    audio_duration_seconds = None
                    try:
                        video_id = extract_video_id(stuck_record.url)
                        if video_id:
                            audio_path = Path(settings.video_storage_dir) / f"{video_id}.wav"
                            if audio_path.exists():
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

            pause_remaining = await get_download_pause_remaining_seconds()
            if pause_remaining > 0:
                global _last_pause_log_at
                now_ts = now_utc()
                if _last_pause_log_at is None or (now_ts - _last_pause_log_at).total_seconds() >= 60:
                    _last_pause_log_at = now_ts
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
                        VideoRecord.created_at.desc(),
                        VideoRecord.id.desc(),
                    ).limit(download_slots).all()

                    for rec in pending_downloads:
                        if rec.id in running_downloads:
                            continue
                        running_downloads.add(rec.id)
                        asyncio.create_task(_run_download(rec.id))

            process_slots = PROCESS_CONCURRENCY - len(running_processing)
            if process_slots > 0:
                ready_records = db.query(VideoRecord).filter(
                    VideoRecord.status.in_([VideoStatus.CONVERTING, VideoStatus.TRANSCRIBING, VideoStatus.SUMMARIZING]),
                    VideoRecord.user_id.isnot(None)
                ).order_by(
                    VideoRecord.created_at.desc(),
                    VideoRecord.updated_at.desc().nullslast(),
                    VideoRecord.id.desc(),
                ).limit(process_slots).all()

                for rec in ready_records:
                    if rec.id in running_processing or rec.id in running_downloads:
                        continue
                    running_processing.add(rec.id)
                    asyncio.create_task(_run_processing(rec.id))

            global _last_pending_subscriptions_at
            if _last_pending_subscriptions_at is None or (
                (now - _last_pending_subscriptions_at).total_seconds() >= PENDING_SUBSCRIPTIONS_INTERVAL_SECONDS
            ):
                _last_pending_subscriptions_at = now
                asyncio.create_task(_process_pending_subscriptions_task())
            global _last_subscription_check_at
            if _last_subscription_check_at is None or (
                (now - _last_subscription_check_at).total_seconds() >= SUBSCRIPTION_CHECK_INTERVAL_HOURS * 3600
            ):
                _last_subscription_check_at = now
                asyncio.create_task(_subscription_check_task())

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

    runner_url = (getattr(settings, "transcribe_runner_url", None) or "").strip()
    if runner_url:
        set_runner_queue_and_started(asyncio.Queue(), True)
        n = max(1, getattr(settings, "transcribe_runner_concurrency", 3))
        for _ in range(n):
            asyncio.create_task(_runner_worker())
        logger.info("Transcribe runner queue enabled: %d concurrent jobs (one per GPU slot)", n)

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
