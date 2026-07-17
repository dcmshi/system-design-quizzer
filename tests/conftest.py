import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quizzer.database import init_db, get_connection
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository


@pytest.fixture(autouse=True)
def _isolate_default_db(tmp_path: Path, monkeypatch):
    """Point the default DB path at a temp file so code that falls back to
    settings.db_path (e.g. the app lifespan's init_db) never touches the
    real data/quizzer.db during tests."""
    from quizzer.config import settings
    monkeypatch.setattr(settings, "db_path", tmp_path / "default-test.db")


@pytest.fixture()
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    """In-memory-equivalent SQLite DB using a temp file."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return get_connection(db_path)


@pytest.fixture()
def doc_repo(db_conn: sqlite3.Connection) -> DocumentRepository:
    return DocumentRepository(db_conn)


@pytest.fixture()
def q_repo(db_conn: sqlite3.Connection) -> QuestionRepository:
    return QuestionRepository(db_conn)


@pytest.fixture()
def mock_ollama_client():
    """Mock OllamaClient that returns a preset JSON response."""
    client = MagicMock()
    client.model = "mock-model"
    client.generate.return_value = """{
        "questions": [
            {
                "question": "What is the primary purpose of consistent hashing?",
                "options": [
                    "To minimize data replication",
                    "To distribute load evenly while minimizing remapping on node changes",
                    "To encrypt data at rest",
                    "To ensure sequential read performance"
                ],
                "correct_index": 1,
                "explanation": "Consistent hashing places both data and nodes on a ring so that adding or removing a node only affects its immediate neighbors, minimizing remapping.",
                "difficulty": "medium",
                "source_chunk_id": "CHUNK001"
            }
        ]
    }"""
    client.health_check.return_value = True
    return client
