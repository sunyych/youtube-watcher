"""Add common video metadata columns (idempotent)."""
from sqlalchemy import text


def upgrade(connection):
    # Basic identifiers / publisher info
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS source_video_id VARCHAR"))
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS channel_id VARCHAR"))
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS channel_title VARCHAR"))
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS uploader_id VARCHAR"))
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS uploader VARCHAR"))

    # Metrics (default 0 so sorting is stable)
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS view_count BIGINT NOT NULL DEFAULT 0"))
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS like_count BIGINT NOT NULL DEFAULT 0"))
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS duration_seconds INTEGER NOT NULL DEFAULT 0"))

    # Download timing
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS downloaded_at TIMESTAMPTZ"))

    # Original remote thumbnail URL (we also store generated local thumbnail_path separately)
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS thumbnail_url TEXT"))

    # Helpful indexes for future sorting/filtering
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_video_records_source_video_id ON video_records (source_video_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_video_records_channel_title ON video_records (channel_title)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_video_records_view_count ON video_records (view_count)"))

