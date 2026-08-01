'use strict';

// ── Screens ──────────────────────────────────────────────────────────────
const screens = {
  setup:    document.getElementById('screen-setup'),
  loading:  document.getElementById('screen-loading'),
  question: document.getElementById('screen-question'),
  end:      document.getElementById('screen-end'),
  review:   document.getElementById('screen-review'),
  stats:    document.getElementById('screen-stats'),
  error:    document.getElementById('screen-error'),
};

let currentScreen = 'setup';

function showScreen(name) {
  Object.values(screens).forEach(s => s.classList.remove('active'));
  screens[name].classList.add('active');
  currentScreen = name;
}

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  questions: [],
  current: 0,
  score: 0,
  answered: false,
  totalRequested: 5,
  keyboardFocus: null,
  results: [],
  mode: 'random',        // 'random' | 'srs'
  srsSessionId: null,
  srsFinishData: null,
  quizSessionId: null,
};

// ── DOM refs ──────────────────────────────────────────────────────────────
const inputDoc     = document.getElementById('input-doc');
const docHint      = document.getElementById('doc-hint');
const inputN       = document.getElementById('input-n');
const inputTag     = document.getElementById('input-tag');
const inputDiff    = document.getElementById('input-diff');
const inputSrsN    = document.getElementById('input-srs-n');
const labelSrsN    = document.getElementById('label-srs-n');
const randomOnlyFields = document.getElementById('random-only-fields');
const btnStart     = document.getElementById('btn-start');
const btnModeRandom = document.getElementById('btn-mode-random');
const btnModeSrs   = document.getElementById('btn-mode-srs');
const btnModeWeak  = document.getElementById('btn-mode-weak');
const dueInfo      = document.getElementById('due-info');
const weakInfo     = document.getElementById('weak-info');
const weakPoolCount = document.getElementById('weak-pool-count');
const dueCount     = document.getElementById('due-count');
const newCount     = document.getElementById('new-count');
const progressFill     = document.getElementById('progress-fill');
const progressLbl      = document.getElementById('progress-label');
const shortfallNotice  = document.getElementById('shortfall-notice');
const scoreLbl     = document.getElementById('score-label');
const diffBadge    = document.getElementById('difficulty-badge');
const questionText = document.getElementById('question-text');
const optionsCont  = document.getElementById('options-container');
const answerError  = document.getElementById('answer-error');
const explanation  = document.getElementById('explanation');
const srsNextInfo  = document.getElementById('srs-next-info');
const srsIntervalText = document.getElementById('srs-interval-text');
const btnNext      = document.getElementById('btn-next');
const btnExit      = document.getElementById('btn-exit');
const endPct       = document.getElementById('end-pct');
const endFraction  = document.getElementById('end-fraction');
const endMsg       = document.getElementById('end-msg');
const srsEndInfo   = document.getElementById('srs-end-info');
const btnPlayAgain   = document.getElementById('btn-play-again');
const btnReview      = document.getElementById('btn-review');
const btnShowReview  = document.getElementById('btn-show-review');
const btnRetryMissed = document.getElementById('btn-retry-missed');
const btnBackEnd     = document.getElementById('btn-back-end');
const reviewList     = document.getElementById('review-list');
const errorTitle     = document.getElementById('error-title');
const errorMsg     = document.getElementById('error-msg');
const btnRetry     = document.getElementById('btn-retry');
const btnStatsBack    = document.getElementById('btn-stats-back');
const btnStatsStartSrs = document.getElementById('btn-stats-start-srs');
const statsDue     = document.getElementById('stats-due');
const statsNew     = document.getElementById('stats-new');
const statsTotal   = document.getElementById('stats-total');
const docTableBody = document.getElementById('doc-table-body');
const statsEmpty   = document.getElementById('stats-empty');

// ── Helpers ───────────────────────────────────────────────────────────────
const LABELS = ['A', 'B', 'C', 'D'];

/** Checkboxes for every document the user picked; empty means "all". */
function selectedDocuments() {
  return Array.from(inputDoc.querySelectorAll('input[type=checkbox]:checked'));
}

