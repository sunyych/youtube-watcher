"""
Reset completed records that have no summary so the queue will re-run summarization.

Sets status to SUMMARIZING so the worker will only run the summary step (and keywords).
"""

from __future__ import annotations

from sqlalchemy import or_

from app.database import init_db, SessionLocal
from app.models.database import VideoRecord, VideoStatus


def main():
    init_db()
    db = SessionLocal()
    try:
        # Completed records with no summary (null or empty)
        q = db.query(VideoRecord).filter(
            VideoRecord.status == VideoStatus.COMPLETED,
            or_(
                VideoRecord.summary.is_(None),
                VideoRecord.summary == "",
            ),
        )
        records = q.order_by(VideoRecord.id.asc()).all()

        for r in records:
            r.status = VideoStatus.SUMMARIZING
            r.progress = 95.0

        db.commit()
        print(f"Re-queued {len(records)} record(s) for re-summarization.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
