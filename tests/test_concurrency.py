"""Concurrency hardening: per-thread SQLite connections for the shared services."""

from __future__ import annotations

import threading
from pathlib import Path

from ulid import ULID

from quizzer import database
from quizzer.config import settings
from quizzer.database import get_shared_connection
from quizzer.ingestion.models import Document
from quizzer.storage.document_repo import DocumentRepository


def test_get_shared_connection_is_per_thread(tmp_path: Path, monkeypatch):
    db = tmp_path / "shared.db"
    database.init_db(db)
    monkeypatch.setattr(settings, "db_path", db)

    ids: dict[int, int] = {}

    def worker() -> None:
        c1 = get_shared_connection()
        c2 = get_shared_connection()
        # Same connection reused within a thread…
        assert c1 is c2
        ids[threading.get_ident()] = id(c1)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # …and a distinct connection object for each thread.
    assert len(ids) == 6
    assert len(set(ids.values())) == 6


def test_repos_without_injected_conn_are_thread_safe(tmp_path: Path, monkeypatch):
    """The production wiring (repos with no explicit conn) must handle concurrent
    writers without 'database is locked' or cross-thread connection errors."""
    db = tmp_path / "concurrent_writes.db"
    database.init_db(db)
    monkeypatch.setattr(settings, "db_path", db)

    n = 12
    errors: list[Exception] = []
    conns: list = []  # hold strong refs so ids stay stable (no GC id-reuse)
    lock = threading.Lock()

    def writer(i: int) -> None:
        try:
            repo = DocumentRepository()  # no explicit conn -> per-thread connection
            conn = repo._conn
            with lock:
                conns.append(conn)
            repo.upsert(
                Document(
                    id=str(ULID()),
                    title=f"Doc {i}",
                    source="test",
                    content="c",
                    source_path=f"t/doc-{i}.md",
                )
            )
        except Exception as exc:  # noqa: BLE001 - surface any threading/db error
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # Each thread used its own distinct connection object (all kept alive above).
    assert len(conns) == n
    assert len({id(c) for c in conns}) == n
    # Every concurrent write is durable and visible from a fresh reader.
    docs = DocumentRepository(database.get_connection(db)).list_all()
    assert len(docs) == n
