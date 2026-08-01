import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bootReview, makeItems } from './fixtures.mjs';

const DUPE_PAIR = [
  { id_a: 'Q1', question_a: 'Question 1?', id_b: 'Q2', question_b: 'Question 2?', similarity: 0.82 },
];

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

describe('review page — request volume', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('loads a page of questions with a single questions request', async () => {
    const page = await bootReview({ items: makeItems(20) });
    pages.push(page);

    assert.equal(page.$$('.question-card').length, 20);
    const questionCalls = page.calls.filter((c) => c.path.startsWith('/api/v1/questions/'));
    assert.deepEqual(
      questionCalls.map((c) => c.path).sort(),
      ['/api/v1/questions/models', '/api/v1/questions/near-duplicates', '/api/v1/questions/prompt-versions'],
    );
    assert.equal(page.calls.filter((c) => c.path === '/api/v1/questions').length, 1);
  });

  it('renders the hit rate that now comes with the list', async () => {
    const items = makeItems(1);
    items[0] = { ...items[0], times_answered: 4, times_correct: 3, hit_rate: 0.75 };
    const page = await bootReview({ items });
    pages.push(page);

    const badge = page.$('.hit-rate');
    assert.equal(badge.textContent, '75% hit rate (3/4)');
    assert.ok(badge.classList.contains('hit-rate-mid'));
  });
});

describe('review page — near-duplicate badge', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  async function bootWithDupes() {
    const page = await bootReview({ 'GET /api/v1/questions/near-duplicates': DUPE_PAIR });
    pages.push(page);
    return page;
  }

  it('is a real button wired to the panel it toggles', async () => {
    const page = await bootWithDupes();

    const badge = page.$('[data-near-dupe-badge]');
    const panel = page.$('[data-near-dupe-panel]');
    assert.equal(badge.tagName, 'BUTTON');
    assert.equal(badge.type, 'button');
    assert.equal(badge.getAttribute('aria-expanded'), 'false');
    assert.equal(badge.getAttribute('aria-controls'), panel.id);
    assert.ok(panel.id);
  });

  it('opens the panel on click and reports the new state', async () => {
    const page = await bootWithDupes();

    const badge = page.$('[data-near-dupe-badge]');
    const panel = page.$('[data-near-dupe-panel]');

    badge.click();
    assert.ok(panel.classList.contains('open'));
    assert.equal(badge.getAttribute('aria-expanded'), 'true');
    assert.match(panel.textContent, /82% similar/);

    badge.click();
    assert.ok(!panel.classList.contains('open'));
    assert.equal(badge.getAttribute('aria-expanded'), 'false');
  });

  it('gives each card its own panel id', async () => {
    const page = await bootWithDupes();

    const ids = page.$$('[data-near-dupe-panel]').map((p) => p.id);
    assert.equal(ids.length, 2);
    assert.equal(new Set(ids).size, 2);
  });
});
