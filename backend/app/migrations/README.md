# Database migrations

Migrations run automatically on app startup (backend and queue worker) via `init_db()` in `app/database.py`.

## Adding a new migration

1. Create a new file in `versions/` named `NNN_description.py` (e.g. `003_add_foo_column.py`).
2. Implement a function `upgrade(connection)` that runs idempotent SQL (e.g. `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`).
3. Use `from sqlalchemy import text` and `connection.execute(text("..."))` for raw SQL.

Example:

```python
"""Add foo column to video_records."""
from sqlalchemy import text

def upgrade(connection):
    connection.execute(text(
        "ALTER TABLE video_records ADD COLUMN IF NOT EXISTS foo VARCHAR"
    ))
```

Migrations are applied in order by the numeric prefix; each runs only once (version is stored in `schema_migrations`).
