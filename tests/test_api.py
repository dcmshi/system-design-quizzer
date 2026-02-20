"""API integration tests using FastAPI TestClient."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quizzer.database import init_db, get_connection
from quizzer.generation.ollama_client import OllamaClient
from quizzer.quiz.app import create_app
from quizzer.quiz.service import QuizService
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository
from ulid import ULID


@pytest.fixture()
def app_client(tmp_path: Path, monkeypatch):
    """Create a test FastAPI app with an isolated SQLite DB."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)

    # Seed a document
    doc_id = str(ULID())
    chunk_id = str(ULID())
    q_id = str(ULID())
    conn.execute(
        "INSERT INTO documents (id, title, source, content, tags, source_path, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id, "Test Doc", "blog", "Content.", "[]", "test/doc.md", datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO chunks (id, document_id, content, word_count, chunk_index, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chunk_id, doc_id, "Chunk content.", 2, 0, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            q_id,
            "What is consistent hashing?",
            json.dumps(["Option A", "Option B", "Option C", "Option D"]),
            1,
            "Consistent hashing distributes load by placing nodes on a ring so only neighbors are affected.",
            "medium",
            doc_id,
            chunk_id,
            "generated",
            "abc123fingerprint",
            "test-model",
            "v1",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    # Build service with mock Ollama
    from unittest.mock import MagicMock
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.health_check.return_value = True

    svc = QuizService(
        question_repo=QuestionRepository(conn),
        document_repo=DocumentRepository(conn),
        ollama_client=mock_ollama,
    )

    import quizzer.quiz.app as app_module
    monkeypatch.setattr(app_module, "_service", svc)

    app = create_app()
    # Bypass lifespan for test
    with TestClient(app, raise_server_exceptions=True) as client:
        # Override the service getter
        monkeypatch.setattr(app_module, "_service", svc)
        yield client, q_id, doc_id


def test_list_questions(app_client):
    client, q_id, doc_id = app_client
    resp = client.get("/api/v1/questions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(q["id"] == q_id for q in data["items"])


def test_get_question_no_answer(app_client):
    client, q_id, _ = app_client
    resp = client.get(f"/api/v1/questions/{q_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == q_id
    assert "correct_index" not in data  # not included in detail


def test_get_question_answer(app_client):
    client, q_id, _ = app_client
    resp = client.get(f"/api/v1/questions/{q_id}/answer")
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct_index"] == 1
    assert "explanation" in data


def test_submit_correct_answer(app_client):
    client, q_id, _ = app_client
    resp = client.post(f"/api/v1/questions/{q_id}/answer", json={"selected_index": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is True
    assert data["correct_index"] == 1


def test_submit_wrong_answer(app_client):
    client, q_id, _ = app_client
    resp = client.post(f"/api/v1/questions/{q_id}/answer", json={"selected_index": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is False


def test_update_status(app_client):
    client, q_id, _ = app_client
    resp = client.patch(f"/api/v1/questions/{q_id}/status", json={"status": "approved"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_quiz_endpoint(app_client):
    client, _, _ = app_client
    resp = client.get("/api/v1/quiz?n=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # answers must not be in quiz response
    for q in data:
        assert "correct_index" not in q


def test_list_documents(app_client):
    client, _, doc_id = app_client
    resp = client.get("/api/v1/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert any(d["id"] == doc_id for d in docs)
    found = next(d for d in docs if d["id"] == doc_id)
    assert found["question_count"] == 1


def test_health_endpoint(app_client):
    client, _, _ = app_client
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["db"] == "connected"


def test_question_not_found(app_client):
    client, _, _ = app_client
    resp = client.get("/api/v1/questions/nonexistent")
    assert resp.status_code == 404


def test_edit_question(app_client):
    client, q_id, _ = app_client
    payload = {
        "question": "What is a load balancer?",
        "options": ["Opt A", "Opt B", "Opt C", "Opt D"],
        "correct_index": 2,
        "explanation": "A load balancer distributes traffic.",
        "difficulty": "easy",
    }
    resp = client.put(f"/api/v1/questions/{q_id}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "edited"
    assert data["question"] == "What is a load balancer?"

    # Verify answer details updated
    ans = client.get(f"/api/v1/questions/{q_id}/answer").json()
    assert ans["correct_index"] == 2
    assert ans["explanation"] == "A load balancer distributes traffic."


def test_edit_question_not_found(app_client):
    client, _, _ = app_client
    payload = {
        "question": "Q?",
        "options": ["A", "B", "C", "D"],
        "correct_index": 0,
        "explanation": "E.",
        "difficulty": "easy",
    }
    resp = client.put("/api/v1/questions/nonexistent", json=payload)
    assert resp.status_code == 404


def test_reject_status(app_client):
    client, q_id, _ = app_client
    resp = client.patch(f"/api/v1/questions/{q_id}/status", json={"status": "rejected"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_quiz_excludes_rejected(app_client):
    client, q_id, _ = app_client
    # Reject the only question
    client.patch(f"/api/v1/questions/{q_id}/status", json={"status": "rejected"})
    # Quiz should return no results
    resp = client.get("/api/v1/quiz?n=5")
    assert resp.status_code == 200
    assert resp.json() == []
