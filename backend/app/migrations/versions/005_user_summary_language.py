"""Add user summary_language column (idempotent)."""
from sqlalchemy import text


def upgrade(connection):
    connection.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS summary_language VARCHAR DEFAULT '中文'"
    ))
