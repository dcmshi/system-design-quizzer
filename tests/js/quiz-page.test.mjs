import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { answer, bootQuiz, startQuiz } from './fixtures.mjs';
import { reply } from './harness.mjs';

/** Grade Q1 wrong and everything else right. */
const gradeQ1Wrong = ({ body }) => ({
  correct: body.question_id !== 'Q1',
  correct_index: 0,
  explanation: 'Because.',
});

describe('quiz page', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('boots without script errors and populates the document picker', async () => {
    const page = await bootQuiz();
    pages.push(page);

    assert.deepEqual(page.errors, []);
    const options = page.$$('#input-doc option').map((o) => o.textContent);
    assert.deepEqual(options, ['Consistent Hashing (12 Q)', 'Load Balancers (7 Q)']);
    assert.ok(page.$('#screen-setup').classList.contains('active'));
  });

  it('runs a full random quiz from setup to results', async () => {
    const page = await bootQuiz();
    pages.push(page);

    await startQuiz(page);
    assert.ok(page.$('#screen-question').classList.contains('active'));
    assert.equal(page.text('#progress-label'), 'Question 1 of 2');
    assert.equal(page.$$('#options-container .option-btn').length, 4);

    await answer(page, 0);
    assert.ok(page.$('#explanation').classList.contains('visible'));

    page.$('#btn-next').click();
    await page.flush();
    assert.equal(page.text('#progress-label'), 'Question 2 of 2');
    assert.equal(page.text('#score-label'), 'Score: 1');

    await answer(page, 0);
    page.$('#btn-next').click();
    await page.flush();

    assert.ok(page.$('#screen-end').classList.contains('active'));
    assert.equal(page.text('#end-pct'), '100%');
    assert.ok(page.calls.some((c) => c.path === '/api/v1/quiz/sessions/S1/finish'));
  });

  it('sends answers to the session endpoint, not the standalone one', async () => {
    const page = await bootQuiz();
    pages.push(page);

    await startQuiz(page);
    await answer(page, 0);

    assert.ok(page.calls.some((c) => c.path === '/api/v1/quiz/sessions/S1/answers'));
    assert.ok(!page.calls.some((c) => c.path.endsWith('/answer')));
  });
});

describe('quiz page — retry missed', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  /** Play both questions, getting Q1 wrong, and land on the end screen. */
  async function playToEnd() {
    const page = await bootQuiz({ 'POST /api/v1/quiz/sessions/*/answers': gradeQ1Wrong });
    pages.push(page);

    await startQuiz(page);
    await answer(page, 1);
    page.$('#btn-next').click();
    await page.flush();
    await answer(page, 0);
    page.$('#btn-next').click();
    await page.flush();
    return page;
  }

  it('offers a retry for the missed question', async () => {
    const page = await playToEnd();

    assert.equal(page.$('#btn-retry-missed').style.display, 'block');
    assert.equal(page.text('#btn-retry-missed'), 'Retry missed (1)');
  });

  it('replays retried answers outside the finished session', async () => {
    const page = await playToEnd();

    page.$('#btn-retry-missed').click();
    await page.flush();
    assert.equal(page.text('#progress-label'), 'Question 1 of 1');

    const before = page.calls.length;
    await answer(page, 0);
    const during = page.calls.slice(before);

    assert.deepEqual(during.map((c) => c.path), ['/api/v1/questions/Q1/answer']);
  });
});

