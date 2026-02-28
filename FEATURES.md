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

- [x] **Question review UI** — a separate screen (or page) to browse generated questions, approve/reject, and edit text/options/answer. The `status` column (`generated → approved → edited`) and `PATCH /questions/{id}/status` already exist; the UI just isn't wired up. This is the highest-leverage quality improvement.
- [x] **Edit endpoint** — `PUT /questions/{id}` to update question text, options, `correct_index`, and `explanation` in place. Required to support the review UI above.
- [x] **Flag / reject questions** — mark a question as `rejected` so it never appears in quizzes. Add `rejected` to the status enum and filter it out of `GET /quiz`.
- [x] **Ingest progress output** — stream per-chunk progress to stdout during ingestion so long runs feel less like a black box. Could also add an ETA based on chunk count.
- [x] **`--list` and `--stats` CLI flags** — quick DB summary without starting the API (document count, question count, status breakdown).

### Quiz experience

- [x] **End-of-quiz review** — after the results screen, let the user scroll through all questions from the session showing what they answered vs. the correct answer + explanation. Currently results disappear once you leave the end screen.
- [x] **Keyboard shortcuts** — press `1`–`4` to select an option, `Enter`/`Space` to confirm, `→` for next. Speeds up power users significantly.
- [ ] **Timer mode** — optional per-question countdown (e.g. 30 s). Adds pressure for exam prep.
- [x] **"Missed only" replay** — at the end of a quiz, offer to replay just the questions you got wrong with one click.

### Filtering & discovery

- [x] **Tag-based filtering** — articles already carry tags in frontmatter; expose `GET /quiz?tag=…` and surface a tag selector on the setup screen. Requires propagating tags through chunks → questions at ingest time.
- [x] **Multi-document selection** — currently the document selector is single-select; allow picking multiple documents for a cross-topic quiz.
- [x] **Question count guard** — if the DB has fewer questions than the requested `n` for a given filter, return what's available and tell the user (`X of N requested`).

### Progress tracking & spaced repetition

- [x] **Session history** — persist quiz results (question ID, selected index, correct, timestamp) to a `sessions` table. Enables all analytics below.
- [x] **Per-question hit rate** — track how often each question is answered correctly. Surface this in the review UI and use it to inform difficulty calibration.
- [x] **Weak-topic replay** — surface questions from topics you've historically scored worst on. Simple heuristic: sort by ascending hit rate, pick bottom quartile.
- [x] **Spaced repetition mode** — SM-2 backend (`srs_cards`, `srs_sessions`, `srs_reviews` tables; `algorithm.py` pure functions; `/api/v1/srs/` routes) + frontend SRS mode (mode toggle, per-answer "Next review: in X days", session summary, stats dashboard with per-document due/new table).

### Export & interop

- [x] **JSON export** — `GET /questions/export?format=json` dumps all questions (filterable by status/document). Includes embedded documents for full-fidelity round-trip.
- [x] **CSV export** — `GET /questions/export?format=csv` — flat spreadsheet with denormalised `document_title`; export-only.
- [x] **JSON import** — `POST /questions/import` restores from a JSON export; upserts documents, creates synthetic chunk placeholders, skips fingerprint duplicates.
- [ ] **Anki deck export** — convert approved questions to an `.apkg` file. `genanki` is the standard library for this.

### Generation & pipeline

- [x] **Per-model quality comparison** — ingest the same document with two different Ollama models and compare question output side-by-side. Helps choose the best model.
- [ ] **Difficulty calibration** — after enough session data, auto-adjust `difficulty` labels based on observed hit rates (e.g. >80% correct → easy, <40% → hard).
- [x] **Prompt versioning in review UI** — show which `prompt_version` and `model` generated each question in the review UI so bad batches can be identified and purged.
- [ ] **Re-generate for a chunk** — CLI flag `--rechunk <doc>` to re-run generation on a specific document's chunks without re-ingesting the document itself.

### Refactors & technical debt

