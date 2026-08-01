import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { loadPage } from './harness.mjs';

const DOCS = [
  {
    id: 'DOC1', title: 'Consistent Hashing', source: 'blog', tags: ['sharding'],
    source_path: 'content/hashing.md', created_at: '2026-01-02T00:00:00Z',
    question_count: 12, chunk_count: 4, word_count: 2400,
  },
  {
    id: 'DOC2', title: 'Load Balancers', source: 'book', tags: ['networking'],
    source_path: 'content/lb.md', created_at: '2026-02-03T00:00:00Z',
    question_count: 0, chunk_count: 2, word_count: 900,
  },
];

export async function bootSources(overrides = {}) {
  return loadPage('sources/index.html', {
    routes: { 'GET /api/v1/documents': DOCS, ...overrides },
  });
}

describe('sources page', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  it('boots without script errors and lists every document', async () => {
    const page = await bootSources();
    pages.push(page);

    assert.deepEqual(page.errors, []);
    assert.equal(page.$$('#doc-body tr').length, 2);
    assert.equal(page.text('#summary'), '2 articles');
  });

  it('filters by search text', async () => {
    const page = await bootSources();
    pages.push(page);

    const search = page.$('#search');
    search.value = 'load';
    search.dispatchEvent(new page.window.Event('input'));

    assert.equal(page.$$('#doc-body tr').length, 1);
    assert.match(page.$('#doc-body tr').textContent, /Load Balancers/);
    assert.equal(page.text('#summary'), '1 of 2 articles');
  });

  it('sorts numeric columns descending first', async () => {
    const page = await bootSources();
    pages.push(page);

    page.$$('thead th[data-col]').find((th) => th.dataset.col === 'question_count').click();
    const first = page.$('#doc-body tr').textContent;
    assert.match(first, /Consistent Hashing/);
  });
});
