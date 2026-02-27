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
from quizzer.quiz.session_service import QuizSessionService
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository
from quizzer.storage.session_repo import SessionRepository
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
        (doc_id, "Test Doc", "blog", "Content.", json.dumps(["caching", "distributed"]), "test/doc.md", datetime.now(timezone.utc).isoformat()),
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


def test_hit_rate_zero_before_any_answer(app_client):
    client, q_id, _ = app_client
    resp = client.get(f"/api/v1/questions/{q_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["times_answered"] == 0
    assert data["times_correct"] == 0
    assert data["hit_rate"] is None


def test_hit_rate_updates_after_quiz_session_answer(app_client):
    client, q_id, _ = app_client
    import quizzer.quiz.app as app_module
    from quizzer.quiz.session_service import QuizSessionService
    from quizzer.storage.session_repo import SessionRepository
    from quizzer.storage.question_repo import QuestionRepository

    conn = app_module._service.questions._conn
    session_svc = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    app_module._quiz_session_service = session_svc

    # Start a session and answer correctly
    sess = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    session_id = sess["session_id"]
    client.post(
        f"/api/v1/quiz/sessions/{session_id}/answers",
        json={"question_id": q_id, "selected_index": 1},  # correct_index is 1
    )

    resp = client.get(f"/api/v1/questions/{q_id}")
    data = resp.json()
    assert data["times_answered"] == 1
    assert data["times_correct"] == 1
    assert data["hit_rate"] == 1.0


def test_hit_rate_wrong_answer(app_client):
    client, q_id, _ = app_client
    import quizzer.quiz.app as app_module
    from quizzer.quiz.session_service import QuizSessionService
    from quizzer.storage.session_repo import SessionRepository
    from quizzer.storage.question_repo import QuestionRepository

    conn = app_module._service.questions._conn
    session_svc = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    app_module._quiz_session_service = session_svc

    sess = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    session_id = sess["session_id"]
    client.post(
        f"/api/v1/quiz/sessions/{session_id}/answers",
        json={"question_id": q_id, "selected_index": 0},  # wrong
    )

    resp = client.get(f"/api/v1/questions/{q_id}")
    data = resp.json()
    assert data["times_answered"] == 1
    assert data["times_correct"] == 0
    assert data["hit_rate"] == 0.0


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
    assert data["requested"] == 1
    assert data["returned"] == len(data["questions"])
    assert len(data["questions"]) >= 1
    # answers must not be in quiz response
    for q in data["questions"]:
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
    # Quiz should return no results but still reflect the requested count
    resp = client.get("/api/v1/quiz?n=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["questions"] == []
    assert data["requested"] == 5
    assert data["returned"] == 0


def test_tags_endpoint(app_client):
    client, _, _ = app_client
    resp = client.get("/api/v1/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert "caching" in tags
    assert "distributed" in tags
    assert tags == sorted(tags)


def test_quiz_tag_filter_match(app_client):
    client, q_id, _ = app_client
    resp = client.get("/api/v1/quiz?n=5&tag=caching")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["questions"]) >= 1
    assert any(q["id"] == q_id for q in data["questions"])


def test_quiz_tag_filter_no_match(app_client):
    client, _, _ = app_client
    resp = client.get("/api/v1/quiz?n=5&tag=nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["questions"] == []
    assert data["returned"] == 0


def test_quiz_multi_document_filter(app_client):
    """Passing two document_id params returns questions from both documents."""
    client, q_id, doc_id = app_client
    # Access the underlying connection via the service
    import quizzer.quiz.app as app_module
    conn = app_module._service.questions._conn

    doc_id2 = str(ULID())
    chunk_id2 = str(ULID())
    q_id2 = str(ULID())
    conn.execute(
        "INSERT INTO documents (id, title, source, content, tags, source_path, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id2, "Test Doc 2", "blog", "Content 2.", json.dumps([]), "test/doc2.md",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO chunks (id, document_id, content, word_count, chunk_index, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chunk_id2, doc_id2, "Chunk 2.", 2, 0, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            q_id2,
            "What is a load balancer?",
            json.dumps(["A", "B", "C", "D"]),
            0,
            "Distributes traffic.",
            "easy",
            doc_id2,
            chunk_id2,
            "generated",
            "fingerprint_doc2",
            "test-model",
            "v1",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    resp = client.get(f"/api/v1/quiz?n=10&document_id={doc_id}&document_id={doc_id2}")
    assert resp.status_code == 200
    returned_ids = {q["id"] for q in resp.json()["questions"]}
    assert q_id in returned_ids
    assert q_id2 in returned_ids


def test_quiz_single_document_id_still_works(app_client):
    """Single document_id param (list of 1) still filters correctly."""
    client, q_id, doc_id = app_client
    resp = client.get(f"/api/v1/quiz?n=5&document_id={doc_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["questions"]) >= 1
    assert all(q["source_document_id"] == doc_id for q in data["questions"])


def test_export_json(app_client):
    client, q_id, doc_id = app_client
    resp = client.get("/api/v1/questions/export")
    assert resp.status_code == 200
    data = resp.json()
    assert "documents" in data
    assert "questions" in data
    assert "version" in data
    assert len(data["questions"]) >= 1
    q = data["questions"][0]
    assert q["id"] == q_id
    assert "correct_index" in q
    assert "explanation" in q


def test_export_csv(app_client):
    client, q_id, _ = app_client
    resp = client.get("/api/v1/questions/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    import csv as _csv, io
    reader = _csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) >= 1
    assert "option_a" in reader.fieldnames
    assert "option_d" in reader.fieldnames
    assert rows[0]["id"] == q_id


def test_export_status_filter(app_client):
    client, _, _ = app_client
    resp = client.get("/api/v1/questions/export?status=approved")
    assert resp.status_code == 200
    data = resp.json()
    # Seeded question has status='generated', so approved filter returns empty
    assert data["questions"] == []


def test_import_roundtrip(app_client):
    client, q_id, _ = app_client
    # Export the data
    export_resp = client.get("/api/v1/questions/export")
    assert export_resp.status_code == 200
    payload = export_resp.json()
    # Import it back
    import_resp = client.post("/api/v1/questions/import", json=payload)
    assert import_resp.status_code == 200
    result = import_resp.json()
    assert result["imported"] == 0   # fingerprint already exists
    assert result["skipped"] == 1
    assert result["errors"] == []
    # Original question still present
    assert client.get(f"/api/v1/questions/{q_id}").status_code == 200


def test_import_skips_duplicates(app_client):
    client, _, _ = app_client
    export_resp = client.get("/api/v1/questions/export")
    payload = export_resp.json()
    # First import: already in DB → all skipped
    r1 = client.post("/api/v1/questions/import", json=payload).json()
    assert r1["skipped"] == 1
    assert r1["imported"] == 0
    # Second import: same result
    r2 = client.post("/api/v1/questions/import", json=payload).json()
    assert r2["skipped"] == 1
    assert r2["imported"] == 0


def test_import_creates_synthetic_chunks(app_client):
    import quizzer.quiz.app as app_module
    client, _, doc_id = app_client
    conn = app_module._service.questions._conn

    new_q_id = str(ULID())
    new_chunk_id = str(ULID())
    new_fp = "unique_fingerprint_synthetic_chunk_test"
    payload = {
        "version": "1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "documents": [],
        "questions": [
            {
                "id": new_q_id,
                "question": "What is a synthetic chunk?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explanation": "A placeholder chunk created on import.",
                "difficulty": "easy",
                "source_document_id": doc_id,
                "source_chunk_id": new_chunk_id,
                "status": "generated",
                "fingerprint": new_fp,
                "model": "test-model",
                "prompt_version": "v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
    resp = client.post("/api/v1/questions/import", json=payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["imported"] == 1
    assert result["errors"] == []
    # Synthetic chunk row must exist in DB
    row = conn.execute("SELECT id FROM chunks WHERE id = ?", (new_chunk_id,)).fetchone()
    assert row is not None


# ── Quiz Session tests ────────────────────────────────────────────────────────

@pytest.fixture()
def quiz_session_client(tmp_path: Path, monkeypatch):
    """Isolated DB with one question, services wired for quiz session tests."""
    db_path = tmp_path / "test_session.db"
    init_db(db_path)
    conn = get_connection(db_path)

    doc_id = str(ULID())
    chunk_id = str(ULID())
    q_id = str(ULID())
    conn.execute(
        "INSERT INTO documents (id, title, source, content, tags, source_path, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id, "Session Doc", "blog", "Content.", json.dumps([]), "test/session_doc.md",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO chunks (id, document_id, content, word_count, chunk_index, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chunk_id, doc_id, "Chunk.", 1, 0, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            q_id,
            "What is a CDN?",
            json.dumps(["Opt A", "Opt B", "Opt C", "Opt D"]),
            2,
            "A CDN caches content closer to users.",
            "easy",
            doc_id,
            chunk_id,
            "generated",
            "session_fp_abc123",
            "test-model",
            "v1",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    from unittest.mock import MagicMock
    mock_ollama = MagicMock(spec=OllamaClient)

    svc = QuizService(
        question_repo=QuestionRepository(conn),
        document_repo=DocumentRepository(conn),
        ollama_client=mock_ollama,
    )
    session_svc = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )

    import quizzer.quiz.app as app_module
    monkeypatch.setattr(app_module, "_service", svc)
    monkeypatch.setattr(app_module, "_quiz_session_service", session_svc)

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        monkeypatch.setattr(app_module, "_service", svc)
        monkeypatch.setattr(app_module, "_quiz_session_service", session_svc)
        yield client, q_id, doc_id


def test_create_quiz_session(quiz_session_client):
    client, q_id, _ = quiz_session_client
    resp = client.post("/api/v1/quiz/sessions", json={"n": 1})
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    assert "started_at" in data
    assert len(data["questions"]) == 1
    q = data["questions"][0]
    assert "correct_index" not in q
    assert q["id"] == q_id


def test_submit_correct_quiz_answer(quiz_session_client):
    client, q_id, _ = quiz_session_client
    sess = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    session_id = sess["session_id"]

    resp = client.post(
        f"/api/v1/quiz/sessions/{session_id}/answers",
        json={"question_id": q_id, "selected_index": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is True
    assert data["correct_index"] == 2
    assert "explanation" in data


def test_submit_wrong_quiz_answer(quiz_session_client):
    client, q_id, _ = quiz_session_client
    sess = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    session_id = sess["session_id"]

    resp = client.post(
        f"/api/v1/quiz/sessions/{session_id}/answers",
        json={"question_id": q_id, "selected_index": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["correct"] is False
    assert data["correct_index"] == 2


def test_finish_quiz_session(quiz_session_client):
    client, q_id, _ = quiz_session_client
    sess = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    session_id = sess["session_id"]
    client.post(
        f"/api/v1/quiz/sessions/{session_id}/answers",
        json={"question_id": q_id, "selected_index": 2},
    )

    resp = client.post(f"/api/v1/quiz/sessions/{session_id}/finish")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert "finished_at" in data
    assert data["n_answered"] == 1
    assert data["n_correct"] == 1
    assert data["n_wrong"] == 0
    assert data["n_skipped"] == 0


def test_get_quiz_session(quiz_session_client):
    client, q_id, _ = quiz_session_client
    sess = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    session_id = sess["session_id"]
    client.post(
        f"/api/v1/quiz/sessions/{session_id}/answers",
        json={"question_id": q_id, "selected_index": 0},
    )

    resp = client.get(f"/api/v1/quiz/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert len(data["answers"]) == 1
    assert data["answers"][0]["question_id"] == q_id
    assert data["answers"][0]["is_correct"] is False


def test_finish_nonexistent_session(quiz_session_client):
    client, _, _ = quiz_session_client
    resp = client.post("/api/v1/quiz/sessions/nonexistent/finish")
    assert resp.status_code == 404