- [x] **Fix N+1 in `list_documents`** — `QuizService.list_documents` (`quiz/service.py:104-117`) calls `count_by_document()` in a per-document loop. Replace with one `SELECT source_document_id, COUNT(*) FROM questions GROUP BY source_document_id` query and merge in Python.
- [x] **Fix double-query total count in `list_questions`** — `QuizService.list_questions` (`quiz/service.py:38-44`) fetches up to 10 000 rows just to count them. Replace with a `SELECT COUNT(*)` query that uses the same filters.
- [x] **Remove dead `QuestionRecord` class** — `QuestionRecord` with `__slots__` is defined in `question_repo.py:9-18` but never returned by any method (all methods return `dict`). Delete it.
- [x] **Fix greedy regex in `_parse_questions`** — `_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)` is greedy and will grab from the first `{` to the last `}`, mangling multi-question JSON. Switch to lazy `.*?` or use `json.JSONDecoder.raw_decode` to find the first valid JSON object.
- [x] **Eliminate private `_conn` access in `import_data`** — `QuizService.import_data` (`quiz/service.py:152-153`) calls `self.questions._conn.execute(...)` directly to insert synthetic chunk rows. Add a `ChunkRepository.insert_placeholder()` method (or add to `DocumentRepository`) so the service doesn't reach into private attributes.
- [x] **Deduplicate WHERE-clause filter building** — `list_questions`, `get_random_sample`, `list_all_for_export`, and `_weak_filters` in `question_repo.py` all hand-build identical `difficulty / status / document_ids` filter snippets. Extract a shared `_base_filters(difficulty, status, document_ids)` helper.
- [x] **Typed response models for session GET routes** — `GET /quiz/sessions/{id}` and `GET /srs/sessions/{id}` both declare `response_model=dict`. Define proper Pydantic schemas (`QuizSessionDetail`, `SrsSessionDetail`) so clients get validated, documented shapes.
- [x] **Replace module-level service globals with `app.state`** — `app.py` uses `_service / _srs_service / _quiz_session_service` globals + circular-import workarounds in each router. Moved to `quiz/deps.py`; routers import `deps` at module level, eliminating deferred circular-import workarounds.
- [x] **Database migrations** — `init_db` uses `CREATE TABLE IF NOT EXISTS` which cannot add columns to existing tables. Add a simple version table + migration runner so future schema changes (e.g. new columns) can be applied without dropping data.

### Quiz experience

- [ ] **SRS hesitant-correct rating** — SM-2 supports rating `3` ("correct but difficult") but `SrsService.submit_review` hard-codes `5 if correct else 0`. Surface a "Struggled" button in the SRS UI alongside "Got it" to feed rating `3`, slowing interval growth for shaky knowledge.
- [ ] **Timer mode** — optional per-question countdown (e.g. 30 s). Adds pressure for exam prep.
- [ ] **Session history screen** — a "Past Sessions" page listing historical random and SRS sessions with date, score, and a link to replay the review. Requires a `GET /quiz/sessions` listing endpoint (currently only `GET /quiz/sessions/{id}` exists).

### Admin & data quality

- [ ] **Full-text search on questions** — `GET /questions` can filter by difficulty/status/document but not text. Add an optional `q=` query param that runs a SQLite `LIKE` (or FTS5) search on question text for faster review-UI browsing.
- [ ] **Bulk approve / reject in review UI** — the review screen handles one question at a time. Add checkboxes + a toolbar action to approve or reject a selected batch, speeding up QA on large ingests.
- [ ] **Purge by model / prompt_version** — the review UI shows `model` + `prompt_version` metadata but there's no way to bulk-reject all questions from a bad generation run. Add a `PATCH /questions/bulk-status` endpoint accepting a list of IDs, or a `model=` + `prompt_version=` filter on the status-patch endpoint.

### Generation & pipeline

- [ ] **Difficulty calibration** — after enough session data, auto-adjust `difficulty` labels based on observed hit rates (e.g. >80% correct → easy, <40% → hard). Could be a CLI script that emits suggested UPDATE statements for review.
- [ ] **Re-generate for a chunk** — CLI flag `--rechunk <doc>` to re-run generation on a specific document's chunks without re-ingesting the document itself. Useful when switching models or prompts.
- [ ] **Configurable question-count thresholds** — `_question_count` in `generator.py` hard-codes ≤400→1, ≤600→2, else→3. Expose as `QUIZZER_CHUNK_Q_THRESHOLDS` settings so power users can tune density without code changes.

