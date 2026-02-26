"""
Refresh title (and optional metadata) for video records that have no title.

Uses yt-dlp extract_info(url, download=False) to fetch metadata only.
Member-only videos are skipped (not updated); use mark-membership-unavailable to mark them.
"""

from __future__ import annotations

import yt_dlp

from sqlalchemy import or_, cast, String

from app.database import init_db, SessionLocal
from app.models.database import VideoRecord
from app.services.video_downloader import looks_like_membership_only_error


def main():
    init_db()
    db = SessionLocal()
    try:
        # Records with URL but no title (or empty title). Exclude status='unavailable'
        # (stored lowercase in DB) so ORM does not hit LookupError when loading.
        q = db.query(VideoRecord).filter(
            VideoRecord.url.isnot(None),
            VideoRecord.url != "",
            or_(VideoRecord.title.is_(None), VideoRecord.title == ""),
            cast(VideoRecord.status, String) != "unavailable",
        )
        records = q.order_by(VideoRecord.id.asc()).all()
        updated = 0
        skipped_member = 0

        BATCH_COMMIT = 50  # commit every N updates to avoid long transaction / connection drop
        opts = {"quiet": True, "no_warnings": True, "extract_flat": False}
        for r in records:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(r.url, download=False)
                if not info:
                    continue
                title = info.get("title") or ""
                if title:
                    r.title = title
                    if info.get("duration"):
                        r.duration_seconds = int(info["duration"])
                    if info.get("channel_id"):
                        r.channel_id = info["channel_id"]
                    if info.get("channel") or info.get("uploader"):
                        r.channel_title = info.get("channel") or info.get("uploader")
                    updated += 1
                    if updated % BATCH_COMMIT == 0:
                        db.commit()
            except Exception as e:
                msg = str(e)
                if looks_like_membership_only_error(msg):
                    skipped_member += 1
                    # Skip: do not update; use make mark-membership-unavailable to mark as unavailable
                # else leave record unchanged (e.g. network error)

        db.commit()
        print(f"Refreshed titles: {updated}. Skipped (member-only): {skipped_member}. Total processed: {len(records)}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
