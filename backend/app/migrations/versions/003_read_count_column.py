"""Add read_count to video_records (idempotent)."""
from sqlalchemy import text


def upgrade(connection):
    # Track how many times a record has been opened/read.
    connection.execute(
        text(
            "ALTER TABLE video_records "
            "ADD COLUMN IF NOT EXISTS read_count INTEGER NOT NULL DEFAULT 0"
        )
    )

