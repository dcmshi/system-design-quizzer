"""Integration tests for the SRS API endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quizzer.database import init_db, get_connection
from quizzer.quiz.app import create_app
from quizzer.quiz.service import QuizService
from quizzer.srs.repository import SrsRepository
from quizzer.srs.service import SrsService
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository
from ulid import ULID


@pytest.fixture()
def srs_client(tmp_path: Path, monkeypatch):
    """Test client with isolated DB seeded with one question."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)

    doc_id = str(ULID())
    chunk_id = str(ULID())
    q_id = str(ULID())
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "INSERT INTO documents (id, title, source, content, tags, source_path, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id, "Test Doc", "blog", "Content.", "[]", "test/doc.md", now),
    )
    conn.execute(
        "INSERT INTO chunks (id, document_id, content, word_count, chunk_index, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chunk_id, doc_id, "Chunk.", 1, 0, now),
    )
    conn.execute(
        "INSERT INTO questions "
        "(id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            q_id,
            "What is X?",
            json.dumps(["A", "B", "C", "D"]),
            1,
            "Because B.",
            "easy",
            doc_id,
            chunk_id,
            "generated",
            "fp001",
            "test-model",
            "v1",
            now,
        ),
    )
    conn.commit()

    q_repo = QuestionRepository(conn)
    doc_repo = DocumentRepository(conn)
    srs_repo = SrsRepository(conn)

    from unittest.mock import MagicMock
    mock_ollama = MagicMock()
    mock_ollama.health_check.return_value = True

    quiz_svc = QuizService(question_repo=q_repo, document_repo=doc_repo, ollama_client=mock_ollama)
    srs_svc = SrsService(srs_repo=srs_repo, question_repo=q_repo)

    app = create_app()
    monkeypatch.setattr("quizzer.quiz.app._service", quiz_svc)
    monkeypatch.setattr("quizzer.quiz.app._srs_service", srs_svc)

    return TestClient(app, raise_server_exceptions=True), q_id


# ------------------------------------------------------------------
# /api/v1/srs/due
# ------------------------------------------------------------------

def test_due_counts_new_questions(srs_client):
    client, q_id = srs_client
    resp = client.get("/api/v1/srs/due")
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_count"] >= 1
    assert data["due_count"] == 0
    assert data["total_actionable"] == data["new_count"] + data["due_count"]


# ------------------------------------------------------------------
# POST /api/v1/srs/sessions
# ------------------------------------------------------------------

def test_start_session_returns_questions(srs_client):
    client, q_id = srs_client
    resp = client.post("/api/v1/srs/sessions", json={"n": 10})
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    assert len(data["questions"]) == 1
    assert data["questions"][0]["id"] == q_id


def test_start_session_empty_when_no_due(srs_client):
    """A question due in the future should not appear in the session."""
    client, q_id = srs_client
    # First, review it so it moves to the future
    r1 = client.post("/api/v1/srs/sessions", json={"n": 5})
    session_id = r1.json()["session_id"]
    client.post(
        f"/api/v1/srs/sessions/{session_id}/reviews",
        json={"question_id": q_id, "selected_index": 1},  # correct
    )
    # Now start a new session — question should be scheduled in the future
    r2 = client.post("/api/v1/srs/sessions", json={"n": 5})
    assert r2.status_code == 201
    assert len(r2.json()["questions"]) == 0


# ------------------------------------------------------------------
# POST /api/v1/srs/sessions/{id}/reviews
# ------------------------------------------------------------------

def test_correct_review_returns_expected_fields(srs_client):
    client, q_id = srs_client
    session_id = client.post("/api/v1/srs/sessions", json={"n": 5}).json()["session_id"]
    resp = client.post(
        f"/api/v1/srs/sessions/{session_id}/reviews",
        json={"question_id": q_id, "selected_index": 1},  # correct_index == 1
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is True
    assert data["correct_index"] == 1
    assert "explanation" in data
    assert data["interval_days"] == 1
    assert data["ease_factor"] > 2.5  # improved on perfect answer


def test_wrong_review_resets_interval(srs_client):
    client, q_id = srs_client
    session_id = client.post("/api/v1/srs/sessions", json={"n": 5}).json()["session_id"]
    resp = client.post(
        f"/api/v1/srs/sessions/{session_id}/reviews",
        json={"question_id": q_id, "selected_index": 0},  # wrong
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is False
    assert data["interval_days"] == 1
    assert data["ease_factor"] == pytest.approx(2.5)  # unchanged on wrong


def test_review_with_invalid_session_returns_404(srs_client):
    client, q_id = srs_client
    resp = client.post(
        "/api/v1/srs/sessions/nonexistent/reviews",
        json={"question_id": q_id, "selected_index": 0},
    )
    assert resp.status_code == 404


# ------------------------------------------------------------------
# POST /api/v1/srs/sessions/{id}/finish
# ------------------------------------------------------------------

def test_finish_session_returns_stats(srs_client):
    client, q_id = srs_client
    session_id = client.post("/api/v1/srs/sessions", json={"n": 5}).json()["session_id"]
    client.post(
        f"/api/v1/srs/sessions/{session_id}/reviews",
        json={"question_id": q_id, "selected_index": 1},
    )
    resp = client.post(f"/api/v1/srs/sessions/{session_id}/finish")
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_reviewed"] == 1
    assert data["n_correct"] == 1
    assert data["n_wrong"] == 0
    assert data["session_id"] == session_id


def test_finish_nonexistent_session_returns_404(srs_client):
    client, _ = srs_client
    resp = client.post("/api/v1/srs/sessions/ghost/finish")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# GET /api/v1/srs/sessions/{id}
# ------------------------------------------------------------------

def test_get_session_includes_reviews(srs_client):
    client, q_id = srs_client
    session_id = client.post("/api/v1/srs/sessions", json={"n": 5}).json()["session_id"]
    client.post(
        f"/api/v1/srs/sessions/{session_id}/reviews",
        json={"question_id": q_id, "selected_index": 0},
    )
    resp = client.get(f"/api/v1/srs/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert len(data["reviews"]) == 1
    assert data["reviews"][0]["question_id"] == q_id


def test_get_nonexistent_session_returns_404(srs_client):
    client, _ = srs_client
    resp = client.get("/api/v1/srs/sessions/ghost")
    assert resp.status_code == 404
