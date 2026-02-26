"""Channel subscription routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel, HttpUrl

from app.database import get_db
from app.models.database import User, ChannelSubscription, VideoRecord, Playlist
from app.routers.auth import get_current_user
from app.routers.history import HistoryItem
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


class SubscribeRequest(BaseModel):
    channel_url: HttpUrl


class UpdateSubscriptionRequest(BaseModel):
    channel_url: Optional[HttpUrl] = None
    auto_playlist_id: Optional[int] = None


class SubscriptionItem(BaseModel):
    id: int
    channel_id: Optional[str]
    channel_url: str
    channel_title: Optional[str]
    status: str  # 'pending' | 'resolved'
    created_at: str
    last_check_at: Optional[str]
    auto_playlist_id: Optional[int] = None

    class Config:
        from_attributes = True


def _subscription_to_item(sub: ChannelSubscription) -> SubscriptionItem:
    return SubscriptionItem(
        id=sub.id,
        channel_id=sub.channel_id,
        channel_url=sub.channel_url,
        channel_title=sub.channel_title,
        status=sub.status or "resolved",
        created_at=sub.created_at.isoformat() if sub.created_at else "",
        last_check_at=sub.last_check_at.isoformat() if sub.last_check_at else None,
        auto_playlist_id=getattr(sub, "auto_playlist_id", None),
    )


@router.post("", response_model=SubscriptionItem)
async def subscribe(
    request: SubscribeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Record a channel subscription. Resolution (channel_id/title) runs in the queue; returns immediately with status=pending."""
    url_str = str(request.channel_url).strip()
    existing = (
        db.query(ChannelSubscription)
        .filter(
            ChannelSubscription.user_id == user.id,
            ChannelSubscription.channel_url == url_str,
        )
        .first()
    )
    if existing:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=_subscription_to_item(existing).model_dump(),
        )
    sub = ChannelSubscription(
        user_id=user.id,
        channel_url=url_str,
        status="pending",
        channel_id=None,
        channel_title=None,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    logger.info("User %s added subscription (pending) for URL %s", user.id, url_str)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_subscription_to_item(sub).model_dump(),
    )


@router.get("", response_model=List[SubscriptionItem])
async def list_subscriptions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List current user's channel subscriptions."""
    subs = (
        db.query(ChannelSubscription)
        .filter(ChannelSubscription.user_id == user.id)
        .order_by(ChannelSubscription.created_at.desc())
        .all()
    )
    return [_subscription_to_item(s) for s in subs]


@router.get("/{subscription_id}/videos", response_model=List[HistoryItem])
async def get_subscription_videos(
    subscription_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List videos belonging to this subscription (channel)."""
    sub = (
        db.query(ChannelSubscription)
        .filter(
            ChannelSubscription.id == subscription_id,
            ChannelSubscription.user_id == user.id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    records = (
        db.query(VideoRecord)
        .filter(
            VideoRecord.user_id == user.id,
            VideoRecord.subscription_id == subscription_id,
        )
        .order_by(desc(VideoRecord.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return records


@router.patch("/{subscription_id}", response_model=SubscriptionItem)
async def update_subscription(
    subscription_id: int,
    request: UpdateSubscriptionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update subscription URL; resolution runs in the queue. Sets status=pending until queue resolves."""
    sub = (
        db.query(ChannelSubscription)
        .filter(
            ChannelSubscription.id == subscription_id,
            ChannelSubscription.user_id == user.id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    if request.channel_url is not None:
        url_str = str(request.channel_url).strip()
        sub.channel_url = url_str
        sub.status = "pending"
        sub.channel_id = None
        sub.channel_title = None
    if "auto_playlist_id" in request.model_dump(exclude_unset=True):
        if request.auto_playlist_id is None:
            sub.auto_playlist_id = None
        else:
            playlist = db.query(Playlist).filter(
                Playlist.id == request.auto_playlist_id,
                Playlist.user_id == user.id,
            ).first()
            if not playlist:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
            sub.auto_playlist_id = playlist.id
    db.commit()
    db.refresh(sub)
    logger.info("User %s updated subscription %s (pending resolve)", user.id, subscription_id)
    return _subscription_to_item(sub)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    subscription_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove a channel subscription. Existing downloaded videos are kept."""
    sub = (
        db.query(ChannelSubscription)
        .filter(
            ChannelSubscription.id == subscription_id,
            ChannelSubscription.user_id == user.id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    db.delete(sub)
    db.commit()
    logger.info("User %s unsubscribed (id=%s)", user.id, subscription_id)