describe('quiz page — error screen', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  const EVIL = '<img src=x onerror="window.__pwned = true">';

  it('renders a document title from the database as text, not markup', async () => {
    const page = await bootQuiz({
      'GET /api/v1/documents': [{ id: 'DOC1', title: EVIL, question_count: 3 }],
      'POST /api/v1/quiz/sessions': { session_id: 'S1', questions: [], started_at: 'now' },
    });
    pages.push(page);

    page.$$('#input-doc option')[0].selected = true;
    await startQuiz(page);

    assert.ok(page.$('#screen-error').classList.contains('active'));
    assert.equal(page.$('#error-msg img'), null);
    assert.equal(page.window.__pwned, undefined);
    assert.match(page.text('#error-msg'), /<img src=x/);
  });

  it('renders an API error detail as text, not markup', async () => {
    const page = await bootQuiz({
      'POST /api/v1/quiz/sessions': reply(500, { detail: EVIL }),
    });
    pages.push(page);

    await startQuiz(page);

    assert.ok(page.$('#screen-error').classList.contains('active'));
    assert.equal(page.$('#error-msg img'), null);
    assert.equal(page.window.__pwned, undefined);
    assert.match(page.text('#error-msg'), /<img src=x/);
  });

  it('still formats the ingest hint with real markup', async () => {
    const page = await bootQuiz({
      'POST /api/v1/quiz/sessions': { session_id: 'S1', questions: [], started_at: 'now' },
    });
    pages.push(page);

    await startQuiz(page);

    assert.match(page.text('#error-msg code'), /scripts\/ingest\.py/);
  });
});

describe('quiz page — SRS stats screen', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  const BY_DOC = [
    { document_id: 'DOC2', due_count: 1, new_count: 2, total_actionable: 3 },
    { document_id: 'DOC1', due_count: 5, new_count: 0, total_actionable: 5 },
  ];

  async function openStats(overrides = {}) {
    const page = await bootQuiz({ 'GET /api/v1/srs/due/by-document': BY_DOC, ...overrides });
    pages.push(page);
    page.$('#link-stats').click();
    await page.flush();
    return page;
  }

  it('reads per-document counts in one call instead of one per document', async () => {
    const page = await openStats();

    assert.equal(page.calls.filter((c) => c.path === '/api/v1/srs/due').length, 1);
    assert.equal(page.calls.filter((c) => c.path === '/api/v1/srs/due/by-document').length, 1);
  });

  it('joins the bulk counts onto the document rows, busiest first', async () => {
    const page = await openStats();

    const rows = page.$$('#doc-table-body tr').map((tr) =>
      [...tr.children].map((td) => td.textContent));
    assert.deepEqual(rows, [
      ['Consistent Hashing', '5', '0', '12'],
      ['Load Balancers', '1', '2', '7'],
    ]);
    assert.equal(page.text('#stats-due'), '3');
  });

  it('shows zeroes for a document with no SRS rows', async () => {
    const page = await openStats({ 'GET /api/v1/srs/due/by-document': [] });

    const first = page.$('#doc-table-body tr');
    assert.deepEqual([...first.children].map((td) => td.textContent),
      ['Consistent Hashing', '0', '0', '12']);
  });
});

describe('quiz page — failed answer submission', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  /** Boot a quiz whose answer endpoint fails until `state.fail` is cleared. */
  async function bootFlaky() {
    const state = { fail: true };
    const page = await bootQuiz({
      'POST /api/v1/quiz/sessions/*/answers': () => (state.fail
        ? reply(503, { detail: 'upstream down' })
        : { correct: true, correct_index: 0, explanation: 'Because.' }),
    });
    pages.push(page);
    await startQuiz(page);
    return { page, state };
  }

  it('keeps the user on the question instead of tearing the quiz down', async () => {
    const { page } = await bootFlaky();

    await answer(page, 0);

    assert.ok(page.$('#screen-question').classList.contains('active'));
    assert.ok(!page.$('#screen-error').classList.contains('active'));
    assert.equal(page.text('#progress-label'), 'Question 1 of 2');
  });

  it('shows the failure inline and re-enables the options', async () => {
    const { page } = await bootFlaky();

    await answer(page, 0);

    const inlineError = page.$('#answer-error');
    assert.ok(inlineError.classList.contains('visible'));
    assert.match(inlineError.textContent, /upstream down/);
    assert.equal(inlineError.getAttribute('role'), 'alert');
    assert.ok(page.$$('#options-container .option-btn').every((b) => !b.disabled));
  });

  it('lets the same answer succeed on a retry', async () => {
    const { page, state } = await bootFlaky();

    await answer(page, 0);
    state.fail = false;
    await answer(page, 0);

    assert.ok(!page.$('#answer-error').classList.contains('visible'));
    assert.ok(page.$('#explanation').classList.contains('visible'));
    assert.ok(page.$('#btn-next').classList.contains('visible'));
  });
});
