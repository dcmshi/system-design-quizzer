import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bootSources } from './fixtures.mjs';

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
    assert.match(page.$('#doc-body tr').textContent, /Consistent Hashing/);
  });
});

describe('sources page — sort defaults', () => {
  const pages = [];
  after(() => pages.forEach((p) => p.close()));

  const firstRow = (page) => page.$('#doc-body tr').textContent;

  it('starts text columns ascending and count columns descending', async () => {
    const page = await bootSources();
    pages.push(page);

    page.$$('thead th[data-col]').find((th) => th.dataset.col === 'word_count').click();
    assert.match(firstRow(page), /Consistent Hashing/, 'most words first');

    page.$$('thead th[data-col]').find((th) => th.dataset.col === 'title').click();
    assert.match(firstRow(page), /Consistent Hashing/, 'A before L');
  });

  it('uses the same defaults from the sort dropdown as from the headers', async () => {
    const page = await bootSources();
    pages.push(page);

    const select = page.$('#sort-by');
    select.value = 'chunk_count';
    select.dispatchEvent(new page.window.Event('change'));
    const fromDropdown = firstRow(page);

    const reloaded = await bootSources();
    pages.push(reloaded);
    reloaded.$$('thead th[data-col]').find((th) => th.dataset.col === 'chunk_count').click();

    assert.equal(fromDropdown, reloaded.$('#doc-body tr').textContent);
  });

  it('flips direction when the same header is clicked twice', async () => {
    const page = await bootSources();
    pages.push(page);
    const header = page.$$('thead th[data-col]').find((th) => th.dataset.col === 'question_count');

    header.click();
    assert.match(firstRow(page), /Consistent Hashing/);
    header.click();
    assert.match(firstRow(page), /Load Balancers/);
  });
});
