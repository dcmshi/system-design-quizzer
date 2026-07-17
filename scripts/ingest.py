"""CLI: ingest .md articles → generate MCQs → store in SQLite."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make sure src/ is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ulid import ULID

from quizzer.config import settings
from quizzer.database import init_db, get_connection
from quizzer.generation.factory import create_llm_client
from quizzer.generation.gemini_client import GeminiClient
from quizzer.generation.generator import MCQGenerator
from quizzer.generation.ollama_client import OllamaClient
from quizzer.ingestion.chunker import chunk_document
from quizzer.ingestion.loader import load_document, resolve_source_path
from quizzer.storage.document_repo import DocumentRepository
from quizzer.storage.question_repo import QuestionRepository
from quizzer.validation.duplicate_detector import fingerprint
from quizzer.validation.normalizer import normalize_mcq
from quizzer.validation.schema_validator import validate_mcq


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest articles and generate MCQs")
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        dest="sources",
        metavar="PATH",
        help="Path to a .md file or directory (repeatable). Defaults to content_dir.",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Re-ingest documents already tracked in the DB (use with --force and optionally --tag).",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="With --from-db: only re-ingest documents that have this tag.",
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
        help="Override LLM model name (default from config)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=["gemini", "ollama", "auto"],
        help="LLM provider: gemini, ollama, or auto (default from config)",
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


def _format_eta(chunk_times: list[float], remaining: int) -> str:
    """Return a human-readable ETA based on average chunk time so far."""
    if not chunk_times or remaining == 0:
        return ""
    avg = sum(chunk_times) / len(chunk_times)
    eta_s = int(avg * remaining)
    if eta_s < 60:
        return f"ETA ~{eta_s}s"
    return f"ETA ~{eta_s // 60}m {eta_s % 60:02d}s"


def collect_md_files(sources: list[Path] | None) -> list[Path]:
    """Collect .md files from a list of paths (files or dirs). Deduplicates, preserves sort order."""
    if not sources:
        sources = [settings.content_dir]
    seen: set[Path] = set()
    result: list[Path] = []
    for source in sources:
        if source.is_file():
            candidates = [source]
        elif source.is_dir():
            candidates = sorted(source.rglob("*.md"))
        else:
            candidates = []
        for p in candidates:
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(p)
    return result


def collect_md_files_from_db(doc_repo: DocumentRepository, tag: str | None) -> list[Path]:
    """Resolve .md file paths from documents already in the DB, optionally filtered by tag."""
    docs = doc_repo.list_all()
    if tag:
        docs = [d for d in docs if tag in (d.tags or [])]
    paths: list[Path] = []
    for doc in docs:
        p = resolve_source_path(doc.source_path)
        if p.exists():
            paths.append(p)
    return paths


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

    client = create_llm_client(provider=args.provider, model=args.model)
    log.info("LLM provider: %s (model=%s)", type(client).__name__, client.model)

    if not client.health_check():
        if isinstance(client, GeminiClient):
            log.warning("Gemini unreachable — falling back to Ollama …")
            client = OllamaClient(model=args.model or settings.ollama_model)
            if not client.health_check():
                log.error("Ollama fallback also unreachable at %s — aborting", settings.ollama_base_url)
                sys.exit(1)
            log.info("Ollama fallback OK (model=%s)", client.model)
        else:
            log.error("Ollama not reachable at %s — aborting", settings.ollama_base_url)
            sys.exit(1)
    else:
        log.info("LLM ready (model=%s)", client.model)

    # Load existing fingerprints once
    existing_fingerprints: set[str] = q_repo.get_all_fingerprints()

    if args.from_db:
        files = collect_md_files_from_db(doc_repo, tag=args.tag)
        if not files:
            tag_hint = f" with tag '{args.tag}'" if args.tag else ""
            log.warning("No DB documents found%s with resolvable source paths", tag_hint)
            sys.exit(0)
        log.info("--from-db: %d document(s) selected%s", len(files), f" (tag={args.tag})" if args.tag else "")
    else:
        files = collect_md_files(args.sources)
        if not files:
            log.warning("No .md files found in %s", args.sources or settings.content_dir)
            sys.exit(0)

    generator = MCQGenerator(client)

    stats = {"documents": 0, "chunks": 0, "chunks_failed": 0, "questions": 0, "skipped_docs": 0, "skipped_q": 0}

    total_files = len(files)

    for file_idx, md_path in enumerate(files, 1):
        try:
            doc = load_document(md_path)
        except Exception as exc:
            log.error("Failed to load %s: %s", md_path, exc)
            continue

        existing = doc_repo.get_by_source_path(doc.source_path)
        if existing and not args.force:
            print(f"[{file_idx}/{total_files}] '{doc.title}' — already ingested, skipping")
            stats["skipped_docs"] += 1
            continue

        # Preserve the stored document ID so chunks' foreign key stays valid
        if existing:
            doc.id = existing.id

        chunks = chunk_document(doc)
        n_chunks = len(chunks)
        print(f"\n[{file_idx}/{total_files}] '{doc.title}'  ({n_chunks} chunk(s))")

        if not args.dry_run:
            doc_repo.upsert(doc)
            if existing:
                # Drop the previous run's chunks that produced no surviving
                # questions, so chunk/word counts don't inflate on re-ingest.
                removed = doc_repo.delete_orphan_chunks(doc.id)
                if removed:
                    log.debug("Removed %d orphan chunk(s) from previous ingest", removed)
            for chunk in chunks:
                doc_repo.upsert_chunk(chunk)

        stats["documents"] += 1
        stats["chunks"] += n_chunks

        chunk_times: list[float] = []

        for i, chunk in enumerate(chunks, 1):
            n_added = 0
            heading = (chunk.heading or f"chunk {i}")[:32]
            eta = _format_eta(chunk_times, n_chunks - i)
            prefix = f"  [{i}/{n_chunks}] {heading:<32} {chunk.word_count:>4}w"
            print(f"{prefix}  generating…  {eta:<10}", end="\r", flush=True)

            log.debug("Chunk %d (%d words) → generating …", chunk.chunk_index, chunk.word_count)
            t0 = time.monotonic()
            try:
                result = generator.generate_for_chunk(chunk, doc.id)
            except Exception as exc:
                elapsed = time.monotonic() - t0
                chunk_times.append(elapsed)
                log.error("Generation failed for chunk %s: %s", chunk.id, exc)
                print(f"{prefix}  FAILED        {elapsed:.1f}s{' ' * 10}")
                stats["chunks_failed"] += 1
                continue

            elapsed = time.monotonic() - t0
            chunk_times.append(elapsed)

            for raw_mcq in result.questions:
                mcq = normalize_mcq(raw_mcq)
                errors = validate_mcq(mcq)
                if errors:
                    log.warning("Validation failed: %s", errors)
                    continue

                fp = fingerprint(mcq.question)
                if fp in existing_fingerprints:
                    log.debug("Duplicate question skipped")
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
                        log.error("Insert failed: %s", exc)
                        continue

                existing_fingerprints.add(fp)
                stats["questions"] += 1
                n_added += 1
                log.debug("+ question: %s", mcq.question[:60])

            print(f"{prefix}  {n_added} Q        {elapsed:.1f}s{' ' * 10}")

    client.close()

    print("\n=== Ingestion Summary ===")
    print(f"  Documents ingested : {stats['documents']}")
    print(f"  Documents skipped  : {stats['skipped_docs']}")
    print(f"  Chunks processed   : {stats['chunks']}")
    print(f"  Chunks failed      : {stats['chunks_failed']}")
    print(f"  Questions stored   : {stats['questions']}")
    print(f"  Duplicates skipped : {stats['skipped_q']}")
    if args.dry_run:
        print("  (DRY RUN — nothing written to DB)")


if __name__ == "__main__":
    main()
