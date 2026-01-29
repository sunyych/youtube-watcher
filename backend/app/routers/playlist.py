"""Playlist routes"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import re
import logging

from app.database import get_db
from app.models.database import Playlist, PlaylistItem, User, VideoRecord
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playlist", tags=["playlist"])


def extract_tags_from_title(title: str) -> List[str]:
    """Extract tags from video title"""
    if not title:
        return []
    
    tags = []
    
    # Common patterns for tags in YouTube titles
    # Pattern 1: [Tag] or 【Tag】format
    bracket_tags = re.findall(r'[\[【]([^\]]+)[\]】]', title)
    tags.extend(bracket_tags)
    
    # Pattern 2: #Tag format
    hashtag_tags = re.findall(r'#(\w+)', title)
    tags.extend(hashtag_tags)
    
    # Pattern 3: Extract key words (nouns, adjectives)
    # Remove common stop words and extract meaningful words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now'}
    
    # Extract words (2+ characters, alphanumeric)
    words = re.findall(r'\b[a-zA-Z]{2,}\b', title.lower())
    meaningful_words = [w for w in words if w not in stop_words and len(w) >= 2]
    
    # Take top 3-5 meaningful words as tags
    if meaningful_words:
        # Remove duplicates and take unique words
        unique_words = list(dict.fromkeys(meaningful_words))[:5]
        tags.extend(unique_words)
    
    # Clean and normalize tags
    cleaned_tags = []
    for tag in tags:
        tag = tag.strip().lower()
        if tag and len(tag) >= 2 and tag not in cleaned_tags:
            cleaned_tags.append(tag)
    
    return cleaned_tags[:10]  # Limit to 10 tags


def add_tags_to_video(video: VideoRecord, new_tags: List[str], db: Session):
    """Add tags to video keywords field"""
    if not new_tags:
        return
    
    # Get existing keywords
    existing_keywords = []
    if video.keywords:
        existing_keywords = [k.strip().lower() for k in video.keywords.split(',') if k.strip()]
    
    # Merge new tags with existing keywords
    all_keywords = existing_keywords.copy()
    for tag in new_tags:
        tag_lower = tag.strip().lower()
        if tag_lower and tag_lower not in all_keywords:
            all_keywords.append(tag_lower)
    
    # Update keywords
    if all_keywords:
        video.keywords = ','.join(all_keywords)
        from datetime import datetime
        video.updated_at = datetime.now()
        db.commit()
        logger.info(f"Added tags to video {video.id}: {', '.join(new_tags)}")


class PlaylistResponse(BaseModel):
    id: int
    name: str
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class PlaylistItemResponse(BaseModel):
    id: int
    playlist_id: int
    video_record_id: int
    position: int
    created_at: datetime
    
    # Video info
    title: Optional[str]
    url: str
    status: str
    progress: float

    class Config:
        from_attributes = True


class AddItemRequest(BaseModel):
    video_record_id: int


class UpdateItemRequest(BaseModel):
    position: int


class CreatePlaylistRequest(BaseModel):
    name: str


class UpdatePlaylistRequest(BaseModel):
    name: str


@router.get("", response_model=PlaylistResponse)
async def get_playlist(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get current user's playlist (create if doesn't exist)"""
    playlist = db.query(Playlist).filter(Playlist.user_id == user.id).first()
    
    if not playlist:
        # Create default playlist
        playlist = Playlist(
            user_id=user.id,
            name="默认播放列表"
        )
        db.add(playlist)
        db.commit()
        db.refresh(playlist)
    
    return playlist


