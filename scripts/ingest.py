"""CLI: ingest .md articles → generate MCQs → store in SQLite."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make sure src/ is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ulid import ULID

from quizzer.config import settings
from quizzer.database import init_db, get_connection
from quizzer.generation.generator import MCQGenerator
from quizzer.generation.ollama_client import OllamaClient
from quizzer.ingestion.chunker import chunk_document
from quizzer.ingestion.loader import load_document
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository
from quizzer.validation.duplicate_detector import fingerprint, is_duplicate
from quizzer.validation.normalizer import normalize_mcq
from quizzer.validation.schema_validator import validate_mcq


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest articles and generate MCQs")
    parser.add_argument(
        "--source",
        type=Path,
        help="Path to a single .md file or a directory. Defaults to content_dir.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if document already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without writing to DB",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override Ollama model (default from config)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all ingested documents with question counts and exit",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show DB summary statistics (counts by status/difficulty) and exit",
    )
    return parser.parse_args()


def collect_md_files(source: Path | None) -> list[Path]:
    base = source or settings.content_dir
    if base.is_file():
        return [base]
    if base.is_dir():
        return sorted(base.rglob("*.md"))
    return []


def cmd_list(doc_repo: DocumentRepository, q_repo: QuestionRepository) -> None:
    docs = doc_repo.list_all()
    if not docs:
        print("No documents ingested yet.")
        return
    print(f"Documents in DB ({len(docs)}):\n")
    for doc in docs:
        q_count = q_repo.count_by_document(doc.id)
        tags = ", ".join(doc.tags) if doc.tags else "—"
        print(f"  {doc.title}")
        print(f"    source   : {doc.source}")
        print(f"    path     : {doc.source_path}")
        print(f"    tags     : {tags}")
        print(f"    questions: {q_count}")
        print()


def cmd_stats(doc_repo: DocumentRepository, q_repo: QuestionRepository) -> None:
    docs = doc_repo.list_all()
    total_docs = len(docs)
    total_questions = sum(q_repo.count_by_document(d.id) for d in docs)
    by_status = q_repo.counts_by_status()
    by_diff = q_repo.counts_by_difficulty()

    print("=== Database Summary ===\n")
    print(f"  Documents  : {total_docs}")
    print(f"  Questions  : {total_questions}")

    print("\n  By status:")
    for status in ("generated", "approved", "edited", "rejected"):
        print(f"    {status:<12}: {by_status.get(status, 0)}")

    print("\n  By difficulty:")
    for diff in ("easy", "medium", "hard"):
        print(f"    {diff:<12}: {by_diff.get(diff, 0)}")
    print()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    log = logging.getLogger("ingest")

    init_db()
    conn = get_connection()
    doc_repo = DocumentRepository(conn)
    q_repo = QuestionRepository(conn)

    # Read-only commands — exit before touching Ollama
    if args.list:
        cmd_list(doc_repo, q_repo)
        sys.exit(0)
    if args.stats:
        cmd_stats(doc_repo, q_repo)
        sys.exit(0)

    model = args.model or settings.ollama_model
    ollama = OllamaClient(model=model)

    log.info("Checking Ollama at %s …", settings.ollama_base_url)
    if not ollama.health_check():
        log.error("Ollama is not reachable at %s — aborting", settings.ollama_base_url)
        sys.exit(1)
    log.info("Ollama OK (model=%s)", model)

    # Load existing fingerprints once
    existing_fingerprints: set[str] = q_repo.get_all_fingerprints()

    files = collect_md_files(args.source)
    if not files:
        log.warning("No .md files found in %s", args.source or settings.content_dir)
        sys.exit(0)

    generator = MCQGenerator(ollama)

    stats = {"documents": 0, "chunks": 0, "questions": 0, "skipped_docs": 0, "skipped_q": 0}

    for md_path in files:
        log.info("Processing %s", md_path)
        try:
            doc = load_document(md_path)
        except Exception as exc:
            log.error("Failed to load %s: %s", md_path, exc)
            continue

        existing = doc_repo.get_by_source_path(doc.source_path)
        if existing and not args.force:
            log.info("  Already ingested (source_path=%s) — skipping (use --force)", doc.source_path)
            stats["skipped_docs"] += 1
            continue

        # Preserve the stored document ID so chunks' foreign key stays valid
        if existing:
            doc.id = existing.id

        chunks = chunk_document(doc)
        log.info("  %d chunk(s) from '%s'", len(chunks), doc.title)

        if not args.dry_run:
            doc_repo.upsert(doc)
            for chunk in chunks:
                doc_repo.upsert_chunk(chunk)

        stats["documents"] += 1
        stats["chunks"] += len(chunks)

        for chunk in chunks:
            log.debug("    Chunk %d (%d words) → generating …", chunk.chunk_index, chunk.word_count)
            try:
                result = generator.generate_for_chunk(chunk, doc.id)
            except Exception as exc:
                log.error("    Generation failed for chunk %s: %s", chunk.id, exc)
                continue

            for raw_mcq in result.questions:
                mcq = normalize_mcq(raw_mcq)
                errors = validate_mcq(mcq)
                if errors:
                    log.warning("    Validation failed: %s", errors)
                    continue

                fp = fingerprint(mcq.question)
                if is_duplicate(mcq.question, existing_fingerprints):
                    log.debug("    Duplicate question skipped")
                    stats["skipped_q"] += 1
                    continue

                if not args.dry_run:
                    try:
                        q_repo.insert(
                            id=str(ULID()),
                            question=mcq.question,
                            options=mcq.options,
                            correct_index=mcq.correct_index,
                            explanation=mcq.explanation,
                            difficulty=mcq.difficulty,
                            source_document_id=doc.id,
                            source_chunk_id=chunk.id,
                            fingerprint=fp,
                            model=result.model,
                            prompt_version=result.prompt_version,
                            created_at=datetime.now(timezone.utc).isoformat(),
                        )
                    except Exception as exc:
                        log.error("    Insert failed: %s", exc)
                        continue

                existing_fingerprints.add(fp)
                stats["questions"] += 1
                log.debug("    + question: %s", mcq.question[:60])

    ollama.close()

    print("\n=== Ingestion Summary ===")
    print(f"  Documents ingested : {stats['documents']}")
    print(f"  Documents skipped  : {stats['skipped_docs']}")
    print(f"  Chunks processed   : {stats['chunks']}")
    print(f"  Questions stored   : {stats['questions']}")
    print(f"  Duplicates skipped : {stats['skipped_q']}")
    if args.dry_run:
        print("  (DRY RUN — nothing written to DB)")


if __name__ == "__main__":
    main()
