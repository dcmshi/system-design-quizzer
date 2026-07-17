import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from quizzer.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    source      TEXT NOT NULL,
    content     TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',
    source_path TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    word_count  INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    heading     TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id                 TEXT PRIMARY KEY,
    question           TEXT NOT NULL,
    options            TEXT NOT NULL,
    correct_index      INTEGER NOT NULL CHECK (correct_index BETWEEN 0 AND 3),
    explanation        TEXT NOT NULL,
    difficulty         TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard')),
    source_document_id TEXT NOT NULL REFERENCES documents(id),
    source_chunk_id    TEXT NOT NULL REFERENCES chunks(id),
    status             TEXT NOT NULL DEFAULT 'generated'
                           CHECK (status IN ('generated','approved','edited','rejected')),
    fingerprint        TEXT NOT NULL UNIQUE,
    model              TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_status     ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_document   ON questions(source_document_id);

CREATE TABLE IF NOT EXISTS srs_cards (
    question_id    TEXT PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
    ease_factor    REAL    NOT NULL DEFAULT 2.5,
    interval_days  INTEGER NOT NULL DEFAULT 0,
    repetitions    INTEGER NOT NULL DEFAULT 0,
    due_date       TEXT    NOT NULL,
    last_reviewed  TEXT,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS srs_sessions (
    id             TEXT    PRIMARY KEY,
    question_count INTEGER NOT NULL DEFAULT 0,
    question_ids   TEXT,
    started_at     TEXT    NOT NULL,
    finished_at    TEXT
);

CREATE TABLE IF NOT EXISTS srs_reviews (
    id                TEXT    PRIMARY KEY,
    session_id        TEXT    NOT NULL REFERENCES srs_sessions(id) ON DELETE CASCADE,
    question_id       TEXT    NOT NULL REFERENCES questions(id),
    rating            INTEGER NOT NULL CHECK(rating IN (0, 3, 5)),
    was_correct       INTEGER NOT NULL CHECK(was_correct IN (0, 1)),
    ease_factor_after REAL    NOT NULL,
    interval_after    INTEGER NOT NULL,
    reviewed_at       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_srs_cards_due       ON srs_cards(due_date);
CREATE INDEX IF NOT EXISTS idx_srs_reviews_session  ON srs_reviews(session_id);
CREATE INDEX IF NOT EXISTS idx_srs_reviews_question ON srs_reviews(question_id);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id             TEXT PRIMARY KEY,
    question_count INTEGER NOT NULL DEFAULT 0,
    question_ids   TEXT,
    difficulty     TEXT,
    tag            TEXT,
    document_ids   TEXT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT
);

CREATE TABLE IF NOT EXISTS quiz_answers (
    id             TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    question_id    TEXT NOT NULL REFERENCES questions(id),
    selected_index INTEGER NOT NULL,
    is_correct     INTEGER NOT NULL CHECK(is_correct IN (0, 1)),
    answered_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quiz_answers_session  ON quiz_answers(session_id);
CREATE INDEX IF NOT EXISTS idx_quiz_answers_question ON quiz_answers(question_id);
"""


# List of (version, sql) pairs for non-idempotent schema changes.
# New migrations are appended here; the runner applies any not yet recorded.
_MIGRATIONS: list[tuple[int, str]] = [
    # v1: rebuild questions table so status CHECK includes 'rejected'.
    # legacy_alter_table=ON prevents SQLite from rewriting child-table FK
    # references when renaming the parent, so srs_cards / srs_reviews /
    # quiz_answers continue to reference 'questions' after the rebuild.
    (1, """
PRAGMA legacy_alter_table=ON;
PRAGMA foreign_keys=OFF;
ALTER TABLE questions RENAME TO _questions_old;
CREATE TABLE questions (
    id                 TEXT PRIMARY KEY,
    question           TEXT NOT NULL,
    options            TEXT NOT NULL,
    correct_index      INTEGER NOT NULL CHECK (correct_index BETWEEN 0 AND 3),
    explanation        TEXT NOT NULL,
    difficulty         TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard')),
    source_document_id TEXT NOT NULL REFERENCES documents(id),
    source_chunk_id    TEXT NOT NULL REFERENCES chunks(id),
    status             TEXT NOT NULL DEFAULT 'generated'
                           CHECK (status IN ('generated','approved','edited','rejected')),
    fingerprint        TEXT NOT NULL UNIQUE,
    model              TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    created_at         TEXT NOT NULL
);
INSERT INTO questions SELECT * FROM _questions_old;
DROP TABLE _questions_old;
CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_status     ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_document   ON questions(source_document_id);
PRAGMA foreign_keys=ON;
PRAGMA legacy_alter_table=OFF;
"""),
    # v2: record which questions belong to a session (NULL for legacy rows)
    # so answers/reviews for non-member questions can be rejected.
    (2, """
ALTER TABLE quiz_sessions ADD COLUMN question_ids TEXT;
ALTER TABLE srs_sessions  ADD COLUMN question_ids TEXT;
"""),
]


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Wait (instead of erroring) when another connection holds the write lock.
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# Per-thread connections. FastAPI runs sync endpoints in a threadpool, and a
# single sqlite3.Connection must not be used concurrently from multiple threads.
# Each worker thread gets — and reuses — its own connection; WAL mode lets those
# connections read concurrently while writes are serialised with a busy timeout.
_local = threading.local()


def get_shared_connection() -> sqlite3.Connection:
    """Return this thread's SQLite connection (to settings.db_path), creating
    it on first use."""
    conn = getattr(_local, "connection", None)
    if conn is None:
        conn = get_connection()
        _local.connection = conn
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT    NOT NULL
        )
        """
    )
    conn.commit()


def _stamp_all_migrations(conn: sqlite3.Connection) -> None:
    """Record every migration as applied without executing it.

    Used for brand-new databases: _SCHEMA already creates the final shape, so
    replaying migrations would be wasted work at best (and fail outright for
    non-re-runnable statements like ALTER TABLE ADD COLUMN).
    """
    _ensure_migrations_table(conn)
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        [(version, now) for version, _ in _MIGRATIONS],
    )
    conn.commit()


def migrate_db(db_path: Path | None = None) -> None:
    """Apply any pending migrations recorded in _MIGRATIONS."""
    conn = get_connection(db_path)
    try:
        _ensure_migrations_table(conn)
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        current = row["v"] if row and row["v"] is not None else 0
        for version, sql in _MIGRATIONS:
            if version > current:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    conn = get_connection(db_path)
    try:
        fresh = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='questions'"
        ).fetchone() is None
        conn.executescript(_SCHEMA)
        if fresh:
            _stamp_all_migrations(conn)
    finally:
        conn.close()
    migrate_db(db_path)
