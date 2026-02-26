"""
Reset records that have no transcript (or 'Transcription unavailable') so the queue
will re-run conversion + transcription.

Sets status to CONVERTING and clears transcript/transcript_file_path so the worker
resumes from conversion and then transcribes again.
"""

from __future__ import annotations

from sqlalchemy import or_

from app.database import init_db, SessionLocal
from app.models.database import VideoRecord, VideoStatus


def main():
    init_db()
    db = SessionLocal()
    try:
        # Records that have no transcript or placeholder "Transcription unavailable"
        q = db.query(VideoRecord).filter(
            VideoRecord.status == VideoStatus.COMPLETED,
            or_(
                VideoRecord.transcript.is_(None),
                VideoRecord.transcript == "",
                VideoRecord.transcript.startswith("Transcription unavailable"),
            ),
        )
        records = q.order_by(VideoRecord.id.asc()).all()

        for r in records:
            r.status = VideoStatus.CONVERTING
            r.transcript = None
            r.transcript_file_path = None
            r.summary = None  # will be regenerated after transcript
            r.progress = 25.0

        db.commit()
        print(f"Re-queued {len(records)} record(s) for re-transcription.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
