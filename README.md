# System Design MCQ Generator

Converts locally stored system design articles into structured multiple-choice questions
via a local Ollama LLM. The pipeline is deterministic and batch-oriented. Questions are
served through a FastAPI REST API.

**Stack:** Python · uv · Ollama · SQLite · FastAPI

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- [Ollama](https://ollama.com/) running locally on `http://localhost:11434`
- A pulled model, e.g. `ollama pull mistral`

---

## Setup

```bash
# Clone and enter the project
cd system_design_quizzer

# Install all dependencies (including dev extras)
uv sync --extra dev
```

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

# Use a different model
uv run python scripts/ingest.py --model llama3 --verbose
```

The pipeline for each article:
1. Parse frontmatter → normalize text
2. Chunk by headings (300–800 words per chunk)
3. Send each chunk to Ollama → receive JSON MCQs
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

The web UI lets you choose a question count (1–50), filter by difficulty, and work through a quiz with immediate answer feedback and explanations. No build step — it's a single static HTML file served by FastAPI.

---

## API Reference

Base path: `/api/v1`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/questions` | List questions. Filters: `difficulty`, `status`, `document_id`, `limit`, `offset` |
| `GET` | `/questions/{id}` | Get question detail (no answer) |
| `GET` | `/questions/{id}/answer` | Get question with correct answer + explanation |
| `POST` | `/questions/{id}/answer` | Submit answer `{"selected_index": 0}` → `{correct, correct_index, explanation}` |
| `PATCH` | `/questions/{id}/status` | Update status `{"status": "approved"\|"edited"}` |
| `GET` | `/quiz` | Random sample. Params: `n` (default 5), `difficulty` |
| `GET` | `/documents` | List documents with question counts |
| `GET` | `/health` | DB + Ollama connectivity check |

### Example session

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Get a 5-question quiz
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

---

## Configuration

All settings are read from environment variables with the `QUIZZER_` prefix.
You can also place them in a `.env` file at the project root.

| Variable | Default | Description |
|----------|---------|-------------|
| `QUIZZER_CONTENT_DIR` | `content` | Directory containing `.md` articles |
| `QUIZZER_DB_PATH` | `data/quizzer.db` | SQLite database path |
| `QUIZZER_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `QUIZZER_OLLAMA_MODEL` | `mistral` | Model name to use |
| `QUIZZER_OLLAMA_TEMPERATURE` | `0.1` | Generation temperature |
| `QUIZZER_OLLAMA_SEED` | `42` | Seed for reproducibility |
| `QUIZZER_CHUNK_WORD_MIN` | `300` | Minimum words per chunk |
| `QUIZZER_CHUNK_WORD_MAX` | `800` | Maximum words per chunk |
| `QUIZZER_MIN_EXPLANATION_LENGTH` | `50` | Minimum characters in an explanation |

---

## Running Tests

```bash
uv run pytest tests/ -v
```

41 tests covering: ingestion (loader, chunker), validation (normalizer, schema, dedup),
generation (prompt, parser, generator), and the full API surface.

---

## Project Layout

```
system_design_quizzer/
├── content/                    # Manually curated .md articles
│   └── <source>/<slug>.md
├── data/                       # SQLite DB (gitignored)
├── scripts/
│   └── ingest.py               # CLI pipeline
├── src/quizzer/
│   ├── config.py               # Pydantic settings
│   ├── database.py             # Schema DDL + connection factory
│   ├── ingestion/              # loader · cleaner · chunker · models
│   ├── generation/             # ollama_client · prompt_builder · generator · models
│   ├── validation/             # normalizer · schema_validator · duplicate_detector
│   ├── storage/                # document_repo · question_repo
│   └── quiz/
│       ├── app.py              # FastAPI app factory + static file mount
│       ├── router.py           # API routes (/api/v1/...)
│       ├── service.py          # Business logic
│       ├── schemas.py          # Pydantic request/response models
│       └── static/
│           └── index.html      # Single-file web UI (no build step)
└── tests/
    ├── conftest.py
    ├── test_loader.py
    ├── test_chunker.py
    ├── test_validator.py
    ├── test_generator.py
    └── test_api.py
```

---

## Pipeline Overview

```
.md file
  └─ load_document()       parse frontmatter, clean text
      └─ chunk_document()  split by headings → paragraph fallback
          └─ generate_for_chunk()   prompt Ollama → JSON MCQs
              └─ normalize_mcq()   strip, capitalize, punctuate
                  └─ validate_mcq()   4 options, length, no dupes
                      └─ fingerprint()   SHA-256 dedup guard
                          └─ question_repo.insert()   → SQLite
```
