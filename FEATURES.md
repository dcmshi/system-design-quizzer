# Feature Tracker

## Status legend
- `[ ]` not started
- `[~]` in progress
- `[x]` done

---

## In progress / planned

_(move items here when actively working on them)_

---

## Backlog

### Admin & data quality

- [x] **Question review UI** — browse generated questions, approve/reject/edit inline; status badges; paginated; filtered by status/doc/difficulty.
- [x] **Edit endpoint** — `PUT /questions/{id}` to update question text, options, `correct_index`, and `explanation` in place; auto-sets status to `edited`.
- [x] **Flag / reject questions** — `rejected` status excluded from `GET /quiz`; supported in `PATCH /questions/{id}/status`.
- [x] **Ingest progress output** — per-chunk `[i/n] heading  Xw  Y Q  Z.Zs` lines with `\r` overwrite while generating; ETA shown from second chunk onward.
- [x] **`--list` and `--stats` CLI flags** — quick DB summary without starting the API (document count, question count, status breakdown).
- [x] **Full-text search on questions** — `GET /questions?q=` runs a case-insensitive `LIKE` search on `question` and `explanation`; debounced search input in review UI.
- [x] **Bulk approve / reject / delete in review UI** — checkboxes + bulk approve / reject / delete toolbar; `POST /questions/bulk-status` backend.
- [x] **Purge by model / prompt_version** — `POST /questions/bulk-status` accepts a list of IDs and any target status; review UI bulk actions cover the common case.
- [x] **Near-duplicate flagging** — SHA-256 catches exact duplicates but not semantically near-identical questions. Jaccard similarity check on question tokens at review time; visually flag suspicious pairs in the review UI.
- [x] **Bulk re-ingest from review UI** — per-document button in `/review/` to trigger re-ingestion without the CLI. Useful after a prompt or model change.
- [ ] **Question edit history** — store previous field values before each `PUT /questions/{id}` (JSON column or separate table) so bad edits can be undone.

### Quiz experience

- [x] **End-of-quiz review** — "Review Answers" button on end screen shows all Q&A with color-coded options + explanations.
- [x] **Keyboard shortcuts** — `1`–`4` select option, `Enter`/`Space` confirm or advance, `→` next.
- [x] **"Missed only" replay** — "Retry missed (N)" button on end screen replays wrong answers without an API call.
- [~] **SRS hesitant-correct rating** — SM-2 `algorithm.py` already accepts rating `3`; `SrsService.submit_review` hard-codes `5 if correct else 0`. Remaining work: surface a "Struggled" button in the SRS UI and pass rating `3` through the review endpoint.
- [ ] **Timer mode** — optional per-question countdown (e.g. 30 s). Adds pressure for exam prep.
- [~] **Session history screen** — `quiz_sessions` table and `SessionRepository` already exist. Remaining work: `GET /api/v1/quiz/sessions` list endpoint + a "Past Sessions" UI page with date, score, and replay link.
- [x] **Quiz progress bar** — "Question N of M" label + accent-coloured fill bar above the question card; fills to 100% on end screen.
- [ ] **Bookmark / star questions** — a flag (new status value or separate column) to mark questions for focused review, independent of the approve/reject workflow.
- [ ] **Explanation visibility toggle** — setup option to hide the explanation until after answering, or show it only on wrong answers. Supports active recall practice.

### Filtering & discovery

- [x] **Tag-based filtering** — `GET /tags` + `GET /quiz?tag=…`; tag selector dropdown in random-mode setup (hidden when no tags exist).
- [x] **Multi-document selection** — `<select multiple>` on setup screen; `GET /quiz` accepts repeated `document_id` params; nothing selected = all documents.
- [x] **Question count guard** — `GET /quiz` returns `{questions, requested, returned}`; UI shows amber notice when fewer questions served than requested.

### Progress tracking & spaced repetition

- [x] **Session history** — `quiz_sessions` + `quiz_answers` tables; `POST /quiz/sessions`, `/answers`, `/finish`, `GET /quiz/sessions/{id}`; frontend random flow wired through session API.
- [x] **Per-question hit rate** — `get_hit_rate()` aggregates `quiz_answers` + `srs_reviews`; exposed on `GET /questions/{id}`; colour-coded pill on review UI cards.
- [x] **Weak-topic replay** — bottom-quartile hit rate pool; `weak: bool` on `StartQuizSessionRequest`; `GET /quiz/weak-count`; "Weak Topics" mode pill on setup screen.
- [x] **Spaced repetition mode** — SM-2 backend (`srs_cards`, `srs_sessions`, `srs_reviews`; `algorithm.py`; `/api/v1/srs/` routes) + frontend SRS mode with stats dashboard.
- [ ] **SRS card reset** — button in review UI to wipe a card's SM-2 state back to new. Useful after significantly editing a question whose history no longer reflects true knowledge.
- [ ] **Leech detection** — flag cards answered wrong more than N times total; surface them in the review UI for rewriting or rejection. Classic SM-2 leech concept.
- [ ] **Due-load forecast** — chart on the SRS stats screen showing how many cards come due each day over the next 14 days. Helps with study planning.

