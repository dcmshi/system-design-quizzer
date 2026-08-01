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
    due = repo.get_due_questions(10, document_ids=[doc_id])
    assert [q["id"] for q in due] == [q_id]


def test_get_due_questions_with_other_document_filter_excludes(db_conn):
    """A document_id filter must exclude cards from other documents."""
    doc_a, q_a = str(ULID()), str(ULID())
    doc_b, q_b = str(ULID()), str(ULID())
    _seed_question(db_conn, doc_id=doc_a, q_id=q_a)
    _seed_question(db_conn, doc_id=doc_b, q_id=q_b)
    repo = SrsRepository(db_conn)
    due = repo.get_due_questions(10, document_ids=[doc_a])
    ids = {q["id"] for q in due}
    assert q_a in ids
    assert q_b not in ids


def _add_card(conn, question_id: str, due_date: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO srs_cards (question_id, ease_factor, interval_days, repetitions, "
        "due_date, last_reviewed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (question_id, 2.5, 1, 1, due_date, now, now),
    )
    conn.commit()


def test_due_counts_by_document_splits_due_from_new(db_conn):
    doc_a, q_due, q_new = str(ULID()), str(ULID()), str(ULID())
    doc_b, q_future = str(ULID()), str(ULID())
    _seed_question(db_conn, doc_id=doc_a, q_id=q_due)
    _seed_question(db_conn, doc_id=doc_a, q_id=q_new)
    _seed_question(db_conn, doc_id=doc_b, q_id=q_future)
    _add_card(db_conn, q_due, "2026-01-01")
    _add_card(db_conn, q_future, "2099-01-01")

    counts = SrsRepository(db_conn).due_counts_by_document(today="2026-06-01")

    assert counts[doc_a] == {"due_count": 1, "new_count": 1}
    assert counts[doc_b] == {"due_count": 0, "new_count": 0}


def test_due_counts_by_document_matches_the_per_document_query(db_conn):
    doc_id, q_due, q_new = str(ULID()), str(ULID()), str(ULID())
    _seed_question(db_conn, doc_id=doc_id, q_id=q_due)
    _seed_question(db_conn, doc_id=doc_id, q_id=q_new)
    _add_card(db_conn, q_due, "2026-01-01")
    repo = SrsRepository(db_conn)

    bulk = repo.due_counts_by_document(today="2026-06-01")[doc_id]
    assert bulk == repo.due_count(document_ids=[doc_id], today="2026-06-01")


def test_due_counts_by_document_ignores_rejected_questions(db_conn):
    doc_id, q_id = str(ULID()), str(ULID())
    _seed_question(db_conn, doc_id=doc_id, q_id=q_id)
    db_conn.execute("UPDATE questions SET status = 'rejected' WHERE id = ?", (q_id,))
    db_conn.commit()

    assert SrsRepository(db_conn).due_counts_by_document() == {}


def test_get_due_questions_spans_several_documents(db_conn):
    """SRS mode honours the multi-select picker, like random and weak mode."""
    doc_a, q_a = str(ULID()), str(ULID())
    doc_b, q_b = str(ULID()), str(ULID())
    doc_c, q_c = str(ULID()), str(ULID())
    for doc, q in ((doc_a, q_a), (doc_b, q_b), (doc_c, q_c)):
        _seed_question(db_conn, doc_id=doc, q_id=q)

    due = SrsRepository(db_conn).get_due_questions(10, document_ids=[doc_a, doc_b])
    assert {q["id"] for q in due} == {q_a, q_b}


def test_due_count_spans_several_documents(db_conn):
    doc_a, q_a = str(ULID()), str(ULID())
    doc_b, q_b = str(ULID()), str(ULID())
    doc_c, q_c = str(ULID()), str(ULID())
    for doc, q in ((doc_a, q_a), (doc_b, q_b), (doc_c, q_c)):
        _seed_question(db_conn, doc_id=doc, q_id=q)

    counts = SrsRepository(db_conn).due_count(document_ids=[doc_a, doc_b])
    assert counts == {"due_count": 0, "new_count": 2}
