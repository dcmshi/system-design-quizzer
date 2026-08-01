import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { loadPage } from './harness.mjs';

const DOCS = [{ id: 'DOC1', title: 'Consistent Hashing' }];

export function makeItems(n) {
  return Array.from({ length: n }, (_, i) => ({
    id: `Q${i + 1}`,
    question: `Question ${i + 1}?`,
    options: ['Alpha', 'Bravo', 'Charlie', 'Delta'],
    difficulty: 'medium',
    source_document_id: 'DOC1',
    status: 'generated',
    correct_index: 1,
    explanation: `Explanation ${i + 1}.`,
    model: 'mock-model',
    prompt_version: 'v1',
    times_answered: 0,
    times_correct: 0,
    hit_rate: null,
  }));
}

export function reviewRoutes(overrides = {}) {
  const items = overrides.items ?? makeItems(2);
  delete overrides.items;
  return {
    'GET /api/v1/documents': DOCS,
    'GET /api/v1/questions/models': ['mock-model'],
    'GET /api/v1/questions/prompt-versions': ['v1'],
    'GET /api/v1/questions/near-duplicates': [],
    'GET /api/v1/questions': { items, total: items.length, limit: 20, offset: 0 },
    'GET /api/v1/questions/*': ({ path }) => items.find((q) => path.endsWith(`/${q.id}`)) ?? {},
    'GET /api/v1/questions/*/answer': ({ path }) => {
      const q = items.find((it) => path.includes(`/${it.id}/`));
      return { correct_index: q?.correct_index ?? 0, explanation: q?.explanation ?? '' };
    },
    'PATCH /api/v1/questions/*/status': { id: 'Q1', status: 'approved' },
    'PUT /api/v1/questions/*': {},
    'DELETE /api/v1/questions/*': {},
    'POST /api/v1/questions/bulk-status': { updated: 1 },
    ...overrides,
  };
}

export async function bootReview(overrides = {}) {
  return loadPage('review/index.html', { routes: reviewRoutes(overrides) });
}

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