function selectedDocumentIds() {
  return selectedDocuments().map(cb => cb.value);
}

/** Repeatable ?document_id= query string, or '' for all documents. */
function documentQuery(documentIds) {
  if (!documentIds.length) return '';
  return '?' + documentIds.map(id => `document_id=${encodeURIComponent(id)}`).join('&');
}

function difficultyClass(d) {
  return { easy: 'badge-easy', medium: 'badge-medium', hard: 'badge-hard' }[d] || 'badge-unknown';
}

function scoreMessage(pct) {
  if (pct === 100) return 'Perfect score!';
  if (pct >= 80)  return 'Great work!';
  if (pct >= 60)  return 'Good effort!';
  if (pct >= 40)  return 'Keep practising.';
  return 'Keep studying — you\'ll get there!';
}

function formatInterval(days) {
  if (days <= 0) return 'today';
  if (days === 1) return 'in 1 day';
  return `in ${days} days`;
}

function el(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

// Parts are strings or Nodes: server- and DB-controlled text stays a string
// so it lands as a text node, and markup is passed as real elements.
function showError(title, ...parts) {
  errorTitle.textContent = title;
  errorMsg.replaceChildren(...parts);
  showScreen('error');
}

// ── Mode switching ─────────────────────────────────────────────────────────
function setMode(mode) {
  state.mode = mode;
  btnModeRandom.classList.toggle('active', mode === 'random');
  btnModeSrs.classList.toggle('active', mode === 'srs');
  btnModeWeak.classList.toggle('active', mode === 'weak');

  // Reset all mode-specific UI first
  randomOnlyFields.style.display = 'none';
  labelSrsN.style.display = 'none';
  inputSrsN.style.display = 'none';
  dueInfo.classList.remove('visible');
  weakInfo.classList.remove('visible');

  const labelDiff = document.getElementById('label-diff');

  if (mode === 'random') {
    randomOnlyFields.style.display = 'block';
    labelDiff.style.display = 'block';
    inputDiff.style.display = 'block';
    btnStart.textContent = 'Start Quiz';
  } else if (mode === 'srs') {
    labelSrsN.style.display = 'block';
    inputSrsN.style.display = 'block';
    dueInfo.classList.add('visible');
    btnStart.textContent = 'Start SRS Session';
    refreshDueInfo();
  } else {
    // weak — show n input but hide tag/diff (selected by history, not filter)
    randomOnlyFields.style.display = 'block';
    document.getElementById('label-tag').style.display = 'none';
    inputTag.style.display = 'none';
    inputDiff.value = '';
    labelDiff.style.display = 'none';
    inputDiff.style.display = 'none';
    weakInfo.classList.add('visible');
    btnStart.textContent = 'Start Weak Topics Quiz';
    refreshWeakCount();
  }
}

async function refreshDueInfo() {
  if (state.mode !== 'srs') return;
  try {
    const data = await loadDueInfo(selectedDocumentIds());
    dueCount.textContent = data.due_count;
    newCount.textContent = data.new_count;
  } catch (_) {
    dueCount.textContent = '?';
    newCount.textContent = '?';
  }
}

async function refreshWeakCount() {
  if (state.mode !== 'weak') return;
  try {
    let url = '/api/v1/quiz/weak-count' + documentQuery(selectedDocumentIds());
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      weakPoolCount.textContent = data.weak_count;
    }
  } catch (_) {
    weakPoolCount.textContent = '?';
  }
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────
const KEY_TO_INDEX = { '1': 0, '2': 1, '3': 2, '4': 3 };

function setKeyboardFocus(idx) {
  state.keyboardFocus = idx;
  optionsCont.querySelectorAll('.option-btn').forEach((b, i) => {
    b.classList.toggle('focused', i === idx);
  });
}

function clearKeyboardFocus() {
  state.keyboardFocus = null;
  optionsCont.querySelectorAll('.option-btn').forEach(b => b.classList.remove('focused'));
}

function handleKeyDown(e) {
  if (currentScreen !== 'question') return;

  const digit = KEY_TO_INDEX[e.key];
  if (digit !== undefined) {
    const btns = optionsCont.querySelectorAll('.option-btn');
    if (digit < btns.length && !state.answered) {
      e.preventDefault();
      setKeyboardFocus(digit);
    }
    return;
  }

  if (e.key === 'Enter' || e.key === ' ') {
    if (document.activeElement?.tagName === 'BUTTON') return;
    e.preventDefault();
    if (!state.answered && state.keyboardFocus !== null) {
      const btns = optionsCont.querySelectorAll('.option-btn');
      handleAnswer(state.keyboardFocus, btns[state.keyboardFocus]);
    } else if (state.answered && btnNext.classList.contains('visible')) {
      nextQuestion();
    }
    return;
  }

  if (e.key === 'ArrowRight') {
    if (state.answered && btnNext.classList.contains('visible')) {
      nextQuestion();
    }
  }
}

// ── API calls ─────────────────────────────────────────────────────────────
/** One checkbox row: a multi-select's ctrl-click semantics are undiscoverable
 *  on desktop and unusable on touch. */
function buildDocOption(doc) {
  const row = el('label');
  row.className = 'doc-option';
  const box = document.createElement('input');
  box.type = 'checkbox';
  box.value = doc.id;
  box.dataset.title = doc.title;
  const title = el('span', doc.title);
  title.className = 'doc-option-title';
  const count = el('span', `${doc.question_count} Q`);
  count.className = 'doc-option-count';
  row.append(box, title, count);
  return row;
}

async function fetchDocuments() {
  const res = await fetch('/api/v1/documents');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadDocuments() {
  try {
    const docs = await fetchDocuments();
    inputDoc.replaceChildren(...(docs.length
      ? docs.map(buildDocOption)
      : [Object.assign(el('div', 'No documents ingested yet.'), { className: 'doc-picker-empty' })]));
  } catch (err) {
    // Not fatal — a quiz with no document filter still works — but an empty
    // picker with no explanation looks like there is nothing to study.
    docHint.textContent =
      `Could not load the document list (${err.message}). Starting a quiz will use all documents.`;
    docHint.classList.add('input-hint-error');
  }
}

async function loadTags() {
  try {
    const res = await fetch('/api/v1/tags');
    if (!res.ok) return;
    const tags = await res.json();
    if (tags.length === 0) return;
    tags.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = t;
      inputTag.appendChild(opt);
    });
    document.getElementById('label-tag').style.display = 'block';
    inputTag.style.display = 'block';
  } catch (_) {}
}

