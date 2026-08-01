"""API integration tests using FastAPI TestClient."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quizzer.database import init_db, get_connection
from quizzer.quiz import deps as deps_module
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

    # Build service with mock LLM client
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    mock_llm.health_check.return_value = True

    svc = QuizService(
        question_repo=QuestionRepository(conn),
        document_repo=DocumentRepository(conn),
        llm_client=mock_llm,
    )

    monkeypatch.setattr(deps_module, "_service", svc)

    app = create_app()
    # Bypass lifespan for test
    with TestClient(app, raise_server_exceptions=True) as client:
        # Override the service getter
        monkeypatch.setattr(deps_module, "_service", svc)
        yield client, q_id, doc_id


def test_list_questions(app_client):
    client, q_id, doc_id = app_client
    resp = client.get("/api/v1/questions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(q["id"] == q_id for q in data["items"])


def test_list_questions_includes_answer_and_provenance(app_client):
    """The review UI renders a card straight from the list row, so the answer,
    provenance and hit-rate fields must all be present without a second call."""
    client, q_id, _ = app_client
    item = next(q for q in client.get("/api/v1/questions").json()["items"] if q["id"] == q_id)

    assert item["correct_index"] == 1
    assert item["explanation"].startswith("Consistent hashing distributes load")
    assert item["model"] == "test-model"
    assert item["prompt_version"] == "v1"
    assert item["times_answered"] == 0
    assert item["times_correct"] == 0
    assert item["hit_rate"] is None


def test_quiz_sample_still_withholds_the_correct_answer(app_client):
    """Enriching the review list must not leak correct_index to the quiz."""
    client, _, _ = app_client
    for question in client.get("/api/v1/quiz?n=1").json()["questions"]:
        assert "correct_index" not in question
        assert "explanation" not in question


def test_search_treats_percent_as_literal(app_client):
    """A '%' in the query must match literally, not act as a LIKE wildcard."""
    client, _, doc_id = app_client
    conn = deps_module._service.questions._conn
    chunk_id = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()["id"]

    def _add(qid, text, fp):
        conn.execute(
            "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
            "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qid, text, json.dumps(["A", "B", "C", "D"]), 0, "neutral explanation text here.",
             "easy", doc_id, chunk_id, "generated", fp, "m", "v1",
             datetime.now(timezone.utc).isoformat()),
        )

    a_id, b_id = str(ULID()), str(ULID())
    _add(a_id, "cache ratio 50% today", "fp_literal_pct_a")   # contains literal "50%"
    _add(b_id, "cache ratio 5000 today", "fp_literal_pct_b")  # contains "50" but not "50%"
    conn.commit()

    resp = client.get("/api/v1/questions?q=50%25")  # %25 == '%' url-encoded
    assert resp.status_code == 200
    ids = {q["id"] for q in resp.json()["items"]}
    assert a_id in ids       # literal "50%" match
    assert b_id not in ids   # would match only if '%' were a wildcard


def test_list_questions_ordering_stable_on_created_at_ties(app_client):
    """Equal created_at (common after imports) must fall back to id order,
    not arbitrary scan order, so pagination windows don't overlap or skip."""
    client, _, doc_id = app_client
    conn = deps_module._service.questions._conn
    chunk_id = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()["id"]
    tied_at = "2099-01-01T00:00:00+00:00"

    def _add(qid, fp):
        conn.execute(
            "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
            "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qid, f"Tie question {qid}?", json.dumps(["A", "B", "C", "D"]), 0,
             "A neutral explanation for the tie test.", "easy", doc_id, chunk_id,
             "generated", fp, "m", "v1", tied_at),
        )

    _add("ZZZ_TIE", "fp_tie_z")  # inserted first, sorts last by id
    _add("AAA_TIE", "fp_tie_a")  # inserted second, sorts first by id
    conn.commit()

    ids = [q["id"] for q in client.get("/api/v1/questions?limit=200").json()["items"]]
    assert ids.index("AAA_TIE") < ids.index("ZZZ_TIE")


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
    from quizzer.quiz.session_service import QuizSessionService
    from quizzer.storage.session_repo import SessionRepository
    from quizzer.storage.question_repo import QuestionRepository

    conn = deps_module._service.questions._conn
    session_svc = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    deps_module._quiz_session_service = session_svc

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
    from quizzer.quiz.session_service import QuizSessionService
    from quizzer.storage.session_repo import SessionRepository
    from quizzer.storage.question_repo import QuestionRepository

    conn = deps_module._service.questions._conn
    session_svc = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    deps_module._quiz_session_service = session_svc

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