### Export & interop

- [x] **JSON export** — `GET /questions/export?format=json`; filterable by status/document; embedded documents for round-trip fidelity.
- [x] **CSV export** — `GET /questions/export?format=csv`; flat spreadsheet with denormalised `document_title`.
- [x] **JSON import** — `POST /questions/import`; upserts documents, synthetic chunk placeholders, skips fingerprint duplicates.
- [ ] **Anki deck export** — convert approved questions to an `.apkg` file using `genanki`. Each question becomes a basic card; tags map to Anki deck names.
- [ ] **Markdown export** — `GET /questions/export?format=md` renders questions as a formatted markdown file suitable for Obsidian, Notion, or printing.

### Generation & pipeline

- [x] **Per-model quality comparison** — `scripts/compare_models.py --source <doc> --models m1 m2 …`; dry run, no DB writes; per-chunk display with validity markers and summary table.
- [x] **Prompt versioning in review UI** — `model` + `prompt_version` shown as muted `<code>` tags on each review card.
- [ ] **Difficulty calibration** — after enough session data, auto-adjust `difficulty` labels based on observed hit rates (e.g. >80% correct → easy, <40% → hard). CLI script emitting suggested UPDATE statements for review.
- [ ] **Re-generate for a chunk** — CLI flag `--rechunk <doc>` to re-run generation on a specific document's chunks without re-ingesting. Useful when switching models or prompts.
- [ ] **Configurable question-count thresholds** — `_question_count` in `generator.py` hard-codes ≤400→1, ≤600→2, else→3. Expose as `QUIZZER_CHUNK_Q_THRESHOLDS` setting.
- [ ] **Question diversity filter** — when a chunk produces multiple questions, check pairwise similarity and discard the weaker one if two are too close. Reduces noise at source before DB insertion.
- [~] **Prompt A/B test script** — `scripts/compare_models.py` already compares models on the same content. Remaining work: add a `--prompts` mode that fixes the model and varies `PROMPT_V*` instead, producing the same side-by-side quality table.
- [x] **Dry-run report** — `--dry-run` prints a formatted summary of documents, chunks, questions, and duplicates that would have been written, without touching the DB.

### Content management

- [x] **Source article browser** — a `/sources/` page listing ingested documents with chunk count, word count, question count, and last-ingested date. Currently this info is only accessible via CLI `--list`.
- [ ] **Per-chunk question viewer** — drill down from an article to see which chunks generated which questions. Helps identify chunks producing low-quality output.

### Refactors & technical debt

- [x] **Fix N+1 in `list_documents`** — replaced per-document `count_by_document()` loop with one `GROUP BY` query.
- [x] **Fix double-query total count in `list_questions`** — replaced full row-fetch with `SELECT COUNT(*)` using the same filters.
- [x] **Remove dead `QuestionRecord` class** — deleted `__slots__` class that was never returned by any method.
- [x] **Fix greedy regex in `_parse_questions`** — switched to lazy `.*?` / `raw_decode` to avoid mangling multi-question JSON.
- [x] **Eliminate private `_conn` access in `import_data`** — synthetic chunk rows now inserted via `DocumentRepository.upsert_chunk()`.
- [x] **Deduplicate WHERE-clause filter building** — shared `_search_filter` / `_difficulty_filter` / `_document_ids_filter` helpers in `question_repo.py`.
- [x] **Typed response models for session GET routes** — `QuizSessionDetail` and `SrsSessionDetail` Pydantic schemas replace `response_model=dict`.
- [x] **Replace module-level service globals with `app.state`** — moved to `quiz/deps.py`; eliminates deferred circular-import workarounds.
- [x] **Database migrations** — `schema_migrations` version table + `migrate_db()` runner; applied automatically on server start.

---

## Completed

- [x] Ingestion pipeline: load → chunk → generate → validate → store
- [x] Deduplication via SHA-256 fingerprint
- [x] `--force` re-ingest with correct document ID preservation
- [x] `--dry-run` and `--model` CLI flags
- [x] FastAPI REST API with paginated question listing
- [x] Answer checking without leaking `correct_index` upfront
- [x] Vanilla JS quiz UI (setup → loading → question → end → error screens)
- [x] Document selector on setup screen
- [x] Difficulty filter in quiz setup and API
- [x] `html_to_md.py` preprocessor for ByteByteGo HTML pages
- [x] "Review questions →" link on quiz setup screen