@router.get("/list", response_model=List[PlaylistResponse])
async def list_playlists(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all playlists for current user (create default if none)"""
    playlists = db.query(Playlist).filter(Playlist.user_id == user.id).order_by(Playlist.created_at).all()

    if not playlists:
        # Create default playlist
        default_playlist = Playlist(
            user_id=user.id,
            name="默认播放列表",
        )
        db.add(default_playlist)
        db.commit()
        db.refresh(default_playlist)
        playlists = [default_playlist]

    return playlists


@router.post("", response_model=PlaylistResponse)
async def create_playlist(
    request: CreatePlaylistRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new playlist for current user"""
    name = request.name.strip() or "新建播放列表"

    playlist = Playlist(
        user_id=user.id,
        name=name,
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


@router.put("/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    playlist_id: int,
    request: UpdatePlaylistRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update playlist (e.g., rename)"""
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == user.id,
    ).first()

    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    name = request.name.strip()
    if name:
        playlist.name = name
    db.commit()
    db.refresh(playlist)
    return playlist


@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a playlist and all its items"""
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == user.id,
    ).first()

    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    db.delete(playlist)
    db.commit()

    return {"message": "Playlist deleted"}


@router.get("/items", response_model=List[PlaylistItemResponse])
async def get_playlist_items(
    playlist_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get all items in a playlist (or default playlist if not specified)"""
    if playlist_id is not None:
        playlist = db.query(Playlist).filter(
            Playlist.id == playlist_id,
            Playlist.user_id == user.id,
        ).first()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
    else:
        playlist = db.query(Playlist).filter(Playlist.user_id == user.id).first()
        if not playlist:
            return []
    
    # Get playlist items with video info, ordered by position
    items = db.query(PlaylistItem, VideoRecord).filter(
        PlaylistItem.playlist_id == playlist.id
    ).join(
        VideoRecord, PlaylistItem.video_record_id == VideoRecord.id
    ).order_by(PlaylistItem.position).all()
    
    # Build response objects
    result = []
    for item, video in items:
        result.append(PlaylistItemResponse(
            id=item.id,
            playlist_id=item.playlist_id,
            video_record_id=item.video_record_id,
            position=item.position,
            created_at=item.created_at,
            title=video.title,
            url=video.url,
            status=video.status.value,
            progress=video.progress
        ))
    
    return result


@router.post("/items", response_model=PlaylistItemResponse)
async def add_item(
    request: AddItemRequest,
    playlist_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Add video to a playlist (or default playlist if not specified)"""
    # Check if video exists and belongs to user
    video = db.query(VideoRecord).filter(
        VideoRecord.id == request.video_record_id,
        VideoRecord.user_id == user.id
    ).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Get or create playlist
    if playlist_id is not None:
        playlist = db.query(Playlist).filter(
            Playlist.id == playlist_id,
            Playlist.user_id == user.id,
        ).first()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
    else:
        playlist = db.query(Playlist).filter(Playlist.user_id == user.id).first()
        if not playlist:
            playlist = Playlist(
                user_id=user.id,
                name="默认播放列表"
            )
            db.add(playlist)
            db.commit()
            db.refresh(playlist)
    
    # Check if item already exists
    existing_item = db.query(PlaylistItem).filter(
        PlaylistItem.playlist_id == playlist.id,
        PlaylistItem.video_record_id == request.video_record_id
    ).first()
    
    if existing_item:
        raise HTTPException(status_code=400, detail="Video already in playlist")
    
    # Get next position
    max_position = db.query(func.max(PlaylistItem.position)).filter(
        PlaylistItem.playlist_id == playlist.id
    ).scalar() or 0
    
    item = PlaylistItem(
        playlist_id=playlist.id,
        video_record_id=request.video_record_id,
        position=max_position + 1
    )
    
    db.add(item)
    db.commit()
    db.refresh(item)
    
    # Get video info and return response
    video = db.query(VideoRecord).filter(VideoRecord.id == request.video_record_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Extract tags from title and add to video
    if video.title:
        tags = extract_tags_from_title(video.title)
        if tags:
            add_tags_to_video(video, tags, db)
            # Refresh video to get updated keywords
            db.refresh(video)
    
    return PlaylistItemResponse(
        id=item.id,
        playlist_id=item.playlist_id,
        video_record_id=item.video_record_id,
        position=item.position,
        created_at=item.created_at,
        title=video.title,
        url=video.url,
        status=video.status.value,
        progress=video.progress
    )


@router.put("/items/{item_id}", response_model=PlaylistItemResponse)
async def update_item(
    item_id: int,
    request: UpdateItemRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Update playlist item (e.g., change position)"""
    # Get item and verify it belongs to user's playlist
    item = db.query(PlaylistItem).join(
        Playlist, PlaylistItem.playlist_id == Playlist.id
    ).filter(
        PlaylistItem.id == item_id,
        Playlist.user_id == user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Playlist item not found")
    
    item.position = request.position
    db.commit()
    db.refresh(item)
    
    # Get video info and return response
    video = db.query(VideoRecord).filter(VideoRecord.id == item.video_record_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return PlaylistItemResponse(
        id=item.id,
        playlist_id=item.playlist_id,
        video_record_id=item.video_record_id,
        position=item.position,
        created_at=item.created_at,
        title=video.title,
        url=video.url,
        status=video.status.value,
        progress=video.progress
    )


@router.delete("/items/{item_id}")
async def remove_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Remove item from playlist"""
    # Get item and verify it belongs to user's playlist
    item = db.query(PlaylistItem).join(
        Playlist, PlaylistItem.playlist_id == Playlist.id
    ).filter(
        PlaylistItem.id == item_id,
        Playlist.user_id == user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Playlist item not found")
    
    db.delete(item)
    db.commit()
    
    return {"message": "Item removed from playlist"}


@router.delete("/items")
async def clear_playlist(
    playlist_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Clear all items from a playlist (or default playlist if not specified)"""
    if playlist_id is not None:
        playlist = db.query(Playlist).filter(
            Playlist.id == playlist_id,
            Playlist.user_id == user.id,
        ).first()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
    else:
        playlist = db.query(Playlist).filter(Playlist.user_id == user.id).first()
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Delete all items
    db.query(PlaylistItem).filter(PlaylistItem.playlist_id == playlist.id).delete()
    db.commit()
    
    return {"message": "Playlist cleared"}