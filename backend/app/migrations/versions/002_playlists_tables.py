"""Create playlists and playlist_items tables if not exist."""
from sqlalchemy import text


def upgrade(connection):
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS playlists (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name VARCHAR NOT NULL DEFAULT '默认播放列表',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_playlists_user_id ON playlists (user_id)"))

    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS playlist_items (
            id SERIAL PRIMARY KEY,
            playlist_id INTEGER NOT NULL REFERENCES playlists(id),
            video_record_id INTEGER NOT NULL REFERENCES video_records(id),
            position INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_playlist_items_playlist_id ON playlist_items (playlist_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_playlist_items_video_record_id ON playlist_items (video_record_id)"))
