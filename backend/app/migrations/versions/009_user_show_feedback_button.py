"""Add user show_feedback_button column (idempotent)."""
from sqlalchemy import text


def upgrade(connection):
    connection.execute(text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_feedback_button BOOLEAN NOT NULL DEFAULT true"
    ))