def test_edit_question_refreshes_fingerprint(app_client):
    """The dedup fingerprint must track the edited wording, otherwise a later
    ingest can insert a duplicate of the edited question."""
    from quizzer.validation.duplicate_detector import fingerprint

    client, q_id, _ = app_client
    new_text = "How does a reverse proxy differ from a forward proxy?"
    client.put(f"/api/v1/questions/{q_id}", json={
        "question": new_text,
        "options": ["Opt A", "Opt B", "Opt C", "Opt D"],
        "correct_index": 1,
        "explanation": "A reverse proxy fronts servers; a forward proxy fronts clients.",
        "difficulty": "medium",
    })

    conn = deps_module._service.questions._conn
    row = conn.execute("SELECT fingerprint FROM questions WHERE id = ?", (q_id,)).fetchone()
    assert row["fingerprint"] == fingerprint(new_text)


def test_edit_question_colliding_with_existing_returns_409(app_client):
    """Editing a question to duplicate another question's text must be rejected."""
    from quizzer.validation.duplicate_detector import fingerprint

    client, q_id, doc_id = app_client
    conn = deps_module._service.questions._conn
    _insert_question(conn, doc_id, "What is sharding?", fingerprint("What is sharding?"))

    resp = client.put(f"/api/v1/questions/{q_id}", json={
        "question": "What is sharding?",  # collides with other_id
        "options": ["Opt A", "Opt B", "Opt C", "Opt D"],
        "correct_index": 0,
        "explanation": "This edit would duplicate an existing question.",
        "difficulty": "easy",
    })
    assert resp.status_code == 409
    # Original question unchanged
    detail = client.get(f"/api/v1/questions/{q_id}").json()
    assert detail["question"] != "What is sharding?"


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


def test_rejected_excluded_from_document_count(app_client):
    client, q_id, doc_id = app_client
    # Before reject: count is 1
    docs = client.get("/api/v1/documents").json()
    before = next(d for d in docs if d["id"] == doc_id)["question_count"]
    assert before == 1
    # After reject: count drops to 0
    client.patch(f"/api/v1/questions/{q_id}/status", json={"status": "rejected"})
    docs = client.get("/api/v1/documents").json()
    after = next(d for d in docs if d["id"] == doc_id)["question_count"]
    assert after == 0


def test_delete_question(app_client):
    client, q_id, _ = app_client
    resp = client.delete(f"/api/v1/questions/{q_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/v1/questions/{q_id}").status_code == 404


def test_delete_question_not_found(app_client):
    client, _, _ = app_client
    assert client.delete("/api/v1/questions/nonexistent").status_code == 404


