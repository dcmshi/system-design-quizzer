"""Compare MCQ output quality across multiple Ollama models on a single document.

Usage:
    uv run python scripts/compare_models.py \\
        --source content/bytebytego/consistent-hashing.md \\
        --models llama3.2 mistral

Optional:
    --chunks N   Only run on the first N chunks (handy for a quick sanity-check)

Nothing is written to the DB — this is always a dry run.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quizzer.generation.generator import MCQGenerator
from quizzer.generation.ollama_client import OllamaClient
from quizzer.ingestion.chunker import chunk_document
from quizzer.ingestion.loader import load_document
from quizzer.ingestion.models import Chunk
from quizzer.validation.normalizer import normalize_mcq
from quizzer.validation.schema_validator import validate_mcq

LABELS = "ABCD"
WIDTH = 62


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class QuestionResult:
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    difficulty: str
    valid: bool
    errors: list[str]


@dataclass
class ModelChunkResult:
    model: str
    chunk_index: int
    questions: list[QuestionResult] = field(default_factory=list)
    parse_failed: bool = False
    elapsed: float = 0.0


@dataclass
class ModelSummary:
    model: str
    valid: int = 0
    invalid: int = 0
    parse_errors: int = 0
    elapsed: float = 0.0


# ── Formatting helpers ────────────────────────────────────────────────────────

def _rule(char: str = "─") -> str:
    return char * WIDTH


def _print_question(q: QuestionResult, num: int) -> None:
    status = "✓" if q.valid else "✗"
    print(f"  Q{num} [{q.difficulty}] {status}  {q.question}")
    for i, opt in enumerate(q.options):
        marker = " ✓" if i == q.correct_index else "  "
        print(f"       {LABELS[i]}.{marker} {opt}")
    expl = q.explanation
    if len(expl) > 120:
        expl = expl[:117] + "…"
    print(f"       → {expl}")
    if not q.valid:
        for err in q.errors:
            print(f"       ⚠ {err}")
    print()


def _print_model_section(result: ModelChunkResult) -> None:
    header = f" {result.model} "
    side = (WIDTH - len(header) - 2) // 2
    print(f"  {'─' * side}{header}{'─' * (WIDTH - side - len(header) - 2)}")
    if result.parse_failed:
        print("  (parse failed — no questions)\n")
        return
    if not result.questions:
        print("  (no questions generated)\n")
        return
    print()
    for i, q in enumerate(result.questions, 1):
        _print_question(q, i)


# ── Core logic ────────────────────────────────────────────────────────────────

def run_model_on_chunk(
    model: str, chunk: Chunk, generator: MCQGenerator
) -> ModelChunkResult:
    result = ModelChunkResult(model=model, chunk_index=chunk.chunk_index)
    t0 = time.monotonic()
    try:
        gen = generator.generate_for_chunk(chunk, document_id="compare")
    except Exception as exc:
        result.parse_failed = True
        result.elapsed = time.monotonic() - t0
        print(f"  [{model}] ERROR: {exc}")
        return result

    result.elapsed = time.monotonic() - t0

    for raw in gen.questions:
        mcq = normalize_mcq(raw)
        errors = validate_mcq(mcq)
        result.questions.append(QuestionResult(
            question=mcq.question,
            options=mcq.options,
            correct_index=mcq.correct_index,
            explanation=mcq.explanation,
            difficulty=mcq.difficulty,
            valid=len(errors) == 0,
            errors=errors,
        ))

    return result


def compare(source: Path, models: list[str], max_chunks: int | None) -> None:
    # ── Load document ──────────────────────────────────────────────────────
    try:
        doc = load_document(source)
    except Exception as exc:
        print(f"Error loading {source}: {exc}", file=sys.stderr)
        sys.exit(1)

    chunks = chunk_document(doc)
    if max_chunks is not None:
        chunks = chunks[:max_chunks]

    n_chunks = len(chunks)
    print(f"\nComparing {len(models)} models on \"{doc.title}\"")
    print(f"{n_chunks} chunk(s)  ·  {len(models)} model(s)\n")

    # ── Health-check all models upfront ───────────────────────────────────
    clients: dict[str, OllamaClient] = {}
    for model in models:
        client = OllamaClient(model=model)
        if not client.health_check():
            print(f"Error: Ollama is not reachable. Is it running?", file=sys.stderr)
            sys.exit(1)
        clients[model] = client

    # ── Verify models exist ────────────────────────────────────────────────
    # (a bad model name gives a 404 on the first generate call; we catch it then)

    summaries: dict[str, ModelSummary] = {m: ModelSummary(model=m) for m in models}

    # ── Per-chunk loop ─────────────────────────────────────────────────────
    for ci, chunk in enumerate(chunks, 1):
        heading = chunk.heading or f"chunk {ci}"
        print(_rule("━"))
        print(f"Chunk {ci}/{n_chunks}: \"{heading}\" ({chunk.word_count} words)")
        print(_rule("━"))
        print()

        for model in models:
            generator = MCQGenerator(clients[model])
            print(f"  [{model}] generating…", end="\r", flush=True)
            result = run_model_on_chunk(model, chunk, generator)
            print(" " * 50, end="\r")  # clear the line

            _print_model_section(result)

            s = summaries[model]
            s.elapsed += result.elapsed
            if result.parse_failed:
                s.parse_errors += 1
            for q in result.questions:
                if q.valid:
                    s.valid += 1
                else:
                    s.invalid += 1

    # ── Close clients ──────────────────────────────────────────────────────
    for client in clients.values():
        client.close()

    # ── Summary table ──────────────────────────────────────────────────────
    print(_rule("━"))
    print("Summary")
    print(_rule("━"))
    print(f"  {'Model':<20} {'Valid Qs':>8} {'Invalid':>8} {'Parse errs':>11} {'Time':>7}")
    print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*11} {'─'*7}")
    for model in models:
        s = summaries[model]
        total = s.valid + s.invalid
        print(
            f"  {model:<20} {s.valid:>8} {s.invalid:>8} {s.parse_errors:>11} {s.elapsed:>6.1f}s"
        )
    print()

    best_valid = max(summaries.values(), key=lambda s: s.valid)
    best_time  = min(summaries.values(), key=lambda s: s.elapsed)
    if best_valid.model == best_time.model:
        print(f"  → {best_valid.model} leads on both question count and speed.")
    else:
        print(f"  → Most questions : {best_valid.model} ({best_valid.valid} valid)")
        print(f"  → Fastest        : {best_time.model} ({best_time.elapsed:.1f}s)")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare MCQ generation quality across Ollama models (dry run, no DB writes)"
    )
    parser.add_argument(
        "--source", type=Path, required=True,
        help="Path to a single .md article",
    )
    parser.add_argument(
        "--models", nargs="+", required=True, metavar="MODEL",
        help="Two or more Ollama model names to compare (e.g. llama3.2 mistral)",
    )
    parser.add_argument(
        "--chunks", type=int, default=None, metavar="N",
        help="Only process the first N chunks (default: all)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if len(args.models) < 2:
        print("Error: --models requires at least two model names", file=sys.stderr)
        sys.exit(1)
    compare(args.source, args.models, args.chunks)
