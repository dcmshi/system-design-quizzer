"""Tests for DocumentRepository — orphan chunk cleanup on re-ingest."""

from datetime import datetime, timezone

from quizzer.ingestion.models import Chunk, Document


def _make_doc(doc_repo, doc_id: str, source_path: str) -> Document:
    doc = Document(
        id=doc_id,
        title="Doc " + doc_id,
        source="test",
        content="Content.",
        source_path=source_path,
    )
    doc_repo.upsert(doc)
    return doc


def _make_chunk(doc_repo, chunk_id: str, doc_id: str) -> Chunk:
    chunk = Chunk(
        id=chunk_id, document_id=doc_id, content="Chunk.", word_count=1, chunk_index=0
    )
    doc_repo.upsert_chunk(chunk)
    return chunk


def _make_question(q_repo, q_id: str, doc_id: str, chunk_id: str) -> None:
    q_repo.insert(
        id=q_id,
        question="What is X?",
        options=["A", "B", "C", "D"],
        correct_index=0,
        explanation="Because A is the right answer here.",
        difficulty="easy",
        source_document_id=doc_id,
        source_chunk_id=chunk_id,
        fingerprint="fp_" + q_id,
        model="m",
        prompt_version="v1",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_delete_orphan_chunks_removes_only_unreferenced(doc_repo, q_repo):
    _make_doc(doc_repo, "DOC1", "a/doc1.md")
    _make_chunk(doc_repo, "CH_REFERENCED", "DOC1")
    _make_chunk(doc_repo, "CH_ORPHAN", "DOC1")
    _make_question(q_repo, "Q1", "DOC1", "CH_REFERENCED")

    removed = doc_repo.delete_orphan_chunks("DOC1")

    assert removed == 1
    remaining = {c.id for c in doc_repo.list_chunks("DOC1")}
    assert remaining == {"CH_REFERENCED"}


def test_delete_orphan_chunks_scoped_to_document(doc_repo, q_repo):
    _make_doc(doc_repo, "DOC1", "a/doc1.md")
    _make_doc(doc_repo, "DOC2", "a/doc2.md")
    _make_chunk(doc_repo, "CH_D1_ORPHAN", "DOC1")
    _make_chunk(doc_repo, "CH_D2_ORPHAN", "DOC2")

    removed = doc_repo.delete_orphan_chunks("DOC1")

    assert removed == 1
    assert {c.id for c in doc_repo.list_chunks("DOC2")} == {"CH_D2_ORPHAN"}
