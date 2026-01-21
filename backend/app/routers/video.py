"""Video processing routes"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from pathlib import Path
import json
import asyncio
import logging

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
