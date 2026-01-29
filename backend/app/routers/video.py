"""Video processing routes"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from pathlib import Path
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
from app.services.whisper_service import WhisperService
from app.services.llm_service import LLMService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["video"])

# Initialize services
video_downloader = VideoDownloader(settings.video_storage_dir)
audio_converter = AudioConverter(settings.video_storage_dir)

# Initialize Whisper service (will be initialized lazily or in lifespan)
whisper_service = None

def get_whisper_service():
    """Get or initialize Whisper service"""
    global whisper_service
    if whisper_service is None:
        try:
            whisper_service = WhisperService(
                model_size="medium",
                device=settings.acceleration if settings.acceleration != "mlx" else "cpu",
                compute_type=None
            )
            logger.info("Whisper service initialized successfully")
        except Exception as e:
            logger.warning(f"Whisper service initialization failed: {e}. Transcription will not be available.")
            whisper_service = None
    return whisper_service

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
            error_message=existing_record.error_message
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
        error_message=record.error_message
    )


@router.get("/status/{record_id}", response_model=VideoStatusResponse)
async def get_video_status(
    record_id: int,
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
    
    # Update queue position if pending
    if record.status == VideoStatus.PENDING:
        pending_count = db.query(VideoRecord).filter(
            VideoRecord.status == VideoStatus.PENDING,
            VideoRecord.user_id == user.id,
            VideoRecord.id < record.id
        ).count()
        record.queue_position = pending_count + 1
        db.commit()
    
    return VideoStatusResponse(
        id=record.id,
        url=record.url,
        title=record.title,
        status=record.status.value,
        progress=record.progress,
        queue_position=record.queue_position,
        error_message=record.error_message
    )


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
        error_message=record.error_message
    )


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
    
    # Handle Range requests for video seeking
    range_header = request.headers.get('range')
    
    if range_header:
        # Parse range header
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            
            # Validate range
            if start >= file_size or end >= file_size or start > end:
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
    
    # Return full file if no range request
    content_type = "video/mp4"
    if video_path.suffix == '.webm':
        content_type = "video/webm"
    elif video_path.suffix == '.mkv':
        content_type = "video/x-matroska"
    
    return FileResponse(
        path=str(video_path),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
    )
