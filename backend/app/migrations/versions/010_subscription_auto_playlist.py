"""Add auto_playlist_id to channel_subscriptions for auto-adding new videos to a playlist."""
from sqlalchemy import text


def upgrade(connection):
    connection.execute(text(
        "ALTER TABLE channel_subscriptions "
        "ADD COLUMN IF NOT EXISTS auto_playlist_id INTEGER REFERENCES playlists(id)"
    ))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_channel_subscriptions_auto_playlist_id "
        "ON channel_subscriptions (auto_playlist_id)"
    ))


def downgrade(connection):
    connection.execute(text("DROP INDEX IF EXISTS ix_channel_subscriptions_auto_playlist_id"))
    connection.execute(text("ALTER TABLE channel_subscriptions DROP COLUMN IF EXISTS auto_playlist_id"))
