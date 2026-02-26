"""Ensure video_status has 'UNAVAILABLE' (for DBs where 011 added 'unavailable' or enum uses names)."""
from sqlalchemy import text


def upgrade(connection):
    connection.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'video_status' AND e.enumlabel = 'UNAVAILABLE'
            ) THEN
                ALTER TYPE video_status ADD VALUE 'UNAVAILABLE';
            END IF;
        END $$;
    """))


def downgrade(connection):
    pass