### Export & interop

- [ ] **Anki deck export** — convert approved questions to an `.apkg` file using `genanki`. Each question becomes a cloze or basic card; tags map to Anki deck names.

---

## Completed

- [x] "Missed only" replay — "Retry missed (N)" button on end screen replays wrong answers without an API call
- [x] Question count guard — `GET /quiz` returns `{questions, requested, returned}`; UI shows amber notice when fewer questions served than requested
- [x] End-of-quiz review — "Review Answers" button on end screen shows all Q&A with color-coded options + explanations
- [x] Keyboard shortcuts — `1`–`4` select option, `Enter`/`Space` confirm or advance, `→` next
- [x] `--list` — list ingested documents with per-doc question counts; exits without touching Ollama
- [x] `--stats` — total questions + breakdown by status and difficulty; exits without touching Ollama
- [x] Question review UI at `/review` — approve, edit inline, reject; status badges; paginated; filtered by status/doc/difficulty
- [x] `PUT /questions/{id}` — edit question content (auto-sets status to `edited`)
- [x] `rejected` status — excluded from `GET /quiz`, supported in `PATCH /status`
- [x] "Review questions →" link on quiz setup screen
- [x] Ingestion pipeline: load → chunk → generate → validate → store
- [x] Deduplication via SHA-256 fingerprint
- [x] `--force` re-ingest with correct document ID preservation
- [x] `--dry-run` and `--model` CLI flags
- [x] FastAPI REST API with paginated question listing
- [x] Answer checking without leaking `correct_index` upfront
- [x] Vanilla JS quiz UI (setup → loading → question → end → error screens)
- [x] Document selector on setup screen
- [x] Difficulty filter in quiz setup and API
- [x] Tag-based filtering — `GET /tags` + `GET /quiz?tag=…`; tag selector dropdown in random-mode setup (hidden when no tags exist)
- [x] Ingest progress output — per-chunk `[i/n] heading  Xw  Y Q  Z.Zs` lines with `\r` overwrite while generating; ETA shown from second chunk onward
- [x] `html_to_md.py` preprocessor for ByteByteGo HTML pages
- [x] Multi-document selection — `<select multiple>` on setup screen; `GET /quiz` accepts repeated `document_id` params collected into `list[str]`; nothing selected = all documents; SRS mode uses first selected doc
- [x] JSON/CSV export + JSON import — `GET /questions/export?format=json|csv`; `POST /questions/import`; round-trip fidelity via embedded documents and synthetic chunk placeholders
- [x] Random quiz session history — `quiz_sessions` + `quiz_answers` tables; `POST /quiz/sessions`, `/answers`, `/finish`, `GET /quiz/sessions/{id}`; frontend random flow wired through session API; 84 tests pass
- [x] Prompt versioning in review UI — model + prompt_version shown as muted `<code>` tags on each question card in `/review/`; parallel fetch of `GET /questions/{id}` alongside existing answer fetch; no backend changes
- [x] Per-model quality comparison — `scripts/compare_models.py --source <doc> --models m1 m2 [m3…] [--chunks N]`; dry run, no DB writes; per-chunk question display with validity markers; summary table of valid/invalid/parse-errors/time per model
- [x] Per-question hit rate — `get_hit_rate()` aggregates `quiz_answers` + `srs_reviews`; exposed on `GET /questions/{id}` as `times_answered`, `times_correct`, `hit_rate`; colour-coded pill on review UI cards (green ≥80%, amber 50–79%, red <50%, muted "Never attempted"); 87 tests pass
- [x] Weak-topic replay — `get_weak_sample/count()` queries `quiz_answers ∪ srs_reviews`, sorts by hit rate asc, bottom quartile; `weak: bool` on `StartQuizSessionRequest`; `GET /quiz/weak-count`; "Weak Topics" third mode pill on setup screen with pool-size info; 90 tests pass
