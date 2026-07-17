# TODO — Code Audit Findings (2026-07-16)

Findings from a full-repo audit. Ordered by severity. All items addressed on 2026-07-16 (audit day).

## Critical

- [x] **1. `clean_text` destroys prose between `<` and `>`** — `src/quizzer/ingestion/cleaner.py:9`
  The HTML-stripping regex `<[^>]+>` matches *any* `<`…`>` span, including across newlines.
  `"If latency < 100ms the SLA holds, but p99 > 250ms breaks it."` → `"If latency  250ms breaks it."`
  Fix: only strip plausible HTML tags (e.g. `</?[a-zA-Z][^>\n]*>`).

## Data integrity

- [x] **2. `--force` re-ingest accumulates duplicate chunks** — `scripts/ingest.py` + `document_repo.py`
  Every re-ingest inserts a fresh set of chunk rows (new ULIDs); old ones are never deleted, so
  `chunk_count`/`word_count` on `/documents` and the sources UI inflate on each run (CLI and
  `/documents/{id}/reingest` API both affected). Fix: delete the document's chunks that have no
  questions referencing them before inserting the new set.

- [x] **3. Import can't reconcile documents by `source_path`** — `quiz/service.py::import_data`
  `DocumentRepository.upsert` conflicts on `source_path` but never updates `id`, so when the target
  DB already ingested the same article under a different id, every imported question references a
  nonexistent document id and fails its FK check. Fix: after upsert, re-read the document by
  `source_path` and remap `source_document_id` on imported questions/chunks.

- [x] **4. Export with `status=rejected` silently returns nothing** — `question_repo.py::list_all_for_export`
  The hard-coded base filter `status != 'rejected'` contradicts an explicit `status=rejected`
  request. Fix: only apply the base filter when no explicit status is given.

- [x] **5. Edited questions keep their stale fingerprint** — `quiz/service.py::edit_question`
  After an edit, the fingerprint still hashes the old wording, so a future ingest generating the
  new wording is not caught as a duplicate. Fix: recompute the fingerprint on edit; surface a 409
  when the edit would collide with an existing question.

- [x] **6. Session answers accept questions not in the session** — `session_service.py`, `srs/service.py`
  `submit_answer`/`submit_review` record answers for arbitrary `question_id`s, polluting hit-rate
  and weak-topic stats. Fix: persist the session's question ids and reject answers for
  non-member questions (needs schema migration).

## Smaller correctness / robustness

- [x] **7. Fresh DBs replay all migrations pointlessly** — `database.py::init_db`
  `_SCHEMA` already creates the final shape, then migration v1 rebuilds the questions table anyway.
  Fix: stamp brand-new DBs at the latest migration version instead of replaying.

- [x] **8. `get_shared_connection(db_path)` ignores `db_path` after a thread's first call** — `database.py`
  Misleading parameter; every real caller passes nothing. Fix: drop the parameter.

- [x] **9. Health check loads every fingerprint** — `quiz/service.py::health`
  Full-column scan just to prove DB connectivity. Fix: `SELECT 1`.

- [x] **10. Unstable pagination on `created_at` ties** — `question_repo.py`
  `ORDER BY created_at` with no tiebreaker; imports preserve timestamps so ties are real.
  Fix: add `, id` to the ORDER BY in `list_questions` / `list_all_for_export`.

- [x] **11. Re-ingest subprocess is fire-and-forget** — `quiz/router.py::_run_reingest`
  `check=False`, output discarded — failures are invisible; concurrent re-ingests of the same
  document are possible. Fix: capture and log output; guard against concurrent re-ingest per doc.

- [x] **12. Review UI escaping inconsistency** — `static/review/index.html`
  `q.model`, `q.prompt_version`, and `err.message` are interpolated into `innerHTML` unescaped
  while everything else uses `textContent`. Fix: build those nodes with `textContent`.

- [x] **13. SM-2 uses local `date.today()`** — `srs/service.py`, `srs/repository.py`
  Everything else stores UTC; near-midnight scheduling drift. Fix: `datetime.now(timezone.utc).date()`.

## Hygiene

- [x] **14. Ruff findings (8)** — unused imports in tests + `srs/service.py`, unused locals in
  `compare_models.py` / `test_loader.py`, one placeholder-less f-string. Fix: `ruff check --fix`
  plus two manual removals.

- [x] **15. No CI** — add a GitHub Actions workflow running `ruff check` + `pytest`.

- [x] **16. Double fingerprint computation** — `scripts/ingest.py` calls `fingerprint()` then
  `is_duplicate()` which recomputes it. Fix: check `fp in existing_fingerprints` directly.
