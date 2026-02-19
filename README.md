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

---

## Setup

### 1. Install dependencies

```bash
# Clone and enter the project
cd system_design_quizzer

# Install all dependencies (including dev extras)
uv sync --extra dev
```

### 2. Set up Ollama

[Download and install Ollama](https://ollama.com/download), then start the server:

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

### 3. Configure your model

Create a `.env` file at the project root to set your model (and any other overrides):

```bash
QUIZZER_OLLAMA_MODEL=llama3.2
```

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

![Quiz UI screenshot](docs/quiz_screenshot.png)

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
The recommended approach is a `.env` file at the project root (already gitignored):

```bash
# .env
QUIZZER_OLLAMA_MODEL=llama3.2
```

| Variable | Default | Description |
|----------|---------|-------------|
| `QUIZZER_CONTENT_DIR` | `content` | Directory containing `.md` articles |
| `QUIZZER_DB_PATH` | `data/quizzer.db` | SQLite database path |
| `QUIZZER_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `QUIZZER_OLLAMA_MODEL` | `mistral` | Model name — must match `ollama list` exactly |
| `QUIZZER_OLLAMA_TEMPERATURE` | `0.1` | Generation temperature |
| `QUIZZER_OLLAMA_SEED` | `42` | Seed for reproducibility |
| `QUIZZER_CHUNK_WORD_MIN` | `300` | Minimum words per chunk |
| `QUIZZER_CHUNK_WORD_MAX` | `800` | Maximum words per chunk |
| `QUIZZER_MIN_EXPLANATION_LENGTH` | `50` | Minimum characters in an explanation |

> **Tip:** If ingestion logs a `404` from Ollama, the model name doesn't match. Run `ollama list` to see exact names and update `QUIZZER_OLLAMA_MODEL` accordingly.

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
