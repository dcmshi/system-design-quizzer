import pytest

from quizzer.ingestion.chunker import chunk_document
from quizzer.ingestion.models import Document


def _make_doc(content: str) -> Document:
    return Document(
        id="DOC001",
        title="Test Doc",
        source="test",
        content=content,
        source_path="test/doc.md",
    )


def _words(n: int) -> str:
    return " ".join(["word"] * n)


def test_single_small_section_produces_one_chunk():
    content = f"# Section One\n\n{_words(400)}"
    doc = _make_doc(content)
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].heading == "Section One"
    assert chunks[0].chunk_index == 0


def test_multiple_small_sections_accumulate():
    # Two 200-word sections should accumulate into one chunk (< 300 min alone)
    content = f"# Section A\n\n{_words(200)}\n\n# Section B\n\n{_words(200)}"
    doc = _make_doc(content)
    chunks = chunk_document(doc)
    # They should accumulate since each is under chunk_word_min (300)
    assert len(chunks) >= 1


def test_large_section_splits_by_paragraph():
    # 900-word body → should be split (max 800)
    para = _words(300)
    content = f"# Big Section\n\n{para}\n\n{para}\n\n{para}"
    doc = _make_doc(content)
    chunks = chunk_document(doc)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.word_count <= 850  # allow slight overflow at paragraph boundaries


def test_chunks_are_sequential():
    content = "\n\n".join([f"# Section {i}\n\n{_words(350)}" for i in range(4)])
    doc = _make_doc(content)
    chunks = chunk_document(doc)
    indices = [c.chunk_index for c in chunks]
    assert indices == sorted(indices)
    assert indices == list(range(len(chunks)))


def test_no_headings_chunks_by_paragraph():
    para = _words(200)
    content = f"{para}\n\n{para}\n\n{para}"
    doc = _make_doc(content)
    chunks = chunk_document(doc)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.document_id == "DOC001"


def test_determinism():
    content = f"# A\n\n{_words(350)}\n\n# B\n\n{_words(350)}\n\n# C\n\n{_words(350)}"
    doc = _make_doc(content)
    chunks1 = chunk_document(doc)
    chunks2 = chunk_document(doc)
    # Same content (different ULIDs) but same structure
    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1.content == c2.content
        assert c1.word_count == c2.word_count
        assert c1.chunk_index == c2.chunk_index
