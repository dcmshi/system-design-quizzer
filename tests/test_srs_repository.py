"""Unit tests for SrsRepository query construction."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ulid import ULID

from quizzer.srs.repository import SrsRepository


def _seed_question(conn, *, doc_id: str, q_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if not conn.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,)).fetchone():
        conn.execute(
            "INSERT INTO documents (id, title, source, content, tags, source_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, f"Doc {doc_id[:4]}", "blog", "Content.", "[]", f"p/{doc_id}.md", now),
        )
    chunk_id = str(ULID())
    conn.execute(
        "INSERT INTO chunks (id, document_id, content, word_count, chunk_index, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chunk_id, doc_id, "Chunk.", 1, 0, now),
    )
    conn.execute(
        "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            q_id, "Q?", json.dumps(["A", "B", "C", "D"]), 1, "because", "easy",
            doc_id, chunk_id, "generated", str(ULID()), "m", "v1", now,
        ),
    )
    conn.commit()


def test_get_due_questions_without_document_filter(db_conn):
    doc_id, q_id = str(ULID()), str(ULID())
    _seed_question(db_conn, doc_id=doc_id, q_id=q_id)
    repo = SrsRepository(db_conn)
    due = repo.get_due_questions(10)
    assert [q["id"] for q in due] == [q_id]


def test_get_due_questions_with_matching_document_filter(db_conn):
    """Regression: a document_id filter must not drop new/due cards for that doc."""
    doc_id, q_id = str(ULID()), str(ULID())
    _seed_question(db_conn, doc_id=doc_id, q_id=q_id)
    repo = SrsRepository(db_conn)
    due = repo.get_due_questions(10, document_id=doc_id)
    assert [q["id"] for q in due] == [q_id]


def test_get_due_questions_with_other_document_filter_excludes(db_conn):
    """A document_id filter must exclude cards from other documents."""
    doc_a, q_a = str(ULID()), str(ULID())
    doc_b, q_b = str(ULID()), str(ULID())
    _seed_question(db_conn, doc_id=doc_a, q_id=q_a)
    _seed_question(db_conn, doc_id=doc_b, q_id=q_b)
    repo = SrsRepository(db_conn)
    due = repo.get_due_questions(10, document_id=doc_a)
    ids = {q["id"] for q in due}
    assert q_a in ids
    assert q_b not in ids
