"""Add watch_position_seconds and watch_updated_at to video_records (idempotent)."""
from sqlalchemy import text


def upgrade(connection):
    # User's last watch position (seconds) for resume playback.
    connection.execute(
        text(
            "ALTER TABLE video_records "
            "ADD COLUMN IF NOT EXISTS watch_position_seconds REAL"
        )
    )
    connection.execute(
        text(
            "ALTER TABLE video_records "
            "ADD COLUMN IF NOT EXISTS watch_updated_at TIMESTAMPTZ"
        )
    )
