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

- [ ] **Question review UI** — a separate screen (or page) to browse generated questions, approve/reject, and edit text/options/answer. The `status` column (`generated → approved → edited`) and `PATCH /questions/{id}/status` already exist; the UI just isn't wired up. This is the highest-leverage quality improvement.
- [ ] **Edit endpoint** — `PUT /questions/{id}` to update question text, options, `correct_index`, and `explanation` in place. Required to support the review UI above.
- [ ] **Flag / reject questions** — mark a question as `rejected` so it never appears in quizzes. Add `rejected` to the status enum and filter it out of `GET /quiz`.
- [ ] **Ingest progress output** — stream per-chunk progress to stdout during ingestion so long runs feel less like a black box. Could also add an ETA based on chunk count.
- [ ] **`--list` and `--stats` CLI flags** — quick DB summary without starting the API (document count, question count, status breakdown).

### Quiz experience

- [ ] **End-of-quiz review** — after the results screen, let the user scroll through all questions from the session showing what they answered vs. the correct answer + explanation. Currently results disappear once you leave the end screen.
- [x] **Keyboard shortcuts** — press `1`–`4` to select an option, `Enter`/`Space` to confirm, `→` for next. Speeds up power users significantly.
- [ ] **Timer mode** — optional per-question countdown (e.g. 30 s). Adds pressure for exam prep.
- [ ] **"Missed only" replay** — at the end of a quiz, offer to replay just the questions you got wrong with one click.

### Filtering & discovery

- [ ] **Tag-based filtering** — articles already carry tags in frontmatter; expose `GET /quiz?tag=…` and surface a tag selector on the setup screen. Requires propagating tags through chunks → questions at ingest time.
- [ ] **Multi-document selection** — currently the document selector is single-select; allow picking multiple documents for a cross-topic quiz.
- [ ] **Question count guard** — if the DB has fewer questions than the requested `n` for a given filter, return what's available and tell the user (`X of N requested`).

### Progress tracking & spaced repetition

- [ ] **Session history** — persist quiz results (question ID, selected index, correct, timestamp) to a `sessions` table. Enables all analytics below.
- [ ] **Per-question hit rate** — track how often each question is answered correctly. Surface this in the review UI and use it to inform difficulty calibration.
- [ ] **Weak-topic replay** — surface questions from topics you've historically scored worst on. Simple heuristic: sort by ascending hit rate, pick bottom quartile.
- [ ] **Spaced repetition mode** — SM-2 or a simple interval-based scheduler so high-confidence questions surface less often. Depends on session history.

### Export & interop

- [ ] **JSON export** — `GET /questions/export?format=json` dumps all approved questions. Useful for backups or sharing.
- [ ] **Anki deck export** — convert approved questions to an `.apkg` file. `genanki` is the standard library for this.
- [ ] **CSV export** — flat spreadsheet of questions for manual review or import into other tools.

### Generation & pipeline

- [ ] **Per-model quality comparison** — ingest the same document with two different Ollama models and compare question output side-by-side. Helps choose the best model.
- [ ] **Difficulty calibration** — after enough session data, auto-adjust `difficulty` labels based on observed hit rates (e.g. >80% correct → easy, <40% → hard).
- [ ] **Prompt versioning in review UI** — show which `prompt_version` and `model` generated each question in the review UI so bad batches can be identified and purged.
- [ ] **Re-generate for a chunk** — CLI flag `--rechunk <doc>` to re-run generation on a specific document's chunks without re-ingesting the document itself.

---

## Completed

- [x] Keyboard shortcuts — `1`–`4` select option, `Enter`/`Space` confirm or advance, `→` next
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
- [x] `html_to_md.py` preprocessor for ByteByteGo HTML pages
