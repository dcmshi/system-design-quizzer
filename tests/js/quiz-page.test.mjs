import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { loadPage, makeQuestions } from './harness.mjs';

const DOCS = [
  { id: 'DOC1', title: 'Consistent Hashing', question_count: 12 },
  { id: 'DOC2', title: 'Load Balancers', question_count: 7 },
];

export function quizRoutes(overrides = {}) {
  return {
    'GET /api/v1/documents': DOCS,
    'GET /api/v1/tags': ['caching', 'sharding'],
    'GET /api/v1/srs/due': { due_count: 3, new_count: 4, total_actionable: 7 },
    'GET /api/v1/quiz/weak-count': { weak_count: 5 },
    'POST /api/v1/quiz/sessions': { session_id: 'S1', questions: makeQuestions(2), started_at: 'now' },
    'POST /api/v1/quiz/sessions/*/answers': { correct: true, correct_index: 0, explanation: 'Because.' },
    'POST /api/v1/quiz/sessions/*/finish': {
      session_id: 'S1', finished_at: 'now', n_answered: 2, n_correct: 2, n_wrong: 0, n_skipped: 0,
    },
    ...overrides,
  };
}

export async function bootQuiz(overrides = {}) {
  return loadPage('index.html', { routes: quizRoutes(overrides) });
}

/** Start a quiz and land on the question screen. */
export async function startQuiz(page) {
  page.$('#btn-start').click();
  await page.flush();
}

/** Answer the currently displayed question by option index. */
export async function answer(page, index = 0) {
  page.$$('#options-container .option-btn')[index].click();
  await page.flush();
}

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