async function fetchQuestions(n, difficulty, documentIds, tag) {
  let url = `/api/v1/quiz?n=${n}`;
  if (difficulty) url += `&difficulty=${encodeURIComponent(difficulty)}`;
  documentIds.forEach(id => { url += `&document_id=${encodeURIComponent(id)}`; });
  if (tag) url += `&tag=${encodeURIComponent(tag)}`;
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function submitAnswer(questionId, selectedIndex) {
  const res = await fetch(`/api/v1/questions/${questionId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selected_index: selectedIndex }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function startSrsSession(n, documentIds) {
  const body = { n, document_ids: documentIds };
  const res = await fetch('/api/v1/srs/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function submitSrsReview(sessionId, questionId, selectedIndex) {
  const res = await fetch(`/api/v1/srs/sessions/${sessionId}/reviews`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question_id: questionId, selected_index: selectedIndex }),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function finishSrsSession(sessionId) {
  const res = await fetch(`/api/v1/srs/sessions/${sessionId}/finish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function createQuizSession(n, difficulty, documentIds, tag, weak = false) {
  const res = await fetch('/api/v1/quiz/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      n,
      difficulty: difficulty || null,
      tag: tag || null,
      document_ids: documentIds,
      weak,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function submitQuizAnswer(sessionId, questionId, selectedIndex) {
  const res = await fetch(`/api/v1/quiz/sessions/${sessionId}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question_id: questionId, selected_index: selectedIndex }),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function finishQuizSession(sessionId) {
  const res = await fetch(`/api/v1/quiz/sessions/${sessionId}/finish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function loadDueInfo(documentIds) {
  const res = await fetch('/api/v1/srs/due' + documentQuery(documentIds));
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function loadDueByDocument() {
  const res = await fetch('/api/v1/srs/due/by-document');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Quiz flow ─────────────────────────────────────────────────────────────
async function startQuiz() {
  // Creating a session is a POST: a second click before it resolves would
  // start a second session and orphan the first.
  if (btnStart.disabled) return;
  const label = btnStart.textContent;
  btnStart.disabled = true;
  btnStart.textContent = 'Starting…';
  try {
    if (state.mode === 'srs') {
      await startSrsFlow();
    } else {
      await startRandomFlow();
    }
  } finally {
    btnStart.disabled = false;
    btnStart.textContent = label;
  }
}

async function startRandomFlow() {
  let n = parseInt(inputN.value, 10);
  if (!n || n < 1) n = 1;
  n = Math.min(n, 50);

  const difficulty = inputDiff.value.trim();
  const documentIds = selectedDocumentIds();
  const tag = inputTag.value.trim();

  state.totalRequested = n;
  state.questions = [];
  state.current = 0;
  state.score = 0;
  state.answered = false;
  state.results = [];
  state.srsSessionId = null;
  state.srsFinishData = null;
  state.quizSessionId = null;

  showScreen('loading');

  const isWeak = state.mode === 'weak';
  try {
    const data = await createQuizSession(
      n,
      isWeak ? null : difficulty,
      documentIds,
      isWeak ? null : tag,
      isWeak,
    );
    if (!data.questions || data.questions.length === 0) {
      if (isWeak) {
        showError(
          'No weak-topic questions yet',
          'Answer some questions first to build a history, then come back to drill your weak spots.'
        );
      } else {
        const context = documentIds.length === 1
          ? [' in ', el('strong', selectedDocuments()[0].dataset.title)]
          : documentIds.length > 1
            ? [' across ', el('strong', `${documentIds.length} selected documents`)]
            : [];
        const diffContext = difficulty
          ? [' for difficulty ', el('strong', difficulty)]
          : [];
        showError(
          'No questions found',
          'No questions are available', ...context, ...diffContext,
          '. Ingest some articles first:', el('br'), el('br'),
          el('code', 'uv run python scripts/ingest.py --source content/<article>.md --verbose'),
        );
      }
      return;
    }
    state.quizSessionId = data.session_id;
    state.questions = data.questions;

    if (data.questions.length < n) {
      shortfallNotice.textContent =
        `Only ${data.questions.length} of ${n} requested questions available with these filters.`;
      shortfallNotice.classList.add('visible');
    } else {
      shortfallNotice.classList.remove('visible');
    }

    renderQuestion();
    showScreen('question');
  } catch (err) {
    showError('Failed to load questions', `Could not reach the API: ${err.message}`);
  }
}

async function startSrsFlow() {
  let n = parseInt(inputSrsN.value, 10);
  if (!n || n < 1) n = 1;
  n = Math.min(n, 100);

  const documentIds = selectedDocumentIds();

  state.totalRequested = n;
  state.questions = [];
  state.current = 0;
  state.score = 0;
  state.answered = false;
  state.results = [];
  state.srsSessionId = null;
  state.srsFinishData = null;
  state.quizSessionId = null;

  showScreen('loading');

  try {
    const data = await startSrsSession(n, documentIds);

    if (!data.questions || data.questions.length === 0) {
      showError(
        'No cards due',
        `No cards are due for review right now. Come back later or ingest more articles.`
      );
      return;
    }

    state.srsSessionId = data.session_id;
    state.questions = data.questions;
    shortfallNotice.classList.remove('visible');

    renderQuestion();
    showScreen('question');
  } catch (err) {
    showError('Failed to start SRS session', `Could not reach the API: ${err.message}`);
  }
}

function renderQuestion() {
  const q = state.questions[state.current];
  const total = state.questions.length;
  const idx = state.current;

  state.answered = false;
  state.keyboardFocus = null;

  // Header
  progressLbl.textContent = `Question ${idx + 1} of ${total}`;
  scoreLbl.textContent = `Score: ${state.score}`;
  progressFill.style.width = `${(idx / total) * 100}%`;

  // Difficulty badge
  diffBadge.textContent = q.difficulty || 'unknown';
  diffBadge.className = 'difficulty-badge ' + difficultyClass(q.difficulty);

  // Question
  questionText.textContent = q.question;

  // Options
  optionsCont.innerHTML = '';
  q.options.forEach((opt, i) => {
    const btn = document.createElement('button');
    btn.className = 'option-btn';
    btn.textContent = `${LABELS[i]}. ${opt}`;
    btn.addEventListener('click', () => handleAnswer(i, btn));
    optionsCont.appendChild(btn);
  });

  // Reset explanation + next + srs info
  answerError.classList.remove('visible');
  explanation.textContent = '';
  explanation.classList.remove('visible');
  srsNextInfo.classList.remove('visible');
  btnNext.classList.remove('visible');
}

async function handleAnswer(selectedIndex, clickedBtn) {
  if (state.answered) return;
  state.answered = true;

  const allBtns = optionsCont.querySelectorAll('.option-btn');
  allBtns.forEach(b => { b.disabled = true; });
  clearKeyboardFocus();
  answerError.classList.remove('visible');

  const q = state.questions[state.current];

  try {
    let result;

    if (state.mode === 'srs' && state.srsSessionId) {
      result = await submitSrsReview(state.srsSessionId, q.id, selectedIndex);
    } else if (state.quizSessionId) {
      result = await submitQuizAnswer(state.quizSessionId, q.id, selectedIndex);
    } else {
      result = await submitAnswer(q.id, selectedIndex);
    }

    // Colour feedback
    allBtns[result.correct_index].classList.add('correct');
    if (!result.correct) {
      clickedBtn.classList.add('wrong');
    }

    if (result.correct) state.score++;

    state.results.push({
      question:      q,
      selectedIndex: selectedIndex,
      correct:       result.correct,
      correctIndex:  result.correct_index,
      explanation:   result.explanation,
    });

    // Explanation — build with a text node so LLM content can't inject HTML
    explanation.textContent = '';
    const explLabel = document.createElement('strong');
    explLabel.textContent = 'Explanation:';
    explanation.append(explLabel, ' ' + result.explanation);
    explanation.classList.add('visible');

    // SRS next-review info
    if (state.mode === 'srs' && result.interval_days !== undefined) {
      srsIntervalText.textContent = formatInterval(result.interval_days);
      srsNextInfo.classList.add('visible');
    }

    // Next / Finish button
    btnNext.textContent = state.current + 1 < state.questions.length ? 'Next \u2192' : 'See Results';
    btnNext.classList.add('visible');
  } catch (err) {
    // Stay on the question: swapping to the error screen would strand the
    // user at setup on "Try Again" and lose the rest of the quiz.
    state.answered = false;
    allBtns.forEach(b => { b.disabled = false; });
    answerError.textContent = `Could not submit that answer: ${err.message}. Pick an option to try again.`;
    answerError.classList.add('visible');
  }
}

function nextQuestion() {
  state.current++;
  if (state.current < state.questions.length) {
    renderQuestion();
  } else {
    showEnd();
  }
}

async function showEnd(exited = false) {
  const answered = state.results.length;
  const total = exited ? answered : state.questions.length;
  const pct = total > 0 ? Math.round((state.score / total) * 100) : 0;

  progressFill.style.width = '100%';

  if (total === 0) {
    endPct.textContent = '—';
    endFraction.textContent = 'No questions answered';
    endMsg.textContent = '';
  } else {
    endPct.textContent = `${pct}%`;
    endFraction.textContent = `${state.score} / ${answered} correct`;
    endMsg.textContent = exited
      ? `Exited after ${answered} of ${state.questions.length} questions`
      : scoreMessage(pct);
  }

  const missedCount = state.results.filter(r => !r.correct).length;
  if (missedCount > 0 && state.mode === 'random') {
    btnRetryMissed.textContent = `Retry missed (${missedCount})`;
    btnRetryMissed.style.display = 'block';
  } else {
    btnRetryMissed.style.display = 'none';
  }

  btnPlayAgain.textContent = state.mode === 'srs' ? 'New SRS Session' : 'Play Again';

  // Only SRS ends with a summary worth waiting for; a random session is
  // finished silently rather than flashing a placeholder at the user.
  const expectsSummary = state.mode === 'srs' && state.srsSessionId;
  if (expectsSummary) {
    srsEndInfo.textContent = 'Finishing session\u2026';
    srsEndInfo.classList.add('visible');
  } else {
    srsEndInfo.classList.remove('visible');
  }

  showScreen('end');

  // Finish the session asynchronously after the screen is shown
  if (expectsSummary) {
    try {
      const data = await finishSrsSession(state.srsSessionId);
      state.srsFinishData = data;
      const correctSpan = el('span', `${data.n_correct} correct`);
      correctSpan.className = 'srs-correct';
      const wrongSpan = el('span', `${data.n_wrong} wrong`);
      wrongSpan.className = 'srs-wrong';
      srsEndInfo.replaceChildren('Session: ', correctSpan, ' · ', wrongSpan);
    } catch (_) {
      srsEndInfo.textContent = 'Session complete.';
    }
  } else if (state.quizSessionId) {
    try {
      await finishQuizSession(state.quizSessionId);
    } catch (_) {
      // Nothing to show either way — the results are already on screen.
    }
  }
}

function replayMissed() {
  const missed = state.results.filter(r => !r.correct).map(r => r.question);
  state.questions = missed;
  state.current = 0;
  state.score = 0;
  state.answered = false;
  state.results = [];
  state.keyboardFocus = null;
  // The session was finished on the end screen; retried answers must not be
  // recorded against it, so fall back to the standalone /answer endpoint.
  state.quizSessionId = null;
  state.srsSessionId = null;
  shortfallNotice.classList.remove('visible');
  renderQuestion();
  showScreen('question');
}

function showReview() {
  reviewList.innerHTML = '';

  state.results.forEach((r, i) => {
    const card = document.createElement('div');
    card.className = 'card';

    const header = document.createElement('div');
    header.className = 'review-q-header';

    const qNum = document.createElement('span');
    qNum.className = 'review-q-num';
    qNum.textContent = `Question ${i + 1} of ${state.results.length}`;

    const badge = document.createElement('span');
    badge.className = `review-result-badge ${r.correct ? 'correct' : 'wrong'}`;
    badge.textContent = r.correct ? '✓ Correct' : '✗ Incorrect';

    header.appendChild(qNum);
    header.appendChild(badge);
    card.appendChild(header);

    const diff = document.createElement('span');
    diff.className = 'difficulty-badge ' + difficultyClass(r.question.difficulty);
    diff.textContent = r.question.difficulty || 'unknown';
    card.appendChild(diff);

    const qText = document.createElement('p');
    qText.className = 'review-q-text';
    qText.textContent = r.question.question;
    card.appendChild(qText);

    const optsDiv = document.createElement('div');
    optsDiv.className = 'review-options';
    r.question.options.forEach((opt, oi) => {
      const optDiv = document.createElement('div');
      optDiv.className = 'review-option';
      const isCorrect  = oi === r.correctIndex;
      const isSelected = oi === r.selectedIndex;
      if (isCorrect)       optDiv.classList.add('correct');
      else if (isSelected) optDiv.classList.add('wrong');
      let text = `${LABELS[oi]}. ${opt}`;
      if (isSelected && !isCorrect) text += '  \u2190 your answer';
      optDiv.textContent = text;
      optsDiv.appendChild(optDiv);
    });
    card.appendChild(optsDiv);

    const expl = document.createElement('div');
    expl.className = 'review-expl';
    const explLabel = document.createElement('strong');
    explLabel.textContent = 'Explanation:';
    expl.append(explLabel, ' ' + r.explanation);
    card.appendChild(expl);

    reviewList.appendChild(card);
  });

  showScreen('review');
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// ── Stats screen ──────────────────────────────────────────────────────────
async function showStats() {
  // Reset stats display
  statsDue.textContent = '—';
  statsNew.textContent = '—';
  statsTotal.textContent = '—';
  docTableBody.innerHTML = '';
  statsEmpty.style.display = 'none';
  showScreen('stats');
  window.scrollTo({ top: 0, behavior: 'instant' });

  try {
    // Overall counts
    const overall = await loadDueInfo([]);
    statsDue.textContent = overall.due_count;
    statsNew.textContent = overall.new_count;
    statsTotal.textContent = overall.total_actionable;

    // Per-document counts — one bulk call, not one per document
    const [docs, byDoc] = await Promise.all([fetchDocuments(), loadDueByDocument()]);

    if (docs.length === 0) {
      statsEmpty.style.display = 'block';
      return;
    }

    const counts = new Map(byDoc.map(row => [row.document_id, row]));
    const perDoc = docs.map(doc => {
      const row = counts.get(doc.id);
      return { doc, due: row?.due_count ?? 0, new: row?.new_count ?? 0 };
    });

    // Sort by (due + new) descending
    perDoc.sort((a, b) => (b.due + b.new) - (a.due + a.new));

    perDoc.forEach(({ doc, due, new: newC }) => {
      const tr = document.createElement('tr');

      const tdTitle = document.createElement('td');
      tdTitle.textContent = doc.title;
      tr.appendChild(tdTitle);

      const tdDue = document.createElement('td');
      tdDue.textContent = due;
      tdDue.className = due > 0 ? 'td-due' : 'td-none';
      tr.appendChild(tdDue);

      const tdNew = document.createElement('td');
      tdNew.textContent = newC;
      tdNew.className = newC > 0 ? 'td-new' : 'td-none';
      tr.appendChild(tdNew);

      const tdTotal = document.createElement('td');
      tdTotal.textContent = doc.question_count;
      tdTotal.className = 'td-total';
      tr.appendChild(tdTotal);

      docTableBody.appendChild(tr);
    });
  } catch (err) {
    statsDue.textContent = '!';
    statsNew.textContent = '!';
    statsTotal.textContent = '!';
  }
}

// ── Event listeners ───────────────────────────────────────────────────────
document.addEventListener('keydown', handleKeyDown);

btnModeRandom.addEventListener('click', () => setMode('random'));
btnModeSrs.addEventListener('click', () => setMode('srs'));
btnModeWeak.addEventListener('click', () => setMode('weak'));

// Refresh mode-specific counts when document selection changes
inputDoc.addEventListener('change', () => {
  if (state.mode === 'srs') refreshDueInfo();
  if (state.mode === 'weak') refreshWeakCount();
});

btnStart.addEventListener('click', startQuiz);
btnNext.addEventListener('click', nextQuestion);
btnExit.addEventListener('click', () => {
  if (confirm('End the quiz and see your results so far?')) showEnd(true);
});
btnPlayAgain.addEventListener('click', () => {
  if (state.mode === 'srs') {
    showScreen('setup');
  } else {
    startQuiz();
  }
});
btnReview.addEventListener('click', () => showScreen('setup'));
btnShowReview.addEventListener('click', showReview);
btnRetryMissed.addEventListener('click', replayMissed);
btnBackEnd.addEventListener('click', () => { showScreen('end'); window.scrollTo({ top: 0, behavior: 'instant' }); });
btnRetry.addEventListener('click', () => showScreen('setup'));

document.getElementById('link-stats').addEventListener('click', e => {
  e.preventDefault();
  showStats();
});

btnStatsBack.addEventListener('click', () => showScreen('setup'));
btnStatsStartSrs.addEventListener('click', () => {
  setMode('srs');
  showScreen('setup');
});

// Allow Enter key in the setup inputs to start the quiz
[inputDoc, inputN, inputDiff, inputSrsN].forEach(field => {
  field.addEventListener('keydown', e => {
    if (e.key === 'Enter') startQuiz();
  });
});

// Populate document and tag dropdowns on load
loadDocuments();
loadTags();
