# System Design MCQ Generator

Converts locally stored system design articles into structured multiple-choice questions
via an LLM (Gemini 2.5 Flash by default, or a local Ollama model). The pipeline is
deterministic and batch-oriented. Questions are served through a FastAPI REST API.

**Stack:** Python · uv · Gemini 2.5 Flash (Google AI Studio) · Ollama (fallback) · SQLite · FastAPI

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- A [Google AI Studio](https://aistudio.google.com/) API key **or** [Ollama](https://ollama.com/) running locally (fallback)

---

## Setup

### 1. Install dependencies

```bash
# Clone and enter the project
cd system_design_quizzer

# Install all dependencies (including dev extras)
uv sync --extra dev
```

### 2. Set up Gemini (recommended)

Gemini 2.5 Flash is the default LLM provider — faster than local models and requires no GPU.

1. Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with a Google account and click **Create API key**
3. Copy the key and add it to your `.env` file:

```bash
QUIZZER_GEMINI_API_KEY=your_key_here
```

That's it. The provider defaults to `auto`, which picks Gemini automatically when a key is present.

> **Free tier limits (Gemini 2.5 Flash):** 10 RPM · 500 RPD · 250 000 TPM
> The default `QUIZZER_GEMINI_REQUEST_DELAY=7.0` keeps requests safely under the 10 RPM cap.
> See [Google AI rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) for full details.

### 2b. Set up Ollama (local fallback)

If you don't have a Gemini API key, or want to run fully offline, [download and install Ollama](https://ollama.com/download) and start the server:

```bash
ollama serve
```

Pull a model. `llama3.2` is a good default — fast and reliable for JSON MCQ generation:

```bash
ollama pull llama3.2
```

Check what you have locally at any time:

```bash
ollama list
```

> **Model recommendations:**
> - `llama3.2` (2 GB) — fast, good JSON compliance, recommended default
> - `mistral` (4.1 GB) — higher quality questions, still fast
> - `llama3.1:8b` (4.9 GB) — best quality of the small models
>
> Avoid code-focused models (e.g. `qwen3-coder`) — they're tuned for code, not prose comprehension.

To force Ollama even when a Gemini key is present, set `QUIZZER_LLM_PROVIDER=ollama` in your `.env`.

See the [Configuration](#configuration) section for all available settings.

---

## Usage

### 1. Add content

Place Markdown articles under `content/<source>/<slug>.md` with YAML frontmatter:

```markdown
---
title: "Consistent Hashing: A Deep Dive"
source: "System Design Primer"
tags: ["distributed-systems", "hashing"]
---

# Introduction

Your article content here...
```

A sample article is included at `content/example/consistent-hashing.md`.

### 1b. Convert a saved HTML page to Markdown (ByteByteGo)

If your source is a ByteByteGo article, save the page from your browser and convert it before ingesting.

**Install the preprocessing extras first (one-time):**

```bash
uv sync --extra preprocessing
```

**Convert:**

```bash
# Default output: content/bytebytego/<stem>.md
uv run python scripts/html_to_md.py content/some-article.html

# Custom output path
uv run python scripts/html_to_md.py content/some-article.html -o content/bytebytego/my-article.md
```

The script:
- Targets the `<article>` element, falling back to `#content` → `<body>`
- Strips nav, sidebars, footers, and pagination chrome
- Replaces `<figure>`/`<img>` tags with `[Figure: <alt text>]` captions so diagrams are described in text
- Unwraps `<a>` tags (ByteByteGo links point back to their site)
- Emits a `.md` file with YAML frontmatter (`title`, `source: "ByteByteGo"`, `url`, `tags`) ready for ingestion

### 1c. Compare models before ingesting (optional)

If you're unsure which model to use, run a quick side-by-side comparison on a single
article before committing to a full ingest. Nothing is written to the database.

```bash
# Compare two models across a full article
uv run python scripts/compare_models.py \
    --source content/example/consistent-hashing.md \
    --models llama3.2 mistral

# Quick check — first 2 chunks only (much faster)
uv run python scripts/compare_models.py \
    --source content/example/consistent-hashing.md \
    --models llama3.2 mistral \
    --chunks 2

# Compare three models at once
uv run python scripts/compare_models.py \
    --source content/example/consistent-hashing.md \
    --models llama3.2 mistral llama3.1:8b
```

The script prints each model's questions per chunk (with ✓/✗ validity markers), then a
summary table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Model                Valid Qs  Invalid  Parse errs    Time
  ──────────────────── ──────── ──────── ─────────── ───────
  llama3.2                   12        1           0   45.2s
  mistral                    15        0           0   62.1s

  → Most questions : mistral (15 valid)
  → Fastest        : llama3.2 (45.2s)
```

Use the winner's name as `QUIZZER_OLLAMA_MODEL` in your `.env` before running ingestion.

### 2. Run ingestion

```bash
# Ingest a single article
uv run python scripts/ingest.py --source content/example/consistent-hashing.md --verbose

# Ingest all articles in the content directory
uv run python scripts/ingest.py

# Re-ingest an already-processed article
uv run python scripts/ingest.py --source content/example/consistent-hashing.md --force

# Preview without writing to the database
uv run python scripts/ingest.py --dry-run --verbose

# Use a different model (must match ollama list)
uv run python scripts/ingest.py --model llama3.2 --verbose

# List all ingested documents with question counts (no Ollama required)
uv run python scripts/ingest.py --list

# Show question counts broken down by status and difficulty (no Ollama required)
uv run python scripts/ingest.py --stats
```

The pipeline for each article:
1. Parse frontmatter → normalize text
2. Chunk by headings (300–800 words per chunk)
3. Send each chunk to the LLM (Gemini or Ollama) → receive JSON MCQs
4. Validate + deduplicate → insert into SQLite

### 3. Start the server

```bash
uv run uvicorn quizzer.quiz.app:app --reload
```

This starts both the REST API and the web UI:

| Endpoint | Description |
|----------|-------------|
| `http://localhost:8000/` | Web UI — take quizzes in the browser |
| `http://localhost:8000/api/v1/` | REST API |
| `http://localhost:8000/docs` | Interactive API docs (Swagger) |

The web UI lets you choose a question count (1–50), tick the documents to draw from, filter by difficulty, and work through a quiz with immediate answer feedback and explanations. An **Exit Quiz** button is always visible during a session — clicking it ends the quiz early and shows your score for the questions answered so far; leaving the page mid-question asks for confirmation first.

The pages are keyboard-operable and screen-reader friendly: `1`–`4` move real focus between options, results are announced through a live region, answered options carry a tick or cross as well as a colour, and every control has a visible focus ring. The palette meets WCAG AA and `prefers-reduced-motion` is honoured.

No build step — plain HTML, CSS and JS served by FastAPI, with the design tokens in `static/css/app.css` and the shared `api.js` / `toast.js` helpers in `static/js/`.

The review UI at `http://localhost:8000/review/` lets you browse, approve, edit, and reject questions. Each card has a checkbox; a **Select all on page** control and a **Reject selected (N)** button let you bulk-reject batches of bad questions in one click.

![Quiz UI screenshot](docs/quiz_screenshot.png)

---

## API Reference

Base path: `/api/v1`

### Quiz endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/questions` | List questions with their answer, provenance and hit rate — everything the review card needs, so it costs one request per page. Filters: `difficulty`, `status`, `document_id`, `q` (text search), `model`, `prompt_version`, `limit`, `offset` |
| `GET` | `/questions/{id}` | Get question detail (no answer) — includes `times_answered`, `times_correct`, `hit_rate` |
| `GET` | `/questions/{id}/answer` | Get question with correct answer + explanation |
| `POST` | `/questions/{id}/answer` | Submit answer `{"selected_index": 0}` → `{correct, correct_index, explanation}` |
| `PATCH` | `/questions/{id}/status` | Update status `{"status": "approved"\|"edited"\|"rejected"}` |
| `PUT` | `/questions/{id}` | Edit question content `{question, options, correct_index, explanation, difficulty}` — refreshes the dedup fingerprint; 409 if the new text duplicates another question |
| `POST` | `/questions/bulk-status` | Bulk status update `{"ids": ["…"], "status": "rejected"}` → `{"updated": N}` |
| `DELETE` | `/questions/{id}` | Permanently delete a question (removes associated SRS and quiz answer history) → 204 |
| `GET` | `/questions/models` | Distinct model names across stored questions (review-UI filter) |
| `GET` | `/questions/prompt-versions` | Distinct prompt versions across stored questions (review-UI filter) |
| `GET` | `/questions/near-duplicates` | Jaccard-similar question pairs. Params: `threshold` (0–1, default 0.5), `document_id` (repeatable) |
| `GET` | `/quiz` | Random sample. Params: `n` (default 5), `difficulty`, `document_id` (repeatable), `tag` → `{questions, requested, returned}` |
| `GET` | `/tags` | Sorted list of unique tags across all documents |
| `GET` | `/documents` | List documents with question, chunk, and word counts |
| `POST` | `/documents/{id}/reingest` | Re-run ingestion for a document's source file in the background → 202 `{document_id, title, status}`; 409 if one is already running for that document |
| `GET` | `/health` | DB + Ollama connectivity check |

### Quiz session endpoints

The web UI drives random and weak-topic quizzes through sessions so answers are
recorded for hit-rate and weak-topic tracking.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/quiz/sessions` | Start a session. Body: `{"n": 5, "difficulty": null, "tag": null, "document_ids": [], "weak": false}` → `{session_id, questions, started_at}` |
| `POST` | `/quiz/sessions/{id}/answers` | Record an answer. Body: `{"question_id": "…", "selected_index": 0}` → `{correct, correct_index, explanation}`. 404 for questions not dealt into the session |
| `POST` | `/quiz/sessions/{id}/finish` | Close a session → `{n_answered, n_correct, n_wrong, n_skipped, …}` |
| `GET` | `/quiz/sessions/{id}` | Session details + full answer log |
| `GET` | `/quiz/weak-count` | Size of the weak-topic pool (bottom-quartile hit rate). Params: `difficulty`, `document_id` (repeatable) |

> Set `"weak": true` on `POST /quiz/sessions` to draw only from the bottom-quartile-by-hit-rate pool instead of a random sample.

### Export & import endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/questions/export` | Download questions as JSON or CSV. Params: `format` (`json`\|`csv`, default `json`), `status`, `document_id` (repeatable). Rejected questions are excluded unless `status=rejected` is passed explicitly |
| `POST` | `/questions/import` | Import from a JSON export payload → `{imported, skipped, errors}` |

### Spaced repetition (SRS) endpoints

The SRS layer implements the SM-2 algorithm (used by Anki). Questions are
scheduled based on past performance — correct answers push the next review
further out; wrong answers reset the interval to 1 day.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/srs/due` | Count of due and new questions. Params: `document_id` (repeatable) |
| `GET` | `/srs/due/by-document` | Due and new counts for every document in one call → `[{document_id, due_count, new_count, total_actionable}]` |
| `POST` | `/srs/sessions` | Start a session — returns due/new questions ordered by urgency. Body: `{"n": 10, "document_ids": []}` |
| `POST` | `/srs/sessions/{id}/reviews` | Submit an answer — applies SM-2, returns next due date + new interval. Body: `{"question_id": "…", "selected_index": 2}` |
| `POST` | `/srs/sessions/{id}/finish` | Close a session — returns correct/wrong counts |
| `GET` | `/srs/sessions/{id}` | Session details + full review log |

**SM-2 ratings used internally:**
- `5` — correct answer (ease factor increases)
- `3` — correct but hesitant (ease factor decreases slightly; reserved for future UI)
- `0` — wrong answer (interval resets to 1 day, ease factor unchanged)

### Example session

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Get a 5-question quiz (random)
curl http://localhost:8000/api/v1/quiz?n=5

# Submit an answer
curl -X POST http://localhost:8000/api/v1/questions/<id>/answer \
  -H "Content-Type: application/json" \
  -d '{"selected_index": 2}'

# Approve a question
curl -X PATCH http://localhost:8000/api/v1/questions/<id>/status \
  -H "Content-Type: application/json" \
  -d '{"status": "approved"}'
```

### Example export & import

```bash
# Export all questions as JSON (downloads quizzer-export.json)
curl -O http://localhost:8000/api/v1/questions/export

# Export only approved questions
curl -O "http://localhost:8000/api/v1/questions/export?status=approved"

# Export questions from specific documents (repeat param for multiple)
curl -O "http://localhost:8000/api/v1/questions/export?document_id=<id1>&document_id=<id2>"

# Export as CSV (flat spreadsheet, no import support)
curl -O "http://localhost:8000/api/v1/questions/export?format=csv"

# Import from a JSON export (e.g. restore a backup or load on a new machine)
curl -X POST http://localhost:8000/api/v1/questions/import \
  -H "Content-Type: application/json" \
  -d @quizzer-export.json
# → {"imported": 42, "skipped": 3, "errors": []}
```

**How import works:**
- Documents in the payload are upserted (safe to run repeatedly).
- Questions already in the database (matched by fingerprint) are skipped — not duplicated.
- Errors on individual questions are collected and returned; the rest still import.
- The JSON format is the canonical round-trip format; CSV is export-only.

### Example SRS session

```bash
# Check how many cards are due or new
curl http://localhost:8000/api/v1/srs/due

# Start a 10-card SRS session
curl -X POST http://localhost:8000/api/v1/srs/sessions \
  -H "Content-Type: application/json" \
  -d '{"n": 10}'
# → {"session_id": "...", "questions": [...], "started_at": "..."}

# Submit an answer for each question
curl -X POST http://localhost:8000/api/v1/srs/sessions/<session_id>/reviews \
  -H "Content-Type: application/json" \
  -d '{"question_id": "<q_id>", "selected_index": 2}'
# → {"correct": true, "correct_index": 2, "explanation": "...",
#    "next_due": "2026-03-03", "interval_days": 1, "ease_factor": 2.6}

# Finish the session
curl -X POST http://localhost:8000/api/v1/srs/sessions/<session_id>/finish
# → {"session_id": "...", "n_reviewed": 10, "n_correct": 8, "n_wrong": 2, ...}
```

---

## Configuration

All settings are read from environment variables with the `QUIZZER_` prefix.
The recommended approach is a `.env` file at the project root (already gitignored):

```bash
# .env — minimal Gemini setup
QUIZZER_GEMINI_API_KEY=your_key_here
```

#### LLM provider

| Variable | Default | Description |
|----------|---------|-------------|
| `QUIZZER_LLM_PROVIDER` | `auto` | `auto` — Gemini if key is set, else Ollama; `gemini` — always Gemini; `ollama` — always local |

#### Gemini (Google AI Studio)

| Variable | Default | Description |
|----------|---------|-------------|
| `QUIZZER_GEMINI_API_KEY` | _(none)_ | API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `QUIZZER_GEMINI_MODEL` | `gemini-2.5-flash` | Model name — see [Google AI rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) |
| `QUIZZER_GEMINI_REQUEST_DELAY` | `7.0` | Seconds between requests — free tier is 10 RPM, so 7s keeps you under |
| `QUIZZER_GEMINI_MAX_RETRIES` | `3` | Retries on 429 — waits the API-suggested `retryDelay` between attempts |

#### Ollama (local fallback)

| Variable | Default | Description |
|----------|---------|-------------|
| `QUIZZER_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `QUIZZER_OLLAMA_MODEL` | `llama3.1:8b` | Model name — must match `ollama list` exactly |
| `QUIZZER_OLLAMA_TEMPERATURE` | `0.1` | Generation temperature |
| `QUIZZER_OLLAMA_SEED` | `42` | Seed for reproducibility |

#### Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `QUIZZER_CONTENT_DIR` | `content` | Directory containing `.md` articles |
| `QUIZZER_DB_PATH` | `data/quizzer.db` | SQLite database path |
| `QUIZZER_CHUNK_WORD_MIN` | `300` | Minimum words per chunk |
| `QUIZZER_CHUNK_WORD_MAX` | `800` | Maximum words per chunk |
| `QUIZZER_MIN_EXPLANATION_LENGTH` | `50` | Minimum characters in an explanation |

> **Tip:** If ingestion logs a `404` from Ollama, the model name doesn't match. Run `ollama list` to see exact names and update `QUIZZER_OLLAMA_MODEL` accordingly.

---

## Running Tests

```bash
uv run pytest tests/ -v     # backend
npm test                    # frontend (jsdom, needs `npm ci` once)
```

220 Python tests covering: ingestion (loader, cleaner, chunker, path resolution), validation (normalizer, schema, dedup),
generation (prompt, parser robustness, generator), the ByteByteGo preprocessor (frontmatter escaping), schema migrations, the full API surface (including export/import validation, quiz sessions, session membership, bulk status, delete, re-ingest), the SM-2 algorithm, the SRS repository, SRS API, static-asset wiring, and the WCAG AA palette.

82 frontend tests boot each page in jsdom against a stubbed API and drive it
through the DOM — quiz flow, SRS mode, review actions, and the accessibility
contract. `tests/js/harness.mjs` inlines each page's scripts from disk, so the
tests run without a server.

CI runs `ruff check` + pytest, and the frontend suite as a separate job (`.github/workflows/ci.yml`).

---

## Project Layout

```
system_design_quizzer/
├── .github/workflows/ci.yml    # CI: ruff + pytest on every push/PR
├── content/                    # Manually curated .md articles
│   └── <source>/<slug>.md
├── data/                       # SQLite DB (gitignored)
├── scripts/
│   ├── ingest.py               # CLI pipeline
│   ├── compare_models.py       # Dry-run model quality comparison
│   └── html_to_md.py           # ByteByteGo HTML → Markdown preprocessor
├── src/quizzer/
│   ├── config.py               # Pydantic settings
│   ├── database.py             # Schema DDL + connection factory
│   ├── ingestion/              # loader · cleaner · chunker · models
│   ├── generation/             # base · factory · gemini_client · ollama_client · prompt_builder · generator · models
│   ├── validation/             # normalizer · schema_validator · duplicate_detector
│   ├── storage/                # document_repo · question_repo · session_repo
│   ├── srs/                    # Spaced repetition (SM-2)
│   │   ├── algorithm.py        # Pure SM-2 functions (apply_review, initial_state)
│   │   ├── repository.py       # CRUD for srs_cards · srs_sessions · srs_reviews
│   │   ├── schemas.py          # SRS request/response models
│   │   ├── service.py          # Business logic (create_session, submit_review, …)
│   │   └── router.py           # Routes under /api/v1/srs/
│   └── quiz/
│       ├── app.py              # FastAPI app factory + static file mount
│       ├── deps.py             # Service singletons wired at startup
│       ├── router.py           # API routes (/api/v1/...)
│       ├── service.py          # Business logic
│       ├── session_service.py  # Quiz-session + weak-topic logic
│       ├── schemas.py          # Pydantic request/response models
│       └── static/             # Plain HTML/CSS/JS — no build step
│           ├── index.html      # Quiz UI
│           ├── favicon.svg
│           ├── css/            # app.css (shared tokens) + one file per page
│           ├── js/             # api.js · toast.js + one file per page
│           ├── review/         # Question review/approve UI
│           └── sources/        # Ingested-article browser
└── tests/
    ├── conftest.py             # shared fixtures + default-DB isolation
    ├── test_loader.py          # loader + source-path resolution
    ├── test_cleaner.py         # HTML-tag stripping vs. < > prose
    ├── test_chunker.py
    ├── test_validator.py
    ├── test_generator.py       # generation + parser robustness
    ├── test_gemini_client.py   # throttling + retry behavior
    ├── test_html_to_md.py      # ByteByteGo frontmatter escaping
    ├── test_database.py        # migration runner + fresh-DB stamping
    ├── test_document_repo.py   # orphan-chunk cleanup
    ├── test_concurrency.py     # per-thread connection safety
    ├── test_api.py
    ├── test_srs_algorithm.py   # SM-2 unit tests
    ├── test_srs_repository.py  # SRS query construction
    ├── test_srs_api.py         # SRS API integration tests
    ├── test_static_assets.py   # asset wiring + markup conventions
    ├── test_css_contrast.py    # WCAG AA palette + focus/motion rules
    └── js/                     # jsdom tests for the three pages (npm test)
```

---

## Pipeline Overview

```
.md file
  └─ load_document()       parse frontmatter, clean text
      └─ chunk_document()  split by headings → paragraph fallback
          └─ generate_for_chunk()   prompt LLM → JSON MCQs
              └─ normalize_mcq()   strip, capitalize, punctuate
                  └─ validate_mcq()   4 options, length, no dupes
                      └─ fingerprint()   SHA-256 dedup guard
                          └─ question_repo.insert()   → SQLite
```
