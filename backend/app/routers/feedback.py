"""Feedback routes: submit user feedback, stored as JSON (+ optional screenshot) per submission."""
import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.models.database import User
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackSubmitRequest(BaseModel):
    page: str
    display_description: Optional[str] = None
    comment: str
    screenshot_base64: Optional[str] = None


class FeedbackSubmitResponse(BaseModel):
    id: str


class FeedbackListItem(BaseModel):
    id: str
    created_at: str


def _ensure_feedback_dir() -> Path:
    path = Path(settings.feedback_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_id() -> str:
    """Unique id for this feedback (filesystem-safe)."""
    return uuid.uuid4().hex


@router.post("", response_model=FeedbackSubmitResponse)
async def submit_feedback(
    request: FeedbackSubmitRequest,
    user: User = Depends(get_current_user),
):
    """Submit user feedback. Saves one JSON file per submission; optional PNG if screenshot provided."""
    feedback_dir = _ensure_feedback_dir()
    fid = _safe_id()
    created_at = datetime.now(timezone.utc).isoformat()

    screenshot_path: Optional[str] = None
    if request.screenshot_base64:
        try:
            raw = base64.b64decode(request.screenshot_base64, validate=True)
            png_path = feedback_dir / f"{fid}.png"
            png_path.write_bytes(raw)
            screenshot_path = f"{fid}.png"
        except Exception as e:
            logger.warning("Failed to save feedback screenshot: %s", e)

    payload = {
        "id": fid,
        "user_id": user.id,
        "username": user.username,
        "page": request.page,
        "display_description": request.display_description,
        "comment": request.comment,
        "screenshot_path": screenshot_path,
        "created_at": created_at,
    }
    json_path = feedback_dir / f"{fid}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return FeedbackSubmitResponse(id=fid)


@router.get("", response_model=List[FeedbackListItem])
async def list_feedback(user: User = Depends(get_current_user)):
    """List all feedback entries (id and created_at). For use by local script or admin."""
    feedback_dir = Path(settings.feedback_storage_dir)
    if not feedback_dir.exists():
        return []
    items: List[FeedbackListItem] = []
    for json_path in sorted(feedback_dir.glob("*.json")):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items.append(FeedbackListItem(
                id=data.get("id", json_path.stem),
                created_at=data.get("created_at", ""),
            ))
        except Exception:
            continue
    return items


@router.get("/{feedback_id}")
async def get_feedback(feedback_id: str, user: User = Depends(get_current_user)) -> Any:
    """Get a single feedback JSON by id. For use by local script to fetch remotely."""
    if not feedback_id or ".." in feedback_id or "/" in feedback_id or "\\" in feedback_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid feedback id")
    feedback_dir = Path(settings.feedback_storage_dir)
    json_path = feedback_dir / f"{feedback_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)
