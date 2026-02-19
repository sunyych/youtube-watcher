"""Create channel_subscriptions table and add subscription_id to video_records."""
from sqlalchemy import text


def upgrade(connection):
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS channel_subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            channel_id VARCHAR NOT NULL,
            channel_url VARCHAR NOT NULL,
            channel_title VARCHAR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_check_at TIMESTAMPTZ
        )
    """))
    connection.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_subscriptions_user_channel "
        "ON channel_subscriptions (user_id, channel_id)"
    ))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_channel_subscriptions_user_id ON channel_subscriptions (user_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_channel_subscriptions_channel_id ON channel_subscriptions (channel_id)"))

    connection.execute(text(
        "ALTER TABLE video_records "
        "ADD COLUMN IF NOT EXISTS subscription_id INTEGER REFERENCES channel_subscriptions(id)"
    ))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_video_records_subscription_id ON video_records (subscription_id)"
    ))
