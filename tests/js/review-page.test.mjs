import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bootReview } from './fixtures.mjs';

describe('review page', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('boots without script errors and renders one card per question', async () => {
    const page = await bootReview();
    pages.push(page);

    assert.deepEqual(page.errors, []);
    assert.equal(page.$$('.question-card').length, 2);
    assert.equal(page.text('#summary'), 'Showing 1–2 of 2 questions');
  });

  it('marks the correct option and shows the explanation', async () => {
    const page = await bootReview();
    pages.push(page);

    const card = page.$('.question-card');
    const correct = card.querySelectorAll('.card-options li.correct');
    assert.equal(correct.length, 1);
    assert.match(correct[0].textContent, /Bravo/);
    assert.match(card.querySelector('.card-explanation').textContent, /Explanation 1\./);
  });

  it('tracks selection state in the bulk bar', async () => {
    const page = await bootReview();
    pages.push(page);

    page.$('.card-checkbox').click();
    assert.equal(page.text('#bulk-approve-btn'), 'Approve selected (1)');
    assert.equal(page.$('#bulk-approve-btn').disabled, false);
  });
});
