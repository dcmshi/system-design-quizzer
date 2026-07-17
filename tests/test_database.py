"""Tests for schema initialization and the migration runner."""

from pathlib import Path

import quizzer.database as db_mod


def test_fresh_db_stamps_migrations_without_replaying(tmp_path: Path, monkeypatch):
    """A brand-new DB already has the final schema — migrations must be
    recorded as applied, not executed (their SQL may not be re-runnable)."""
    sentinel = (99, "INSERT INTO table_that_does_not_exist VALUES (1);")
    monkeypatch.setattr(db_mod, "_MIGRATIONS", db_mod._MIGRATIONS + [sentinel])

    db_path = tmp_path / "fresh.db"
    db_mod.init_db(db_path)  # must not raise

    conn = db_mod.get_connection(db_path)
    try:
        versions = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()
    assert 99 in versions
    assert {v for v, _ in db_mod._MIGRATIONS} <= versions


def test_existing_db_applies_pending_migrations(tmp_path: Path, monkeypatch):
    """A DB stamped at version N gets migration N+1 applied on the next init."""
    db_path = tmp_path / "existing.db"
    db_mod.init_db(db_path)

    pending = (100, "CREATE TABLE migration_ran (id INTEGER PRIMARY KEY);")
    monkeypatch.setattr(db_mod, "_MIGRATIONS", db_mod._MIGRATIONS + [pending])
    db_mod.init_db(db_path)

    conn = db_mod.get_connection(db_path)
    try:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_ran'"
        ).fetchone() is not None
        versions = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()
    assert 100 in versions


def test_init_db_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "idempotent.db"
    db_mod.init_db(db_path)
    db_mod.init_db(db_path)  # must not raise
