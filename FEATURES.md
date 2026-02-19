# FEATURES.md — Work Left To Do

Tracks planned capabilities, known gaps, and quality improvements.
Items are grouped by theme and roughly ordered by value vs effort.

---

## Ingestion

### Multi-source ingestion
Support ingesting from multiple formats beyond Markdown:
- PDF documents (e.g. whitepapers, research papers)
- HTML pages (saved locally, not scraped live)
- Plain `.txt` files

Each format needs its own loader that produces a normalized `Document`.
The `load_document()` interface should dispatch by file extension.

### Batch ingestion report
`scripts/ingest.py` currently prints a summary at the end.
Extend it to write a structured JSON report (`data/ingest_report_<timestamp>.json`)
with per-file outcomes: chunks produced, questions generated, questions rejected (and why).
Useful for auditing generation quality over time.

### Frontmatter validation
Currently missing frontmatter fields are silently defaulted.
Add a strict mode (`--strict`) that rejects articles with missing `title` or `source`.

---

## Generation

### Hosted model fallback
When Ollama is unreachable, fall back to a hosted provider (e.g. Anthropic API).
The `OllamaClient` interface should be abstracted behind a `BaseLLMClient` protocol
so alternate backends can be swapped in via config.

### Prompt versioning system
`PROMPT_V1` is a string constant. As prompts evolve, we need a way to:
- Track which prompt version produced each question (already stored in `questions.prompt_version`)
- Regenerate questions produced by outdated prompts (`--regen-prompt-version v1`)

### Retry on generation failure
`generator.py` currently logs a warning and returns `[]` on parse failure.
Add configurable retry logic (e.g. up to 2 retries) before giving up, with exponential backoff.

### Async generation pipeline
The ingest script is synchronous. For large content libraries, switch to
`asyncio` + `httpx.AsyncClient` to generate questions for multiple chunks concurrently.

---

## Validation

### Semantic deduplication
Current deduplication is exact (SHA-256 of normalized question text).
Add fuzzy/semantic deduplication using sentence embeddings (e.g. via a local
embedding model through Ollama) to catch near-duplicate questions that pass
the fingerprint check.

### Question quality scoring
After validation, score each question on:
- Distractor plausibility (are wrong options clearly distinct and non-trivial?)
- Question clarity (readability score)
- Explanation quality (does it reference the source content?)

Store as `quality_score REAL` in the `questions` table.
Low-scoring questions could be auto-flagged for review rather than discarded outright.

### Regeneration of invalid questions
Currently invalid questions are discarded. Add a `--regen-invalid` flag to
`ingest.py` that retries generation for chunks that produced zero valid questions.

---

## Storage

### Chunk-level re-ingestion
If an article is updated (content changes), the current `--force` flag re-ingests
the whole document. Add content-hash tracking per chunk so only changed chunks
are regenerated.

### Question export
Add `scripts/export.py` to export questions in common formats:
- JSON array (portable)
- CSV (spreadsheet review)
- Anki deck format (`.apkg`) for spaced repetition

---

## API

### Pagination cursor support
`GET /questions` uses `limit`/`offset`. For large datasets, add cursor-based
pagination (`?cursor=<ulid>`) for stable page traversal.

### Question search
`GET /questions?q=<text>` — full-text search over question text using SQLite FTS5.

### Bulk status update
`POST /api/v1/questions/bulk-status` — accept a list of IDs and a target status.
Useful for batch-approving questions after human review.

### Question editing
`PUT /api/v1/questions/{id}` — allow editing question text, options, correct_index,
and explanation. Store the original generated text in a `original_question TEXT` column
and set `status = "edited"` automatically.

### Stats endpoint
`GET /api/v1/stats` — return aggregate counts:
- Total questions by difficulty
- Total questions by status
- Questions per document
- Generation model breakdown

---

## Quiz Features

### Spaced repetition support
Track per-question answer history in an `answer_history` table
(`question_id`, `selected_index`, `correct`, `answered_at`).
Use SM-2 or a similar algorithm to schedule question review.

### User performance analytics
Expose endpoints for per-session stats:
- `GET /api/v1/stats/performance` — accuracy by difficulty, weakest topics
- `GET /api/v1/sessions` — past quiz session summaries

### Quiz session model
Currently quiz is stateless (random sample per request).
Add a `quiz_sessions` table to track a set of questions, answers given,
and score for a given session.

---

## Developer Experience

### `scripts/review.py` — terminal review UI
Simple terminal interface to step through `status=generated` questions,
display each with options, and accept `a`pprove / `e`dit / `d`elete keystrokes.
Writes status updates back via the repo directly.

### Ruff linting + pre-commit hook
Add `.pre-commit-config.yaml` with `ruff check` and `ruff format` hooks.
Currently `ruff` is a dev dependency but not enforced.

### Docker Compose setup
`docker-compose.yml` with:
- `ollama` service (with model pre-pull)
- `api` service running `uvicorn`
- Shared volume for `data/` and `content/`

### Structured logging
Replace `logging.basicConfig` with a structured logger (e.g. `structlog`)
that emits JSON lines in production and pretty output in development.

### Configuration validation on startup
`init_db()` and `OllamaClient.health_check()` are called at startup.
Add a dedicated `startup_checks()` function that validates:
- `content_dir` exists and contains `.md` files
- `db_path` parent directory is writable
- Ollama is reachable and the configured model is available

---

## Known Gaps / Tech Debt

| Area | Issue |
|------|-------|
| `quiz/service.py` | `list_questions` runs two queries to get total count — replace with `SELECT COUNT(*)` |
| `storage/question_repo.py` | `QuestionRecord` class is defined but never used — remove or use it |
| `ingest.py` | No signal handling (SIGINT mid-run leaves DB in partial state) |
| `chunker.py` | Carry buffer uses first section's heading for accumulated multi-section chunks — may be misleading |
| `test_api.py` | Lifespan context is bypassed in tests — add a proper lifespan-aware test fixture |
| General | No migration system — schema changes require manual DB deletion and re-ingestion |
