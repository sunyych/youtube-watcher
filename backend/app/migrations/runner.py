"""Migration runner: applies pending migrations on startup."""
from pathlib import Path
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "versions"


def get_applied_version(connection) -> int:
    """Return the highest applied migration version (0 if none)."""
    result = connection.execute(
        text("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
    )
    row = result.fetchone()
    return int(row[0]) if row else 0


def run_migrations(engine):
    """
    Run all pending migrations in order.
    Call this at app startup (e.g. from init_db) after create_all.
    """
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.commit()

    with engine.begin() as conn:
        current = get_applied_version(conn)
        versions_dir = MIGRATIONS_DIR
        if not versions_dir.exists():
            logger.info("No migrations/versions folder found, skipping migrations")
            return

        migration_files = []
        for path in sorted(versions_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                ver = int(path.stem.split("_")[0])
            except ValueError:
                continue
            migration_files.append((ver, path))

        migration_files.sort(key=lambda x: x[0])

        for ver, path in migration_files:
            if ver <= current:
                continue
            name = path.stem
            logger.info("Running migration %s: %s", ver, name)

            import importlib.util
            spec = importlib.util.spec_from_file_location(f"migration_{ver}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "upgrade"):
                raise RuntimeError(f"Migration {path.name} must define upgrade(connection)")
            mod.upgrade(conn)

            conn.execute(
                text("INSERT INTO schema_migrations (version, name, applied_at) VALUES (:v, :n, NOW())"),
                {"v": ver, "n": name}
            )
            logger.info("Applied migration %s", name)
