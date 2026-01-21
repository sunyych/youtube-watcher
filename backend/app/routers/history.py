"""History routes"""
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from urllib.parse import quote
from pathlib import Path
import re
import logging

from app.database import get_db
from app.models.database import VideoRecord, User
from app.routers.auth import get_current_user
from app.services.markdown_exporter import MarkdownExporter
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryItem(BaseModel):
    id: int
    url: str
    title: Optional[str]
    summary: Optional[str]
    language: Optional[str]
    status: str
    keywords: Optional[str]  # Comma-separated keywords
    created_at: datetime
    
    class Config:
        from_attributes = True


class HistoryDetail(HistoryItem):
    transcript: Optional[str]
    keywords: Optional[str]  # Comma-separated keywords
    progress: float
    completed_at: Optional[datetime]
    error_message: Optional[str]


@router.get("", response_model=List[HistoryItem])
async def get_history(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get video history"""
    records = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id
    ).order_by(desc(VideoRecord.created_at)).offset(skip).limit(limit).all()
    return records


@router.get("/count")
async def get_history_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get total count of video history"""
    count = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id
    ).count()
    return {"count": count}


@router.get("/search", response_model=List[HistoryItem])
async def search_history(
    q: str = Query(..., description="Search query"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Search video history by keywords, title, or URL"""
    if not q or not q.strip():
        # Return empty list if query is empty
        return []
    
    search_term = f"%{q.strip()}%"
    
    # Search in title, URL, keywords, and transcript (only for this user)
    # Handle NULL values properly - ilike on NULL returns NULL, so we need to handle it
    records = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        or_(
            and_(VideoRecord.title.isnot(None), VideoRecord.title.ilike(search_term)),
            VideoRecord.url.ilike(search_term),
            and_(VideoRecord.keywords.isnot(None), VideoRecord.keywords.ilike(search_term)),
            and_(VideoRecord.transcript.isnot(None), VideoRecord.transcript.ilike(search_term))
        )
    ).order_by(desc(VideoRecord.updated_at)).offset(skip).limit(limit).all()
    
    return records


@router.get("/search/count")
async def search_history_count(
    q: str = Query(..., description="Search query"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get total count of search results"""
    if not q or not q.strip():
        return {"count": 0}
    
    search_term = f"%{q.strip()}%"
    
    count = db.query(VideoRecord).filter(
        VideoRecord.user_id == user.id,
        or_(
            and_(VideoRecord.title.isnot(None), VideoRecord.title.ilike(search_term)),
            VideoRecord.url.ilike(search_term),
            and_(VideoRecord.keywords.isnot(None), VideoRecord.keywords.ilike(search_term)),
            and_(VideoRecord.transcript.isnot(None), VideoRecord.transcript.ilike(search_term))
        )
    ).count()
    
    return {"count": count}


@router.get("/{record_id}", response_model=HistoryDetail)
async def get_history_detail(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get video history detail"""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    return record


@router.get("/{record_id}/export")
async def export_markdown(
    record_id: int,
    include_timestamps: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Export video record as Markdown"""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Get segments if available (would need to store in DB or reconstruct)
    record_dict = {
        "title": record.title,
        "url": record.url,
        "summary": record.summary,
        "transcript": record.transcript,
        "language": record.language,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "segments": []  # Would need to store segments in DB
    }
    
    markdown = MarkdownExporter.export(record_dict, include_timestamps=include_timestamps)
    
    # Generate filename - preserve Chinese characters using RFC 5987 encoding
    title = record.title or "video"
    # Sanitize filename: keep alphanumeric, spaces, hyphens, underscores
    # Replace problematic filesystem characters but keep Chinese characters
    # Characters like : / \ ? * " < > | are problematic for filesystems
    problematic_chars = {':', '/', '\\', '?', '*', '"', '<', '>', '|', '：', '？', '！', '，', '。'}
    sanitized = "".join(c if c not in problematic_chars else '_' for c in title).strip()
    sanitized = sanitized.replace(' ', '_')[:100]  # Limit length but allow more for Chinese
    if not sanitized:  # If title was empty after sanitization, use default
        sanitized = "video"
    filename = f"{sanitized}_{record_id}.md"
    
    # Create ASCII fallback filename for compatibility (old browsers/systems)
    ascii_filename = "".join(c if c.isascii() and (c.isalnum() or c in (' ', '-', '_')) else '_' for c in title).rstrip()
    ascii_filename = ascii_filename.replace(' ', '_')[:50]
    if not ascii_filename:
        ascii_filename = "video"
    ascii_filename = f"{ascii_filename}_{record_id}.md"
    
    # Use RFC 5987 encoding for UTF-8 filenames
    # Format: filename="fallback"; filename*=UTF-8''encoded
    encoded_filename = quote(filename, safe='')
    content_disposition = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
    
    # Use bytes for content to avoid encoding issues
    content_bytes = markdown.encode('utf-8')
    
    # Create headers dict with proper encoding
    headers = {
        "Content-Disposition": content_disposition
    }
    
    return Response(
        content=content_bytes,
        media_type="text/markdown; charset=utf-8",
        headers=headers
    )


class UpdateHistoryRequest(BaseModel):
    transcript: Optional[str] = None
    keywords: Optional[str] = None  # Comma-separated keywords


@router.put("/{record_id}", response_model=HistoryDetail)
async def update_history(
    record_id: int,
    request: UpdateHistoryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Update video history transcript and keywords"""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Update transcript if provided
    if request.transcript is not None:
        record.transcript = request.transcript
        # Also update transcript file if it exists
        if record.transcript_file_path:
            from pathlib import Path
            transcript_path = Path(record.transcript_file_path)
            if transcript_path.exists():
                transcript_path.parent.mkdir(parents=True, exist_ok=True)
                with open(transcript_path, 'w', encoding='utf-8') as f:
                    f.write(request.transcript)
    
    # Update keywords if provided
    if request.keywords is not None:
        record.keywords = request.keywords
    
    # Update updated_at timestamp
    from datetime import datetime
    record.updated_at = datetime.now()
    
    db.commit()
    db.refresh(record)
    
    return record




@router.post("/{record_id}/generate-keywords", response_model=HistoryDetail)
async def generate_keywords(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Generate keywords for a video record using LLM"""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if not record.transcript or record.transcript.startswith("Transcription unavailable"):
        raise HTTPException(status_code=400, detail="Cannot generate keywords: transcript not available")
    
    try:
        llm_service = LLMService()
        keywords = await llm_service.generate_keywords(
            record.transcript,
            record.title or "",
            language=record.language or "中文"
        )
        
        if keywords:
            record.keywords = keywords
            from datetime import datetime
            record.updated_at = datetime.now()
            db.commit()
            db.refresh(record)
            return record
        else:
            raise HTTPException(status_code=500, detail="Failed to generate keywords")
    except Exception as e:
        logger.error(f"Error generating keywords: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate keywords: {str(e)}")


@router.delete("/{record_id}")
async def delete_history(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Delete a video record and associated files"""
    record = db.query(VideoRecord).filter(
        VideoRecord.id == record_id,
        VideoRecord.user_id == user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    try:
        # Delete associated files
        from app.config import settings
        
        video_storage_dir = Path(settings.video_storage_dir)
        
        # Try to find video files by extracting video ID from URL
        video_id = None
        if record.url:
            # Extract video ID from various YouTube URL formats
            patterns = [
                r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
                r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})'
            ]
            for pattern in patterns:
                match = re.search(pattern, record.url)
                if match:
                    video_id = match.group(1)
                    break
        
        if video_id:
            # Delete video, audio, and transcript files
            file_extensions = ['.mp4', '.webm', '.mkv', '.wav', '.txt']
            for ext in file_extensions:
                file_path = video_storage_dir / f"{video_id}{ext}"
                if file_path.exists():
                    try:
                        file_path.unlink()
                        logger.info(f"Deleted file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete file {file_path}: {e}")
        
        # Delete transcript file if path is stored
        if record.transcript_file_path:
            transcript_path = Path(record.transcript_file_path)
            if transcript_path.exists():
                try:
                    transcript_path.unlink()
                    logger.info(f"Deleted transcript file: {transcript_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete transcript file {transcript_path}: {e}")
        
        # Delete the database record
        db.delete(record)
        db.commit()
        
        logger.info(f"Deleted video record {record_id} for user {user.id}")
        return {"message": "Video record deleted successfully", "id": record_id}
        
    except Exception as e:
        logger.error(f"Error deleting video record {record_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete video record: {str(e)}")