def test_bulk_reject_questions(app_client):
    client, q_id, _ = app_client
    resp = client.post(
        "/api/v1/questions/bulk-status",
        json={"ids": [q_id], "status": "rejected"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"updated": 1}
    # Question still exists
    assert client.get(f"/api/v1/questions/{q_id}/answer").status_code == 200
    # Quiz excludes it
    quiz_resp = client.get("/api/v1/quiz?n=5")
    assert quiz_resp.status_code == 200
    assert quiz_resp.json()["questions"] == []


def test_bulk_reject_empty_ids_returns_422(app_client):
    client, _, _ = app_client
    resp = client.post(
        "/api/v1/questions/bulk-status",
        json={"ids": [], "status": "rejected"},
    )
    assert resp.status_code == 422


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
    conn = deps_module._service.questions._conn

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
    import csv as _csv
    import io
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


def test_export_rejected_when_explicitly_requested(app_client):
    """Rejected questions are excluded by default, but an explicit
    status=rejected filter must return them, not an empty set."""
    client, q_id, _ = app_client
    client.patch(f"/api/v1/questions/{q_id}/status", json={"status": "rejected"})

    default_export = client.get("/api/v1/questions/export").json()
    assert all(q["id"] != q_id for q in default_export["questions"])

    rejected_export = client.get("/api/v1/questions/export?status=rejected").json()
    assert any(q["id"] == q_id for q in rejected_export["questions"])


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


def test_import_rejects_wrong_option_count(app_client):
    """A payload with != 4 options must be rejected (422), not stored as a landmine."""
    client, _, doc_id = app_client
    payload = {
        "version": "1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "documents": [],
        "questions": [
            {
                "id": str(ULID()),
                "question": "Only three options?",
                "options": ["A", "B", "C"],  # invalid — must be exactly 4
                "correct_index": 0,
                "explanation": "x" * 60,
                "difficulty": "easy",
                "source_document_id": doc_id,
                "source_chunk_id": str(ULID()),
                "status": "generated",
                "fingerprint": "fp_bad_option_count",
                "model": "m",
                "prompt_version": "v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
    resp = client.post("/api/v1/questions/import", json=payload)
    assert resp.status_code == 422


def test_import_remaps_documents_by_source_path(app_client):
    """Importing an export from another machine — where the same article was
    ingested under a different document id — must remap questions onto the
    existing document instead of failing every FK check."""
    client, _, doc_id = app_client

    foreign_doc_id = str(ULID())  # same article, different id on the other machine
    new_q_id = str(ULID())
    payload = {
        "version": "1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "documents": [
            {
                "id": foreign_doc_id,
                "title": "Test Doc",
                "source": "blog",
                "content": "Content.",
                "tags": ["caching"],
                "source_path": "test/doc.md",  # matches the seeded document
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "questions": [
            {
                "id": new_q_id,
                "question": "What does a write-through cache do?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explanation": "It writes to cache and store synchronously on every write.",
                "difficulty": "easy",
                "source_document_id": foreign_doc_id,
                "source_chunk_id": str(ULID()),
                "status": "generated",
                "fingerprint": "fp_remap_source_path_test",
                "model": "m",
                "prompt_version": "v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
    result = client.post("/api/v1/questions/import", json=payload).json()
    assert result["errors"] == []
    assert result["imported"] == 1

    # The question landed on the existing document, not the foreign id.
    detail = client.get(f"/api/v1/questions/{new_q_id}").json()
    assert detail["source_document_id"] == doc_id


def test_import_creates_synthetic_chunks(app_client):
    client, _, doc_id = app_client
    conn = deps_module._service.questions._conn

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
    mock_llm = MagicMock()

    svc = QuizService(
        question_repo=QuestionRepository(conn),
        document_repo=DocumentRepository(conn),
        llm_client=mock_llm,
    )
    session_svc = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )

    monkeypatch.setattr(deps_module, "_service", svc)
    monkeypatch.setattr(deps_module, "_quiz_session_service", session_svc)

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        monkeypatch.setattr(deps_module, "_service", svc)
        monkeypatch.setattr(deps_module, "_quiz_session_service", session_svc)
        yield client, q_id, doc_id


def test_list_questions_hit_rate_reflects_recorded_answers(quiz_session_client):
    client, q_id, _ = quiz_session_client
    session = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    client.post(
        f"/api/v1/quiz/sessions/{session['session_id']}/answers",
        json={"question_id": q_id, "selected_index": 2},
    )

    item = next(q for q in client.get("/api/v1/questions").json()["items"] if q["id"] == q_id)
    assert item["times_answered"] == 1
    assert item["times_correct"] == 1
    assert item["hit_rate"] == 1.0


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


def test_finish_session_skipped_never_negative(quiz_session_client):
    """Answering the same question twice must not produce a negative n_skipped."""
    client, q_id, _ = quiz_session_client
    session_id = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()["session_id"]
    # Answer the single question twice.
    for _ in range(2):
        client.post(
            f"/api/v1/quiz/sessions/{session_id}/answers",
            json={"question_id": q_id, "selected_index": 2},
        )
    data = client.post(f"/api/v1/quiz/sessions/{session_id}/finish").json()
    assert data["n_answered"] == 2
    assert data["n_skipped"] == 0  # clamped, not -1


def _insert_question(conn, doc_id: str, text: str, fp: str) -> str:
    """Insert a bare question row and return its id."""
    qid = str(ULID())
    chunk_id = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (qid, text, json.dumps(["A", "B", "C", "D"]), 0, "A neutral explanation of the answer.",
         "easy", doc_id, chunk_id, "generated", fp, "m", "v1",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return qid


def test_answer_for_question_outside_session_is_rejected(quiz_session_client):
    """Only questions dealt into the session may be answered against it."""
    client, q_id, doc_id = quiz_session_client
    session_id = client.post("/api/v1/quiz/sessions", json={"n": 5}).json()["session_id"]

    # Inserted after the session started, so it is not part of the session.
    conn = deps_module._quiz_session_service._questions._conn
    outsider = _insert_question(conn, doc_id, "Outsider question?", "fp_outsider_quiz")

    resp = client.post(
        f"/api/v1/quiz/sessions/{session_id}/answers",
        json={"question_id": outsider, "selected_index": 0},
    )
    assert resp.status_code == 404
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM quiz_answers WHERE session_id = ?", (session_id,)
    ).fetchone()["c"]
    assert n == 0  # nothing recorded


def test_legacy_session_without_question_ids_still_accepts_answers(quiz_session_client):
    """Sessions created before the question_ids column existed must keep working."""
    client, q_id, _ = quiz_session_client
    conn = deps_module._quiz_session_service._questions._conn
    legacy_id = str(ULID())
    conn.execute(
        "INSERT INTO quiz_sessions (id, question_count, started_at) VALUES (?, ?, ?)",
        (legacy_id, 1, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()

    resp = client.post(
        f"/api/v1/quiz/sessions/{legacy_id}/answers",
        json={"question_id": q_id, "selected_index": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["correct"] is True


# ── Weak-topic replay tests ───────────────────────────────────────────────────

def test_weak_count_zero_with_no_history(quiz_session_client):
    client, _, _ = quiz_session_client
    resp = client.get("/api/v1/quiz/weak-count")
    assert resp.status_code == 200
    assert resp.json()["weak_count"] == 0


def test_weak_session_empty_with_no_history(quiz_session_client):
    client, _, _ = quiz_session_client
    resp = client.post("/api/v1/quiz/sessions", json={"n": 5, "weak": True})
    assert resp.status_code == 201
    assert resp.json()["questions"] == []


def test_weak_count_and_session_after_wrong_answer(quiz_session_client):
    client, q_id, _ = quiz_session_client
    from quizzer.quiz.session_service import QuizSessionService
    from quizzer.storage.session_repo import SessionRepository
    from quizzer.storage.question_repo import QuestionRepository

    conn = deps_module._service.questions._conn
    session_svc = QuizSessionService(
        session_repo=SessionRepository(conn),
        question_repo=QuestionRepository(conn),
    )
    deps_module._quiz_session_service = session_svc

    # Answer wrong so the question lands in the weak pool
    sess = client.post("/api/v1/quiz/sessions", json={"n": 1}).json()
    client.post(
        f"/api/v1/quiz/sessions/{sess['session_id']}/answers",
        json={"question_id": q_id, "selected_index": 0},  # wrong
    )

    # Weak count should now be 1
    count_resp = client.get("/api/v1/quiz/weak-count")
    assert count_resp.status_code == 200
    assert count_resp.json()["weak_count"] == 1

    # Weak session should return the poorly-answered question
    weak_resp = client.post("/api/v1/quiz/sessions", json={"n": 5, "weak": True})
    assert weak_resp.status_code == 201
    data = weak_resp.json()
    assert len(data["questions"]) == 1
    assert data["questions"][0]["id"] == q_id


# ── Near-duplicate detection tests ────────────────────────────────────────────

def test_near_duplicates_empty_with_single_question(app_client):
    """Single question — no pairs possible."""
    client, _, _ = app_client
    resp = client.get("/api/v1/questions/near-duplicates")
    assert resp.status_code == 200
    assert resp.json() == []


def test_near_duplicates_detects_similar_questions(app_client, tmp_path):
    """Two nearly identical questions should be flagged."""
    client, q_id, _ = app_client
    conn = deps_module._service.questions._conn

    # Seed a second question with very similar text
    q2_id = str(ULID())
    chunk_id = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()["id"]
    doc_id = conn.execute("SELECT id FROM documents LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            q2_id,
            "What is consistent hashing used for?",  # highly similar to seed question
            json.dumps(["Opt A", "Opt B", "Opt C", "Opt D"]),
            0, "Explanation.", "easy", doc_id, chunk_id,
            "generated", "fp_near_dupe_test", "model", "v1",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    resp = client.get("/api/v1/questions/near-duplicates?threshold=0.3")
    assert resp.status_code == 200
    pairs = resp.json()
    assert len(pairs) >= 1
    ids_in_pairs = {p["id_a"] for p in pairs} | {p["id_b"] for p in pairs}
    assert q_id in ids_in_pairs or q2_id in ids_in_pairs
    # Similarity must be within [0, 1]
    for p in pairs:
        assert 0.0 <= p["similarity"] <= 1.0
        assert "question_a" in p and "question_b" in p


def test_near_duplicates_excludes_rejected(app_client):
    """Rejected questions must not appear in similarity results."""
    client, q_id, _ = app_client
    conn = deps_module._service.questions._conn

    chunk_id = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()["id"]
    doc_id = conn.execute("SELECT id FROM documents LIMIT 1").fetchone()["id"]
    q2_id = str(ULID())
    conn.execute(
        "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
        "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            q2_id,
            "What is consistent hashing used for?",
            json.dumps(["Opt A", "Opt B", "Opt C", "Opt D"]),
            0, "Explanation.", "easy", doc_id, chunk_id,
            "rejected", "fp_rejected_dupe", "model", "v1",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    resp = client.get("/api/v1/questions/near-duplicates?threshold=0.1")
    assert resp.status_code == 200
    pairs = resp.json()
    # q2 is rejected — must not appear in any pair
    for p in pairs:
        assert p["id_a"] != q2_id
        assert p["id_b"] != q2_id


def test_near_duplicates_matches_naive_allpairs(app_client):
    """The inverted-index scan must return exactly what a naive O(n^2) scan would."""
    client, seed_q, doc_id = app_client
    conn = deps_module._service.questions._conn
    chunk_id = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()["id"]

    texts = [
        "consistent hashing distributes load across nodes",
        "consistent hashing spreads load across many nodes",
        "consistent hashing minimizes remapping on node changes",
        "database sharding partitions rows across shards",
        "database sharding splits rows across many shards",
        "caching reduces latency for repeated reads",
    ]
    for i, t in enumerate(texts):
        conn.execute(
            "INSERT INTO questions (id, question, options, correct_index, explanation, difficulty, "
            "source_document_id, source_chunk_id, status, fingerprint, model, prompt_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(ULID()), t, json.dumps(["A", "B", "C", "D"]), 0, "explanation.", "easy",
             doc_id, chunk_id, "generated", f"fp_nd_{i}", "m", "v1",
             datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()

    from quizzer.quiz.service import _jaccard, _tokenize

    threshold = 0.3
    rows = deps_module._service.questions.get_texts_for_similarity(None)
    toks = [(r["id"], _tokenize(r["question"])) for r in rows]
    naive = set()
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            sim = _jaccard(toks[i][1], toks[j][1])
            if sim >= threshold:
                naive.add((frozenset({toks[i][0], toks[j][0]}), round(sim, 3)))

    got = deps_module._service.find_near_duplicates(threshold, None)
    got_set = {(frozenset({p["id_a"], p["id_b"]}), p["similarity"]) for p in got}
    assert got_set == naive
    assert len(got) == len(got_set)  # no duplicate pairs


def test_near_duplicates_threshold_filters(app_client):
    """Threshold=1.0 should return zero pairs (identical text only, different fingerprints allowed)."""
    client, _, _ = app_client
    resp = client.get("/api/v1/questions/near-duplicates?threshold=1.0")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Re-ingest endpoint tests ──────────────────────────────────────────────────

def test_reingest_resolves_content_relative_path(app_client, tmp_path, monkeypatch):
    """Re-ingest must resolve the content-relative source_path and enqueue the job."""
    client, _, doc_id = app_client
    from quizzer import config
    from quizzer.quiz import router as router_mod

    # The seeded document's source_path is "test/doc.md" (relative to content_dir).
    monkeypatch.setattr(config.settings, "content_dir", tmp_path)
    article = tmp_path / "test" / "doc.md"
    article.parent.mkdir(parents=True)
    article.write_text("---\ntitle: T\nsource: s\n---\nBody.", encoding="utf-8")

    captured: dict = {}
    monkeypatch.setattr(router_mod, "_run_reingest", lambda p: captured.setdefault("path", p))

    resp = client.post(f"/api/v1/documents/{doc_id}/reingest")
    assert resp.status_code == 202
    assert resp.json()["status"] == "started"
    # The background task must receive the resolved, existing path.
    assert captured["path"] == article


def test_reingest_missing_file_returns_422(app_client, tmp_path, monkeypatch):
    client, _, doc_id = app_client
    from quizzer import config
    from quizzer.quiz import router as router_mod

    # content_dir points at an empty temp dir → the seeded "test/doc.md" resolves nowhere.
    monkeypatch.setattr(config.settings, "content_dir", tmp_path)
    monkeypatch.setattr(router_mod, "_run_reingest", lambda p: None)

    resp = client.post(f"/api/v1/documents/{doc_id}/reingest")
    assert resp.status_code == 422


def test_reingest_unknown_document_returns_404(app_client):
    client, _, _ = app_client
    resp = client.post("/api/v1/documents/nonexistent/reingest")
    assert resp.status_code == 404


def _reingest_article(tmp_path, monkeypatch):
    """Point content_dir at tmp_path and create the seeded document's source file."""
    from quizzer import config
    monkeypatch.setattr(config.settings, "content_dir", tmp_path)
    article = tmp_path / "test" / "doc.md"
    article.parent.mkdir(parents=True)
    article.write_text("---\ntitle: T\nsource: s\n---\nBody.", encoding="utf-8")
    return article


def test_reingest_conflict_while_already_running(app_client, tmp_path, monkeypatch):
    """A second re-ingest for the same document must 409 while one is in flight."""
    client, _, doc_id = app_client
    from quizzer.quiz import router as router_mod
    _reingest_article(tmp_path, monkeypatch)
    monkeypatch.setattr(router_mod, "_run_reingest", lambda p: None)

    assert router_mod._try_claim_reingest(doc_id)  # simulate an in-flight run
    try:
        resp = client.post(f"/api/v1/documents/{doc_id}/reingest")
        assert resp.status_code == 409
    finally:
        router_mod._release_reingest(doc_id)

    # Once released, re-ingest is accepted again (and releases itself).
    assert client.post(f"/api/v1/documents/{doc_id}/reingest").status_code == 202
    assert client.post(f"/api/v1/documents/{doc_id}/reingest").status_code == 202


def test_reingest_failure_is_logged(app_client, tmp_path, monkeypatch, caplog):
    """A failing ingest subprocess must leave a trace in the server log."""
    import subprocess as subprocess_mod

    client, _, doc_id = app_client
    from quizzer.quiz import router as router_mod
    _reingest_article(tmp_path, monkeypatch)

    def fake_run(*args, **kwargs):
        return subprocess_mod.CompletedProcess(
            args, returncode=1, stdout="", stderr="boom: ingest exploded"
        )

    monkeypatch.setattr(router_mod.subprocess, "run", fake_run)
    with caplog.at_level("ERROR"):
        resp = client.post(f"/api/v1/documents/{doc_id}/reingest")
    assert resp.status_code == 202
    assert "boom: ingest exploded" in caplog.text


def _jaccard_and_tokenize():
    """Import helpers for unit-level testing."""
    from quizzer.quiz.service import _tokenize, _jaccard
    return _tokenize, _jaccard


def test_tokenize_removes_stopwords_and_short_tokens():
    _tokenize, _ = _jaccard_and_tokenize()
    tokens = _tokenize("What is the best way to use caching?")
    assert "caching" in tokens
    assert "the" not in tokens   # stopword
    assert "is" not in tokens    # too short (< 3 chars)
    assert "way" in tokens


def test_jaccard_identical():
    _tokenize, _jaccard = _jaccard_and_tokenize()
    t = _tokenize("consistent hashing distributes load evenly")
    assert _jaccard(t, t) == 1.0


def test_jaccard_disjoint():
    _tokenize, _jaccard = _jaccard_and_tokenize()
    a = _tokenize("consistent hashing ring")
    b = _tokenize("database sharding partition")
    assert _jaccard(a, b) == 0.0


def test_jaccard_partial():
    _tokenize, _jaccard = _jaccard_and_tokenize()
    a = _tokenize("consistent hashing distributes load")
    b = _tokenize("consistent hashing reduces latency")
    sim = _jaccard(a, b)
    assert 0.0 < sim < 1.0
