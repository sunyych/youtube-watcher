"""Add 'UNAVAILABLE' to video_status enum (member-only / cannot download).
   DB enum uses Python enum names (PENDING, FAILED, etc.), so we add UNAVAILABLE."""
from sqlalchemy import text


def upgrade(connection):
    # PostgreSQL: add enum value if not present (safe to run multiple times)
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
    # PostgreSQL does not support removing enum values easily; leave 'unavailable' in place.
    pass
