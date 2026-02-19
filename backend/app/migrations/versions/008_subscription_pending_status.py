"""Add status and allow nullable channel_id for async subscription resolution by queue."""
from sqlalchemy import text


def upgrade(connection):
    # Allow channel_id to be NULL for pending subscriptions
    connection.execute(text(
        "ALTER TABLE channel_subscriptions ALTER COLUMN channel_id DROP NOT NULL"
    ))
    # Add status: 'pending' = recorded, queue will resolve; 'resolved' = channel_id set
    connection.execute(text("""
        ALTER TABLE channel_subscriptions
        ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'resolved'
    """))
    connection.execute(text(
        "UPDATE channel_subscriptions SET status = 'resolved' WHERE status IS NULL"
    ))
    # Drop old unique constraint (user_id, channel_id) — it was created as a constraint, not a standalone index
    connection.execute(text(
        "ALTER TABLE channel_subscriptions DROP CONSTRAINT IF EXISTS uq_channel_subscriptions_user_channel"
    ))
    # One resolved subscription per (user_id, channel_id)
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_subscriptions_user_channel_resolved
        ON channel_subscriptions (user_id, channel_id)
        WHERE channel_id IS NOT NULL
    """))
    # One pending subscription per (user_id, channel_url)
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_subscriptions_user_url_pending
        ON channel_subscriptions (user_id, channel_url)
        WHERE channel_id IS NULL
    """))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_channel_subscriptions_status "
        "ON channel_subscriptions (status)"
    ))


def downgrade(connection):
    connection.execute(text("DROP INDEX IF EXISTS ix_channel_subscriptions_status"))
    connection.execute(text("DROP INDEX IF EXISTS uq_channel_subscriptions_user_url_pending"))
    connection.execute(text("DROP INDEX IF EXISTS uq_channel_subscriptions_user_channel_resolved"))
    connection.execute(text("""
        DELETE FROM channel_subscriptions WHERE channel_id IS NULL
    """))
    connection.execute(text(
        "ALTER TABLE channel_subscriptions ALTER COLUMN channel_id SET NOT NULL"
    ))
    connection.execute(text(
        "ALTER TABLE channel_subscriptions DROP COLUMN IF EXISTS status"
    ))
    connection.execute(text(
        "ALTER TABLE channel_subscriptions "
        "ADD CONSTRAINT uq_channel_subscriptions_user_channel UNIQUE (user_id, channel_id)"
    ))
