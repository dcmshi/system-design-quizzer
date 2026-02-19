import sqlite3
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
                           CHECK (status IN ('generated','approved','edited')),
    fingerprint        TEXT NOT NULL UNIQUE,
    model              TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_status     ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_document   ON questions(source_document_id);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(_SCHEMA)
