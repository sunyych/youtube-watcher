"""
Mark failed videos whose error_message indicates member-only / no membership
as unavailable so they are no longer shown in the failed list.

ALTER TYPE ADD VALUE in PostgreSQL cannot run inside a transaction (or the new
value is not visible until commit). We run it in autocommit, then UPDATE in a
separate connection.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.database import init_db, engine
from app.services.video_downloader import looks_like_membership_only_error

logger = logging.getLogger(__name__)


def _get_status_enum_type_and_labels(conn) -> tuple[str | None, list[str]]:
    """Return (enum_type_name, list of labels) for video_records.status. type is None if column is not enum."""
    # Get the actual type name of the status column (might be video_status or videostatus etc.)
    r = conn.execute(text("""
        SELECT t.typname
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_type t ON a.atttypid = t.oid
        WHERE c.relname = 'video_records' AND a.attname = 'status' AND NOT a.attisdropped
    """)).fetchone()
    if not r:
        return None, []
    type_name = r[0]
    rows = conn.execute(text("""
        SELECT e.enumlabel
        FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = :tn
        ORDER BY e.enumsortorder
    """), {"tn": type_name}).fetchall()
    return type_name, [row[0] for row in rows]


def _add_enum_value_autocommit(type_name: str, value: str) -> None:
    """Run ALTER TYPE ... ADD VALUE in autocommit so it takes effect."""
    # type_name and value come from DB / fixed literal; safe to embed
    with engine.connect() as conn:
        conn_autocommit = conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn_autocommit.execute(text(f'ALTER TYPE "{type_name}" ADD VALUE \'{value}\''))
        except ProgrammingError as e:
            if "already exists" not in str(e).lower():
                raise


def main():
    init_db()

    with engine.connect() as conn1:
        type_name, labels = _get_status_enum_type_and_labels(conn1)
    has_lower = "unavailable" in labels
    has_upper = "UNAVAILABLE" in labels

    if type_name and not has_lower and not has_upper:
        _add_enum_value_autocommit(type_name, "unavailable")
        target_status = "unavailable"
    elif has_lower:
        target_status = "unavailable"
    elif has_upper:
        target_status = "UNAVAILABLE"
    else:
        # Column might be VARCHAR; use lowercase
        target_status = "unavailable"

    with engine.connect() as conn2:
        rows = conn2.execute(text("""
            SELECT id, error_message FROM video_records
            WHERE status::text IN ('failed', 'FAILED')
            ORDER BY id ASC
        """)).fetchall()

        ids = [r[0] for r in rows if r[1] and looks_like_membership_only_error(r[1])]
        if not ids:
            print("Marked 0 failed record(s) as unavailable (member-only).")
            return

        conn2.execute(
            text("UPDATE video_records SET status = :st, updated_at = NOW() WHERE id = ANY(:ids)"),
            {"st": target_status, "ids": ids},
        )
        conn2.commit()
        print(f"Marked {len(ids)} failed record(s) as unavailable (member-only).")


if __name__ == "__main__":
    main()
