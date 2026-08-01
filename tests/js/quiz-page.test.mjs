import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { answer, bootQuiz, startQuiz } from './fixtures.mjs';

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
