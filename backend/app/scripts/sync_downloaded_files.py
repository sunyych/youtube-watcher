"""
Sync database status with already-downloaded video files on disk.

This is useful when many records are PENDING/FAILED but the corresponding mp4/webm/mkv
files already exist under VIDEO_STORAGE_DIR.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import datetime, timezone

from app.database import init_db, SessionLocal
from app.models.database import VideoRecord, VideoStatus
from app.config import settings


def extract_video_id(url: str) -> str | None:
    if not url:
        return None
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def find_existing(storage_dir: str, url: str) -> Path | None:
    vid = extract_video_id(url)
    if not vid:
        return None
    base = Path(storage_dir)
    for ext in [".mp4", ".mkv", ".webm"]:
        p = base / f"{vid}{ext}"
        if p.exists():
            return p
    for f in base.glob(f"{vid}.*"):
        if f.suffix.lower() in [".mp4", ".mkv", ".webm"]:
            return f
    return None


def main():
    init_db()
    db = SessionLocal()
    try:
        storage_dir = os.getenv("VIDEO_STORAGE_DIR") or settings.video_storage_dir
        storage_dir = str(storage_dir)

        # Optionally limit to a user
        only_user_id = os.getenv("SYNC_USER_ID")
        only_user_id_int = int(only_user_id) if only_user_id else None

        q = db.query(VideoRecord)
        if only_user_id_int is not None:
            q = q.filter(VideoRecord.user_id == only_user_id_int)

        # Skip completed; we only want to correct "not downloaded" statuses.
        q = q.filter(VideoRecord.status.in_([VideoStatus.PENDING, VideoStatus.FAILED, VideoStatus.DOWNLOADING]))

        records = q.order_by(VideoRecord.id.asc()).all()
        updated = 0

        now = datetime.now(timezone.utc)
        for r in records:
            p = find_existing(storage_dir, r.url)
            if not p:
                continue

            # Mark as downloaded stage complete
            r.downloaded_at = r.downloaded_at or now
            r.progress = max(float(r.progress or 0.0), 25.0)
            r.error_message = None

            # If it was completed previously, leave it. Otherwise move forward.
            if r.status != VideoStatus.COMPLETED:
                r.status = VideoStatus.CONVERTING

            updated += 1

        db.commit()
        print(f"Synced downloaded files. Updated records: {updated}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

