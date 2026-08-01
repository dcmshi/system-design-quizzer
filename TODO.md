# TODO — Audit Findings

One section per audit, newest first.

---

# Frontend & Design Audit (2026-08-01)

43 findings across the three static pages. All addressed on 2026-08-01, one commit
per fix, each with a test. The suite went from no frontend coverage at all to 82
jsdom tests plus 46 Python tests over the static assets and the palette.

## Bugs & data risks

- [x] **1. Retry-missed wrote answers into a finished session** — `replayMissed()` reset the
  questions and score but left `state.quizSessionId` set, so retried answers were POSTed to a
  session `finishQuizSession` had already closed, skewing its stats. Fix: clear the session ids
  so retries fall back to the standalone `/answer` endpoint.

- [x] **2. XSS via `showError()`** — the message went straight to `innerHTML` while callers
  interpolated a document title from the DB and a `detail` string from the API. Fix: `showError()`
  takes string-or-Node parts, so untrusted text lands as a text node and only `<strong>`, `<br>`
  and `<code>` are passed as elements. Same treatment for the SRS end pill.

- [x] **3. Near-duplicate badge was a fake button** — a `<span>` with a click listener: not
  focusable, not keyboard-operable, not announced. Fix: a real `<button>` with
  `aria-expanded`/`aria-controls`, built once instead of twice.

- [x] **4. A failed answer destroyed the quiz** — the catch swapped to the full-screen error state
  whose "Try Again" returns to setup, losing all progress. Fix: an inline `role="alert"` on the
  question screen; picking an option retries.

## Performance

- [x] **5. Review page fired 41 requests per page** — the list, then `/answer` and `/{id}` per
  item. Fix: a `QuestionListItem` schema carrying the answer, provenance and hit-rate counts (one
  grouped query), so a page load is one request. The quiz endpoints keep the answer-free
  `QuestionSummary`. Side effect: the hit-rate badge works again — it read `times_answered` off a
  row that never carried it, so every card said "Never attempted".

- [x] **6. Stats screen was N+1** — `/srs/due` once per document. Fix: `GET /srs/due/by-document`.

- [x] **7. Near-duplicate map refetched on every reject/delete** — every pair in the bank reloaded
  for one local change. Fix: `forgetNearDupes()` invalidates in memory.

- [x] **8. Monolithic inline assets** — ~600 lines of CSS and ~800 of JS inline per page, nothing
  cacheable, tokens already drifted. Fix: `css/app.css` + per-page CSS/JS files.

## UX

- [x] **9. No double-submit guard** — Start created a second session on a double click; each bulk
  handler disabled only its own button. Fixed both.
- [x] **10. SRS ignored multi-select** — read `selectedOptions[0]` while random and weak mode read
  all. Fix: `/srs/due` takes a repeatable `document_id`, `/srs/sessions` takes `document_ids`.
- [x] **11. `alert()` mixed with the toast** — seven failures routed through the existing toast.
  `confirm()` on destructive actions is deliberately left as-is.
- [x] **12. "Finishing session…" flash** on every random quiz — the pill now shows only for SRS.
- [x] **13. Stale "Showing X–Y of N"** as cards faded out — `renderSummary()` derives it from the
  cards actually present.
- [x] **14. Emptied page after a bulk action** stranded the user on a page that no longer existed.
- [x] **15. Silent document-list failure** looked like an empty bank — the hint now names it.
- [x] **16. `<select multiple>` picker** replaced with a checkbox list.
- [x] **17. No unsaved-progress guard** — `beforeunload` while a question is showing.

## Accessibility

- [x] **18. Fake keyboard focus** on options — the digit keys now move real DOM focus.
- [x] **19. No live regions** — results, the correct option letter and the score are announced.
- [x] **20. Colour-only feedback** — answered options carry a tick or cross.
- [x] **21. Contrast** — measured every pair in use and fixed six failures (worst: `.kb-hint` at
  2.35:1, a zero due-count at 1.35:1). `tests/test_css_contrast.py` locks the palette.
- [x] **22. Focus styles** — inputs set `outline:none`, buttons had none. One shared focus ring.
- [x] **23. Mode toggle** — `role="group"` + `aria-pressed`.
- [x] **24. Unnamed icon controls** — the exit button and the per-card checkbox.
- [x] **25. Flex centring clipped tall content** — `margin:auto` on `#app` instead.
- [x] **26. No `prefers-reduced-motion` handling.**
- [x] **27. Missing favicon and description meta** — every load 404'd on `/favicon.ico`.
- [x] **28. Status badges** — no change needed; they carry text. The near-dupe badge is item 3.

## Design & consistency

- [x] **29. Tokens duplicated three times** → one `:root` in `app.css` (item 8).
- [x] **30. Hardcoded hex** → `--badge-*` pairs and `--tint-*` fills; a test forbids literals
  outside the shared sheet.
- [x] **31. Inline styles** → a `.hidden` utility plus `.btn-block` / `.btn-compact`; only the
  progress bar's computed width remains.
- [x] **32. Hand-rolled link rows** → one `.nav-links` + `.back-link`.
- [x] **33. Radius drift** → `--radius-sm/md/lg/xl/pill`.
- [x] **34. Toast only on the review page** → `js/toast.js` and `.inline-error` shared.
- [x] **35. Dark-only theme** → `color-scheme: dark`.

## Code quality

- [x] **36. Stale `state.mode` comment** — `'weak'` was undocumented.
- [x] **37. Duplicated fetch/error boilerplate** → `js/api.js` (`api` + `apiPost/Put/Patch/Delete`),
  which also handles the 204 from DELETE that `res.json()` threw on. Removed the dead
  `fetchQuestions()`.
- [x] **38. Five copies of fade-out-and-remove** → `removeCards()`.
- [x] **39. Bulk approve/reject near-identical** → `bulkSetStatus()`, which also gives bulk reject
  the near-duplicate invalidation single reject already had.
- [x] **40. Sort-direction knowledge duplicated** in sources → `defaultSortDir()`.
- [x] **41. `behavior: 'instant'`** is non-standard → `'auto'`.
- [x] **42. No option-label guard** — `LABELS[i]` returned undefined past D and `prefillForm()`
  threw outright. Both handle a malformed question now.
- [x] **43. No frontend tests** — `tests/js/harness.mjs` boots a page in jsdom against a stubbed
  fetch, inlining each page's scripts from disk. Runs as its own CI job.

---

# Code Audit Findings (2026-07-16)

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
