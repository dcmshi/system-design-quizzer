import re

from ulid import ULID

from quizzer.config import settings
from quizzer.ingestion.models import Chunk, Document

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _word_count(text: str) -> int:
    return len(text.split())


def _split_by_paragraphs(text: str, heading: str | None, doc_id: str, start_index: int) -> list[Chunk]:
    """Split oversized text into paragraph-bounded chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buf_words = 0
    chunk_index = start_index

    for para in paragraphs:
        pw = _word_count(para)
        if buf_words + pw > settings.chunk_word_max and buffer:
            chunk_text = "\n\n".join(buffer)
            chunks.append(
                Chunk(
                    id=str(ULID()),
                    document_id=doc_id,
                    content=chunk_text,
                    word_count=_word_count(chunk_text),
                    chunk_index=chunk_index,
                    heading=heading,
                )
            )
            chunk_index += 1
            buffer = [para]
            buf_words = pw
        else:
            buffer.append(para)
            buf_words += pw

    if buffer:
        chunk_text = "\n\n".join(buffer)
        chunks.append(
            Chunk(
                id=str(ULID()),
                document_id=doc_id,
                content=chunk_text,
                word_count=_word_count(chunk_text),
                chunk_index=chunk_index,
                heading=heading,
            )
        )

    return chunks


def chunk_document(doc: Document) -> list[Chunk]:
    text = doc.content

    # Find all heading positions
    heading_matches = list(_HEADING_RE.finditer(text))

    if not heading_matches:
        # No headings — chunk by paragraph grouping
        return _split_by_paragraphs(text, heading=None, doc_id=doc.id, start_index=0)

    # Build sections: list of (heading_text, section_body)
    sections: list[tuple[str | None, str]] = []

    # Content before the first heading
    preamble = text[: heading_matches[0].start()].strip()
    if preamble:
        sections.append((None, preamble))

    for i, match in enumerate(heading_matches):
        heading_text = match.group(1).strip()
        body_start = match.end()
        body_end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((heading_text, body))

    # Accumulate sections into chunks respecting word count bounds
    chunks: list[Chunk] = []
    carry_texts: list[str] = []
    carry_heading: str | None = None
    carry_words = 0
    chunk_index = 0

    def _flush_carry() -> None:
        nonlocal carry_texts, carry_heading, carry_words, chunk_index
        if not carry_texts:
            return
        chunk_text = "\n\n".join(carry_texts)
        wc = _word_count(chunk_text)
        # Oversized — split further
        if wc > settings.chunk_word_max:
            sub = _split_by_paragraphs(chunk_text, carry_heading, doc.id, chunk_index)
            chunks.extend(sub)
            chunk_index += len(sub)
        else:
            chunks.append(
                Chunk(
                    id=str(ULID()),
                    document_id=doc.id,
                    content=chunk_text,
                    word_count=wc,
                    chunk_index=chunk_index,
                    heading=carry_heading,
                )
            )
            chunk_index += 1
        carry_texts = []
        carry_heading = None
        carry_words = 0

    for heading, body in sections:
        if not body:
            continue
        body_words = _word_count(body)

        # Body alone exceeds max — flush carry then split body directly
        if body_words > settings.chunk_word_max:
            _flush_carry()
            sub = _split_by_paragraphs(body, heading, doc.id, chunk_index)
            chunks.extend(sub)
            chunk_index += len(sub)
            continue

        # Adding body to carry would exceed max — flush first
        if carry_words + body_words > settings.chunk_word_max and carry_words >= settings.chunk_word_min:
            _flush_carry()

        # If carry is empty, set heading from this section
        if not carry_texts:
            carry_heading = heading

        carry_texts.append(body)
        carry_words += body_words

        # Carry reached minimum — eligible to flush on next oversized addition
        # Only force-flush if we're already at max
        if carry_words >= settings.chunk_word_max:
            _flush_carry()

    _flush_carry()

    # If nothing was produced (all empty bodies), return empty
    return chunks
