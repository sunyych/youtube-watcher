"""Add missing columns to video_records (idempotent)."""
from sqlalchemy import text


def upgrade(connection):
    # Ensure video_status enum exists (PostgreSQL)
    connection.execute(text("""
        DO $$ BEGIN
            CREATE TYPE video_status AS ENUM (
                'pending', 'downloading', 'converting', 'transcribing',
                'summarizing', 'completed', 'failed'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """))
    # Add columns if not exist (PostgreSQL 9.5+)
    for col, sql in [
        ("user_id", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)"),
        ("transcript_file_path", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS transcript_file_path VARCHAR"),
        ("keywords", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS keywords TEXT"),
        ("queue_position", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS queue_position INTEGER"),
        ("error_message", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS error_message TEXT"),
        ("upload_date", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS upload_date TIMESTAMPTZ"),
        ("thumbnail_path", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS thumbnail_path VARCHAR"),
        ("updated_at", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"),
        ("completed_at", "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"),
    ]:
        connection.execute(text(sql))
    # Ensure status/progress exist (older schemas might not have them)
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending'"))
    connection.execute(text("ALTER TABLE video_records ADD COLUMN IF NOT EXISTS progress DOUBLE PRECISION DEFAULT 0.0"))
    # Create index on user_id if missing
    connection.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_video_records_user_id ON video_records (user_id)
    """))
