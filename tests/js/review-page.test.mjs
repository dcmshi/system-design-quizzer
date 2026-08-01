import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bootReview, makeItems } from './fixtures.mjs';
import { reply } from './harness.mjs';

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

  it('locks every bulk action while one is in flight', async () => {
    const page = await bootReview();
    pages.push(page);
    const bulkButtons = () =>
      ['#bulk-approve-btn', '#bulk-reject-btn', '#bulk-delete-btn'].map((s) => page.$(s));

    page.$('.card-checkbox').click();
    page.$('#bulk-approve-btn').click();
    assert.ok(bulkButtons().every((b) => b.disabled), 'all locked during the request');

    await page.flush();
    await page.wait(250);
    assert.ok(bulkButtons().every((b) => b.disabled), 'all disabled again with nothing selected');

    page.$('.card-checkbox').click();
    assert.ok(bulkButtons().every((b) => !b.disabled));
  });
});

describe('review page — failure feedback', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('reports a failed save through the toast, not a native alert', async () => {
    const page = await bootReview({ 'PUT /api/v1/questions/*': reply(409, { detail: 'duplicate' }) });
    pages.push(page);

    page.$('.question-card .btn-edit').click();
    page.$('.question-card .btn-save').click();
    await page.flush();

    assert.deepEqual(page.alerts, []);
    assert.equal(page.text('#toast'), 'Save failed: duplicate');
    assert.ok(page.$('#toast').classList.contains('error'));
  });

  it('reports a failed status change through the toast', async () => {
    const page = await bootReview({
      'PATCH /api/v1/questions/*/status': reply(500, { detail: 'db down' }),
    });
    pages.push(page);

    page.$('.question-card .btn-approve').click();
    await page.flush();

    assert.deepEqual(page.alerts, []);
    assert.equal(page.text('#toast'), 'Action failed: db down');
  });

  it('rejects an empty edit through the toast', async () => {
    const page = await bootReview();
    pages.push(page);

    const card = page.$('.question-card');
    card.querySelector('.btn-edit').click();
    card.querySelector('[name=question]').value = '   ';
    card.querySelector('.btn-save').click();
    await page.flush();

    assert.deepEqual(page.alerts, []);
    assert.match(page.text('#toast'), /all four options are required/);
    assert.ok(!page.calls.some((c) => c.method === 'PUT'));
  });

  it('announces the toast to assistive technology', async () => {
    const page = await bootReview({
      'PATCH /api/v1/questions/*/status': reply(500, { detail: 'db down' }),
    });
    pages.push(page);
    assert.equal(page.$('#toast'), null, 'built only when something needs saying');

    page.$('.question-card .btn-approve').click();
    await page.flush();

    assert.equal(page.$('#toast').getAttribute('role'), 'status');
    assert.equal(page.$('#toast').getAttribute('aria-live'), 'polite');
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

describe('review page — removing cards', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('removes every selected card on bulk delete', async () => {
    const page = await bootReview({ items: makeItems(3) });
    pages.push(page);

    page.$$('.card-checkbox').slice(0, 2).forEach((cb) => cb.click());
    page.$('#bulk-delete-btn').click();
    await page.flush();
    await page.wait(250);

    assert.deepEqual(page.$$('.question-card').map((c) => c.dataset.id), ['Q3']);
  });

  it('keeps the "Showing X of N" summary in step with the list', async () => {
    const page = await bootReview({ items: makeItems(3) });
    pages.push(page);
    assert.equal(page.text('#summary'), 'Showing 1–3 of 3 questions');

    page.$('.question-card .btn-delete').click();
    await page.flush();
    await page.wait(250);
    assert.equal(page.text('#summary'), 'Showing 1–2 of 2 questions');

    page.$('.question-card .btn-reject').click();
    await page.flush();
    await page.wait(250);
    assert.equal(page.text('#summary'), 'Showing 1–1 of 1 question');
  });

  it('steps back a page when the last page is emptied', async () => {
    const all = makeItems(25);
    const deleted = new Set();
    const remaining = () => all.filter((q) => !deleted.has(q.id));
    const page = await bootReview({
      'GET /api/v1/questions': ({ url }) => {
        const offset = Number(new URL(url, 'http://localhost').searchParams.get('offset'));
        const items = remaining();
        return { items: items.slice(offset, offset + 20), total: items.length, limit: 20, offset };
      },
      'DELETE /api/v1/questions/*': ({ path }) => { deleted.add(path.split('/').pop()); return {}; },
    });
    pages.push(page);

    page.$$('#pagination .page-btn').at(-1).click();  // Next
    await page.flush();
    assert.equal(page.$$('.question-card').length, 5);

    page.$('#select-all').click();
    page.$('#bulk-delete-btn').click();
    await page.flush();
    await page.wait(250);
    await page.flush();

    assert.equal(page.$$('.question-card').length, 20);
    assert.equal(page.text('#summary'), 'Showing 1–20 of 20 questions');
    assert.equal(page.text('#pagination'), '');  // one page left, no pager
  });

  it('falls back to the empty state when the last card goes', async () => {
    const page = await bootReview({ items: makeItems(1) });
    pages.push(page);

    page.$('.question-card .btn-delete').click();
    await page.flush();
    await page.wait(250);

    assert.equal(page.$$('.question-card').length, 0);
    assert.match(page.text('#question-list'), /No questions match/);
    assert.equal(page.text('#summary'), '0 questions');
  });
});

describe('review page — bulk status changes', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('removes cards that stop matching the active filter', async () => {
    const page = await bootReview({ items: makeItems(3) });
    pages.push(page);

    page.$$('.card-checkbox').slice(0, 2).forEach((cb) => cb.click());
    page.$('#bulk-approve-btn').click();
    await page.flush();
    await page.wait(250);

    assert.deepEqual(page.$$('.question-card').map((c) => c.dataset.id), ['Q3']);
    assert.equal(page.calls.find((c) => c.path === '/api/v1/questions/bulk-status').body.status,
      'approved');
  });

  it('updates the badges in place under "All statuses"', async () => {
    const page = await bootReview({ items: makeItems(2) });
    pages.push(page);

    page.$('#filter-status').value = '';
    page.$$('.card-checkbox').forEach((cb) => cb.click());
    page.$('#bulk-reject-btn').click();
    await page.flush();

    assert.equal(page.$$('.question-card').length, 2);
    assert.deepEqual(page.$$('[data-status-badge]').map((b) => b.textContent),
      ['rejected', 'rejected']);
    assert.ok(page.$('[data-status-badge]').classList.contains('badge-rejected'));
  });

  it('names the action it failed at', async () => {
    const page = await bootReview({
      'POST /api/v1/questions/bulk-status': reply(500, { detail: 'locked' }),
    });
    pages.push(page);

    page.$('.card-checkbox').click();
    page.$('#bulk-reject-btn').click();
    await page.flush();

    assert.equal(page.text('#toast'), 'Bulk reject failed: locked');
  });

  it('forgets near-duplicate pairings for bulk-rejected questions', async () => {
    const page = await bootReview({
      'GET /api/v1/questions/near-duplicates': DUPE_PAIR,
      items: makeItems(3),
    });
    pages.push(page);
    assert.equal(page.$$('[data-near-dupe-badge]').length, 2);

    page.$('#filter-status').value = '';
    page.$$('.card-checkbox')[0].click();
    page.$('#bulk-reject-btn').click();
    await page.flush();

    assert.equal(page.$$('[data-near-dupe-badge]').length, 0);
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

  it('drops the pairing locally on delete instead of refetching the bank', async () => {
    const page = await bootWithDupes();

    page.$('.question-card .btn-delete').click();
    await page.flush();
    await page.wait(250);

    assert.equal(page.$$('.question-card').length, 1);
    assert.equal(page.$('[data-near-dupe-badge]'), null);
    assert.equal(page.calls.filter((c) => c.path === '/api/v1/questions/near-duplicates').length, 1);
  });

  it('drops the pairing locally on reject instead of refetching the bank', async () => {
    const page = await bootWithDupes();

    page.$('.question-card .btn-reject').click();
    await page.flush();
    await page.wait(250);

    assert.equal(page.$$('.question-card').length, 1);
    assert.equal(page.$('[data-near-dupe-badge]'), null);
    assert.equal(page.calls.filter((c) => c.path === '/api/v1/questions/near-duplicates').length, 1);
  });
});

describe('review page — control labels', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('names the per-card selection checkbox', async () => {
    const page = await bootReview();
    pages.push(page);

    assert.equal(
      page.$('.card-checkbox').getAttribute('aria-label'),
      'Select this question for bulk actions',
    );
  });
});

describe('shared API helper', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('surfaces the server detail rather than a bare status code', async () => {
    const page = await bootReview({
      'GET /api/v1/questions': reply(500, { detail: 'index corrupt' }),
    });
    pages.push(page);

    assert.match(page.text('#question-list'), /Failed to load questions: index corrupt/);
  });

  it('falls back to the status code when there is no detail', async () => {
    const page = await bootReview({ 'GET /api/v1/questions': reply(502, {}) });
    pages.push(page);

    assert.match(page.text('#question-list'), /Failed to load questions: HTTP 502/);
  });

  it('tolerates a 204 with no body', async () => {
    const page = await bootReview({ 'DELETE /api/v1/questions/*': reply(204, null) });
    pages.push(page);

    page.$('.question-card .btn-delete').click();
    await page.flush();
    await page.wait(250);

    assert.equal(page.$$('.question-card').length, 1);
    assert.deepEqual(page.alerts, []);
  });
});

describe('review page — malformed questions', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('labels every option even when there are more than four', async () => {
    const items = makeItems(1);
    items[0] = { ...items[0], options: ['A1', 'B1', 'C1', 'D1', 'E1'] };
    const page = await bootReview({ items });
    pages.push(page);

    assert.deepEqual(
      page.$$('.card-options .option-label').map((s) => s.textContent),
      ['A.', 'B.', 'C.', 'D.', '5.'],
    );
  });
});
