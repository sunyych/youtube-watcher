"""Video processing routes"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request, Response, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from pathlib import Path
from datetime import datetime, timezone
import json
import asyncio
import logging
import re
import os

from app.database import get_db, init_db
from app.models.database import VideoRecord, VideoStatus, User
from app.routers.auth import get_current_user
from app.services.video_downloader import VideoDownloader
from app.services.audio_converter import AudioConverter
from app.services.llm_service import LLMService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["video"])

# Initialize services (Whisper is only loaded in queue worker)
video_downloader = VideoDownloader(settings.video_storage_dir)
audio_converter = AudioConverter(settings.video_storage_dir)
llm_service = LLMService()
# Queue processing is handled by independent queue worker service


class ProcessVideoRequest(BaseModel):
    url: HttpUrl
    language: Optional[str] = None


class VideoStatusResponse(BaseModel):
    id: int
    url: str
    title: Optional[str]
    status: str
    progress: float
    queue_position: Optional[int]
    error_message: Optional[str]
    watch_position_seconds: Optional[float] = None


class RetryAllFailedResponse(BaseModel):
    retried_count: int
    record_ids: List[int]


class TaskItemResponse(BaseModel):
    id: int
    url: str
    title: Optional[str]
    status: str
    progress: float
    error_message: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    downloaded_at: Optional[str]
    completed_at: Optional[str]


class TaskListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[TaskItemResponse]


class WatchPositionRequest(BaseModel):
    position_seconds: float


class BulkIdsRequest(BaseModel):
    record_ids: List[int]


class BulkActionResponse(BaseModel):
    updated_count: int
    record_ids: List[int]


# Video processing is now handled by the independent queue worker service


@router.post("/process", response_model=VideoStatusResponse)
async def process_video(
    request: ProcessVideoRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Process video from URL"""
    url_str = str(request.url)
    
    # Check if URL already exists for this user
    existing_record = db.query(VideoRecord).filter(
        VideoRecord.url == url_str,
        VideoRecord.user_id == user.id
    ).order_by(VideoRecord.created_at.desc()).first()
    
    if existing_record:
        # Update updated_at to make it appear at the top of the list
        from datetime import datetime
        existing_record.updated_at = datetime.now()
        # Update language if provided
        if request.language:
            existing_record.language = request.language
        db.commit()
        db.refresh(existing_record)
        
        # Calculate queue position
        if existing_record.status == VideoStatus.PENDING:
            pending_count = db.query(VideoRecord).filter(
                VideoRecord.status == VideoStatus.PENDING,
                VideoRecord.user_id == user.id,
                VideoRecord.id < existing_record.id
            ).count()
            existing_record.queue_position = pending_count + 1
            db.commit()
        
        logger.info(f"Found existing record for URL: {url_str}, returning record {existing_record.id}")
        return VideoStatusResponse(
            id=existing_record.id,
            url=existing_record.url,
            title=existing_record.title,
            status=existing_record.status.value,
            progress=existing_record.progress,
            queue_position=existing_record.queue_position,
            error_message=existing_record.error_message,
            watch_position_seconds=existing_record.watch_position_seconds,
        )
    
    # Create new record with PENDING status - queue worker will pick it up
    record = VideoRecord(
        url=url_str,
        user_id=user.id,
        status=VideoStatus.PENDING,
        progress=0.0,
        language=request.language
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    
    # Calculate queue position (pending records before this one for this user)
    pending_count = db.query(VideoRecord).filter(
        VideoRecord.status == VideoStatus.PENDING,
        VideoRecord.user_id == user.id,
        VideoRecord.id < record.id
    ).count()
    record.queue_position = pending_count + 1
    db.commit()
    
    # Note: Tags will be extracted from title when video is downloaded and added to playlist
    
    return VideoStatusResponse(
        id=record.id,
        url=record.url,
        title=record.title,
        status=record.status.value,
        progress=record.progress,
        queue_position=record.queue_position,
        error_message=record.error_message,
        watch_position_seconds=record.watch_position_seconds,
    )


@router.get("/status/{record_id}", response_model=VideoStatusResponse)
async def get_video_status(
    record_id: int,
    count_read: bool = Query(False, description="Increment read_count when opening the player"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get video processing status"""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if count_read:
        record.bump_read_count()

    # Update queue position if pending
    if record.status == VideoStatus.PENDING:
        pending_count = db.query(VideoRecord).filter(
            VideoRecord.status == VideoStatus.PENDING,
            VideoRecord.user_id == user.id,
            VideoRecord.id < record.id
        ).count()
        record.queue_position = pending_count + 1
        db.commit()
    elif count_read:
        db.commit()
    
    return VideoStatusResponse(
        id=record.id,
        url=record.url,
        title=record.title,
        status=record.status.value,
        progress=record.progress,
        queue_position=record.queue_position,
        error_message=record.error_message,
        watch_position_seconds=record.watch_position_seconds,
    )


@router.put("/status/{record_id}/watch-position")
async def save_watch_position(
    record_id: int,
    body: WatchPositionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save playback position for the current user (for resume across devices)."""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    position = max(0.0, float(body.position_seconds))
    record.watch_position_seconds = position
    record.watch_updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"position_seconds": position}


@router.get("/queue")
async def get_queue_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get queue status"""
    pending_count = db.query(VideoRecord).filter(
        VideoRecord.status == VideoStatus.PENDING,
        VideoRecord.user_id == user.id
    ).count()
    
    processing_records = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        VideoRecord.status.in_([
            VideoStatus.DOWNLOADING,
            VideoStatus.CONVERTING,
            VideoStatus.TRANSCRIBING,
            VideoStatus.SUMMARIZING
        ])
    ).all()
    
    return {
        "queue_size": pending_count,
        "processing": len(processing_records),
        "processing_tasks": [
            {
                "id": record.id,
                "status": record.status.value,
            }
            for record in processing_records
        ]
    }


@router.post("/retry/{record_id}", response_model=VideoStatusResponse)
async def retry_video(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Retry processing a failed video"""
    # Get the failed record (only for this user)
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if record.status != VideoStatus.FAILED:
        raise HTTPException(status_code=400, detail="Video is not in failed status")
    
    # Reset record status to PENDING - queue worker will pick it up
    record.status = VideoStatus.PENDING
    record.progress = 0.0
    record.error_message = None
    
    # Calculate queue position (pending records before this one for this user)
    pending_count = db.query(VideoRecord).filter(
        VideoRecord.status == VideoStatus.PENDING,
        VideoRecord.user_id == user.id,
        VideoRecord.id < record.id
    ).count()
    record.queue_position = pending_count + 1
    db.commit()
    db.refresh(record)
    
    return VideoStatusResponse(
        id=record.id,
        url=record.url,
        title=record.title,
        status=record.status.value,
        progress=record.progress,
        queue_position=record.queue_position,
        error_message=record.error_message,
        watch_position_seconds=record.watch_position_seconds,
    )


@router.post("/retry-failed", response_model=RetryAllFailedResponse)
async def retry_all_failed_videos(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retry all FAILED videos for the current user."""
    failed_records = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        VideoRecord.status == VideoStatus.FAILED
    ).order_by(VideoRecord.created_at.asc()).all()

    record_ids = [r.id for r in failed_records]
    if not record_ids:
        return RetryAllFailedResponse(retried_count=0, record_ids=[])

    for record in failed_records:
        record.status = VideoStatus.PENDING
        record.progress = 0.0
        record.error_message = None

    db.commit()
    return RetryAllFailedResponse(retried_count=len(record_ids), record_ids=record_ids)


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    statuses: List[VideoStatus] = Query(..., description="Filter by one or more statuses"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List tasks by status (paginated) for the current user."""
    limit = max(1, min(int(limit), 200))
    skip = max(0, int(skip))

    query = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        VideoRecord.status.in_(statuses),
    )
    total = query.count()

    records = (
        query.order_by(VideoRecord.updated_at.desc().nullslast(), VideoRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    def _dt(v):
        return v.isoformat() if v else None

    items = [
        TaskItemResponse(
            id=r.id,
            url=r.url,
            title=r.title,
            status=r.status.value,
            progress=float(r.progress or 0.0),
            error_message=r.error_message,
            created_at=_dt(r.created_at),
            updated_at=_dt(r.updated_at),
            downloaded_at=_dt(r.downloaded_at),
            completed_at=_dt(r.completed_at),
        )
        for r in records
    ]

    return TaskListResponse(total=total, skip=skip, limit=limit, items=items)


@router.post("/bulk/retry", response_model=BulkActionResponse)
async def bulk_retry(
    request: BulkIdsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reset selected records to PENDING so the queue worker retries them."""
    record_ids = sorted(set(int(x) for x in request.record_ids if x is not None))
    if not record_ids:
        return BulkActionResponse(updated_count=0, record_ids=[])

    records = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        VideoRecord.id.in_(record_ids),
    ).all()

    updated = []
    for r in records:
        # Do not retry already completed items
        if r.status == VideoStatus.COMPLETED:
            continue
        r.status = VideoStatus.PENDING
        r.progress = 0.0
        r.error_message = None
        r.queue_position = None
        r.completed_at = None
        updated.append(r.id)

    db.commit()
    return BulkActionResponse(updated_count=len(updated), record_ids=updated)


@router.post("/bulk/restart-transcribe", response_model=BulkActionResponse)
async def bulk_restart_transcribe(
    request: BulkIdsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Restart transcription for selected records.
    This clears transcript + summary and sets status to TRANSCRIBING.
    """
    record_ids = sorted(set(int(x) for x in request.record_ids if x is not None))
    if not record_ids:
        return BulkActionResponse(updated_count=0, record_ids=[])

    records = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        VideoRecord.id.in_(record_ids),
    ).all()

    for r in records:
        r.transcript = None
        r.transcript_file_path = None
        r.summary = None
        r.error_message = None
        r.completed_at = None
        r.status = VideoStatus.TRANSCRIBING
        r.progress = max(float(r.progress or 0.0), 50.0)

    db.commit()
    return BulkActionResponse(updated_count=len(records), record_ids=[r.id for r in records])


@router.post("/bulk/restart-summary", response_model=BulkActionResponse)
async def bulk_restart_summary(
    request: BulkIdsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restart summarization only for selected records (keeps transcript)."""
    record_ids = sorted(set(int(x) for x in request.record_ids if x is not None))
    if not record_ids:
        return BulkActionResponse(updated_count=0, record_ids=[])

    records = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        VideoRecord.id.in_(record_ids),
    ).all()

    for r in records:
        r.summary = None
        r.error_message = None
        r.completed_at = None
        r.status = VideoStatus.SUMMARIZING
        r.progress = max(float(r.progress or 0.0), 95.0)

    db.commit()
    return BulkActionResponse(updated_count=len(records), record_ids=[r.id for r in records])


@router.websocket("/progress/{record_id}")
async def websocket_progress(websocket: WebSocket, record_id: int):
    """WebSocket endpoint for real-time progress updates"""
    await websocket.accept()
    db = next(get_db())
    
    # Note: WebSocket doesn't support Depends, so we'll need to get user from token
    # For now, we'll allow access but this should be secured in production
    try:
        while True:
            record = db.query(VideoRecord).filter(VideoRecord.id == record_id).first()
            if not record:
                await websocket.send_json({"error": "Video not found"})
                break
            
            if record.status == VideoStatus.COMPLETED or record.status == VideoStatus.FAILED:
                await websocket.send_json({
                    "status": record.status.value,
                    "progress": record.progress,
                    "completed": True
                })
                break
            
            await websocket.send_json({
                "status": record.status.value,
                "progress": record.progress,
                "queue_position": record.queue_position
            })
            
            await asyncio.sleep(1)  # Update every second
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        db.close()


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL"""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user from token in header or query parameter"""
    from fastapi.security import HTTPAuthorizationCredentials
    from jose import JWTError, jwt
    from app.config import settings
    
    # Try to get token from Authorization header
    auth_header = request.headers.get("Authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        logger.debug(f"Got token from Authorization header")
    else:
        # Try to get token from query parameter
        token = request.query_params.get("token")
        if token:
            logger.debug(f"Got token from query parameter")
    
    if not token:
        logger.warning(f"No token found in request. Headers: {dict(request.headers)}, Query: {dict(request.query_params)}")
        return None
    
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            logger.warning("Token payload missing 'sub' field")
            return None
        
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            logger.warning(f"User {user_id} not found in database")
        return user
    except (JWTError, ValueError, TypeError) as e:
        logger.warning(f"Token validation failed: {e}")
        return None


@router.get("/{record_id}/thumbnail")
async def get_video_thumbnail(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get video thumbnail image"""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if not record.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    thumbnail_path = Path(record.thumbnail_path)
    if not thumbnail_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file not found")
    
    return FileResponse(
        str(thumbnail_path),
        media_type="image/jpeg",
        filename=f"thumbnail_{record_id}.jpg"
    )


@router.get("/{record_id}/stream")
async def stream_video(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Stream video file with Range request support (no authentication required for local access)"""
    # Get video record (no user check for local access)
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Extract video ID from URL
    video_id = extract_video_id(record.url)
    if not video_id:
        raise HTTPException(status_code=404, detail="Could not extract video ID from URL")
    
    # Find video file
    video_extensions = ['.mp4', '.webm', '.mkv']
    video_path = None
    
    for ext in video_extensions:
        potential_path = Path(settings.video_storage_dir) / f"{video_id}{ext}"
        if potential_path.exists():
            video_path = potential_path
            break
    
    if not video_path:
        # Try to find any file with the video ID
        for file in Path(settings.video_storage_dir).glob(f"{video_id}.*"):
            if file.suffix in video_extensions:
                video_path = file
                break
    
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    
    # Get file size
    file_size = video_path.stat().st_size
    if file_size == 0:
        raise HTTPException(status_code=404, detail="Video file is empty")

    # Handle Range requests for video seeking
    range_header = request.headers.get('range')

    if range_header:
        # Parse range header (e.g. "bytes=0-", "bytes=0-1023", "bytes=100-500")
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            end = min(end, file_size - 1)

            # Validate range
            if start > end or start >= file_size:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{file_size}"}
                )
            
            # Read chunk
            chunk_size = end - start + 1
            with open(video_path, 'rb') as f:
                f.seek(start)
                chunk = f.read(chunk_size)
            
            # Determine content type
            content_type = "video/mp4"
            if video_path.suffix == '.webm':
                content_type = "video/webm"
            elif video_path.suffix == '.mkv':
                content_type = "video/x-matroska"
            
            return Response(
                content=chunk,
                status_code=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(chunk_size),
                    "Content-Type": content_type,
                },
                media_type=content_type
            )
    
    # No Range header: return first chunk only (206) so browser gets metadata quickly
    # and can request more ranges as needed. Avoids sending entire file for long videos.
    INITIAL_CHUNK_BYTES = 2 * 1024 * 1024  # 2 MB
    start = 0
    end = min(INITIAL_CHUNK_BYTES - 1, file_size - 1) if file_size else 0
    chunk_size = end - start + 1

    content_type = "video/mp4"
    if video_path.suffix == '.webm':
        content_type = "video/webm"
    elif video_path.suffix == '.mkv':
        content_type = "video/x-matroska"

    with open(video_path, 'rb') as f:
        chunk = f.read(chunk_size)

    return Response(
        content=chunk,
        status_code=206,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": content_type,
        },
        media_type=content_type,
    )
