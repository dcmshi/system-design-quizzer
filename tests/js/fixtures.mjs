// Page fixtures shared by the frontend tests.
//
// These live outside the *.test.mjs files so a second test file for the same
// page can reuse them without re-registering the first file's tests.

import { loadPage, makeQuestions } from './harness.mjs';

export const QUIZ_DOCS = [
  { id: 'DOC1', title: 'Consistent Hashing', question_count: 12 },
  { id: 'DOC2', title: 'Load Balancers', question_count: 7 },
];

export function quizRoutes(overrides = {}) {
  return {
    'GET /api/v1/documents': QUIZ_DOCS,
    'GET /api/v1/tags': ['caching', 'sharding'],
    'GET /api/v1/srs/due': { due_count: 3, new_count: 4, total_actionable: 7 },
    'GET /api/v1/quiz/weak-count': { weak_count: 5 },
    'POST /api/v1/quiz/sessions': { session_id: 'S1', questions: makeQuestions(2), started_at: 'now' },
    'POST /api/v1/quiz/sessions/*/answers': { correct: true, correct_index: 0, explanation: 'Because.' },
    'POST /api/v1/quiz/sessions/*/finish': {
      session_id: 'S1', finished_at: 'now', n_answered: 2, n_correct: 2, n_wrong: 0, n_skipped: 0,
    },
    'POST /api/v1/questions/*/answer': { correct: true, correct_index: 0, explanation: 'Because.' },
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

export const REVIEW_DOCS = [{ id: 'DOC1', title: 'Consistent Hashing' }];

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

export function reviewRoutes({ items = makeItems(2), ...overrides } = {}) {
  return {
    'GET /api/v1/documents': REVIEW_DOCS,
    'GET /api/v1/questions/models': ['mock-model'],
    'GET /api/v1/questions/prompt-versions': ['v1'],
    'GET /api/v1/questions/near-duplicates': [],
    // The list endpoint carries answers and provenance; per-item GETs are
    // deliberately unstubbed so reintroducing them fails the tests.
    'GET /api/v1/questions': { items, total: items.length, limit: 20, offset: 0 },
    'PATCH /api/v1/questions/*/status': ({ body }) => ({ status: body.status }),
    'PUT /api/v1/questions/*': {},
    'DELETE /api/v1/questions/*': {},
    'POST /api/v1/questions/bulk-status': { updated: 1 },
    ...overrides,
  };
}

export async function bootReview(overrides = {}) {
  return loadPage('review/index.html', { routes: reviewRoutes(overrides) });
}

export const SOURCE_DOCS = [
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
    routes: { 'GET /api/v1/documents': SOURCE_DOCS, ...overrides },
  });
}
