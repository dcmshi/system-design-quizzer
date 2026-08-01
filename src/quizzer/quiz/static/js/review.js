'use strict';

const PAGE_SIZE = 20;
const LABELS = ['A', 'B', 'C', 'D'];

let page        = 0;
let total       = 0;
let selectedIds = new Set();
let nearDupeMap = new Map(); // question id → [{id, question, similarity}]

const filterStatus  = document.getElementById('filter-status');
const filterDoc     = document.getElementById('filter-doc');
const filterDiff    = document.getElementById('filter-diff');
const filterModel   = document.getElementById('filter-model');
const filterPrompt  = document.getElementById('filter-prompt');
const filterSearch  = document.getElementById('filter-search');
const summaryEl     = document.getElementById('summary');
const listEl        = document.getElementById('question-list');
const paginationEl  = document.getElementById('pagination');
const selectAllCb    = document.getElementById('select-all');
const bulkApproveBtn = document.getElementById('bulk-approve-btn');
const bulkRejectBtn  = document.getElementById('bulk-reject-btn');
const bulkDeleteBtn  = document.getElementById('bulk-delete-btn');
const reingestBtn    = document.getElementById('reingest-btn');
const toastEl        = document.getElementById('toast');

let toastTimer = null;
function showToast(msg, type = 'success') {
  if (toastTimer) clearTimeout(toastTimer);
  toastEl.textContent = msg;
  toastEl.className = `toast show ${type}`;
  toastTimer = setTimeout(() => { toastEl.className = 'toast'; }, 5000);
}

// ── Bulk bar ──────────────────────────────────────────────────────────────

function updateBulkBar() {
  const n = selectedIds.size;
  bulkApproveBtn.textContent = `Approve selected (${n})`;
  bulkApproveBtn.disabled = n === 0;
  bulkRejectBtn.textContent = `Reject selected (${n})`;
  bulkRejectBtn.disabled = n === 0;
  bulkDeleteBtn.textContent = `Delete selected (${n})`;
  bulkDeleteBtn.disabled = n === 0;
  const checkboxes = [...listEl.querySelectorAll('.card-checkbox')];
  const allChecked = checkboxes.length > 0 && checkboxes.every(cb => cb.checked);
  selectAllCb.indeterminate = !allChecked && n > 0;
  selectAllCb.checked = allChecked;
}

// ── Init ──────────────────────────────────────────────────────────────────

async function init() {
  await Promise.all([loadDocuments(), loadFilterOptions(), loadNearDupes()]);
  // Pre-select document from URL param (e.g., links from /sources/)
  const urlDocId = new URLSearchParams(window.location.search).get('document_id');
  if (urlDocId) {
    filterDoc.value = urlDocId;
    reingestBtn.disabled = !filterDoc.value;
  }
  await loadPage();
}

// ── Near-duplicate detection ───────────────────────────────────────────────

async function loadNearDupes() {
  try {
    const res = await fetch('/api/v1/questions/near-duplicates');
    if (!res.ok) return;
    const pairs = await res.json();
    nearDupeMap = new Map();
    pairs.forEach(p => {
      if (!nearDupeMap.has(p.id_a)) nearDupeMap.set(p.id_a, []);
      nearDupeMap.get(p.id_a).push({ id: p.id_b, question: p.question_b, similarity: p.similarity });
      if (!nearDupeMap.has(p.id_b)) nearDupeMap.set(p.id_b, []);
      nearDupeMap.get(p.id_b).push({ id: p.id_a, question: p.question_a, similarity: p.similarity });
    });
  } catch (_) {}
}

/** Forget a question that was deleted or rejected, and any pairing with it.
 *  Cheaper and less racy than refetching every pair in the bank. */
function forgetNearDupes(questionId) {
  nearDupeMap.delete(questionId);
  nearDupeMap.forEach((dupes, id) => {
    const remaining = dupes.filter(d => d.id !== questionId);
    if (remaining.length) nearDupeMap.set(id, remaining);
    else                  nearDupeMap.delete(id);
  });
}

function buildNearDupePanel(dupes, questionId) {
  const panel = document.createElement('div');
  panel.className = 'near-dupe-panel';
  panel.dataset.nearDupePanel = '';
  panel.id = `near-dupes-${questionId}`;
  dupes.forEach(d => {
    const entry = document.createElement('div');
    entry.className = 'near-dupe-entry';
    const preview = d.question.length > 140 ? d.question.slice(0, 140) + '\u2026' : d.question;
    const simSpan = document.createElement('span');
    simSpan.className = 'near-dupe-sim';
    simSpan.textContent = `${Math.round(d.similarity * 100)}% similar \u2014 `;
    const textSpan = document.createElement('span');
    textSpan.className = 'near-dupe-text';
    textSpan.textContent = preview;
    entry.append(simSpan, textSpan);
    panel.appendChild(entry);
  });
  return panel;
}

/** Add the "N similar" toggle and its panel to a card view, if it has dupes. */
function addNearDupeToggle(view, badges, questionId, dupes) {
  if (dupes.length === 0) return;

  const panel = buildNearDupePanel(dupes, questionId);
  const badge = document.createElement('button');
  badge.type = 'button';
  badge.className = 'badge badge-near-dupe';
  badge.dataset.nearDupeBadge = '';
  badge.title = 'Show similar questions';
  badge.textContent = `\u26a0 ${dupes.length} similar`;
  badge.setAttribute('aria-expanded', 'false');
  badge.setAttribute('aria-controls', panel.id);
  badge.addEventListener('click', () => {
    const open = panel.classList.toggle('open');
    badge.setAttribute('aria-expanded', String(open));
  });

  badges.append(badge);
  view.append(panel);
}

function applyNearDupeBadges() {
  listEl.querySelectorAll('.question-card').forEach(card => {
    const view = card.querySelector('.card-view');
    const badges = view.querySelector('.badges');

    const oldBadge = badges.querySelector('[data-near-dupe-badge]');
    if (oldBadge) oldBadge.remove();
    const oldPanel = view.querySelector('[data-near-dupe-panel]');
    if (oldPanel) oldPanel.remove();

    addNearDupeToggle(view, badges, card.dataset.id, nearDupeMap.get(card.dataset.id) || []);
  });
}

// ── Filter options (models + prompt versions) ──────────────────────────────

async function loadFilterOptions() {
  try {
    const [models, promptVersions] = await Promise.all([
      fetch('/api/v1/questions/models').then(r => r.ok ? r.json() : []),
      fetch('/api/v1/questions/prompt-versions').then(r => r.ok ? r.json() : []),
    ]);
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      filterModel.appendChild(opt);
    });
    promptVersions.forEach(pv => {
      const opt = document.createElement('option');
      opt.value = pv; opt.textContent = pv;
      filterPrompt.appendChild(opt);
    });
  } catch (_) {}
}

// ── Documents ─────────────────────────────────────────────────────────────

async function loadDocuments() {
  try {
    const res = await fetch('/api/v1/documents');
    if (!res.ok) return;
    const docs = await res.json();
    docs.forEach(doc => {
      const opt = document.createElement('option');
      opt.value = doc.id;
      opt.textContent = doc.title;
      filterDoc.appendChild(opt);
    });
  } catch (_) {}
}

// ── Page load ─────────────────────────────────────────────────────────────

async function loadPage() {
  selectedIds.clear();
  updateBulkBar();
  listEl.innerHTML = '<div class="state-msg">Loading&hellip;</div>';
  paginationEl.innerHTML = '';
  summaryEl.textContent = '';

  const status    = filterStatus.value;
  const docId     = filterDoc.value;
  const diff      = filterDiff.value;
  const model     = filterModel.value;
  const promptVer = filterPrompt.value;
  const q         = filterSearch.value.trim();

  let url = `/api/v1/questions?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`;
  if (status)    url += `&status=${encodeURIComponent(status)}`;
  if (docId)     url += `&document_id=${encodeURIComponent(docId)}`;
  if (diff)      url += `&difficulty=${encodeURIComponent(diff)}`;
  if (model)     url += `&model=${encodeURIComponent(model)}`;
  if (promptVer) url += `&prompt_version=${encodeURIComponent(promptVer)}`;
  if (q)         url += `&q=${encodeURIComponent(q)}`;

  let data;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (err) {
    const msg = document.createElement('div');
    msg.className = 'state-msg';
    msg.textContent = `Failed to load questions: ${err.message}`;
    listEl.replaceChildren(msg);
    return;
  }

  total = data.total;

  if (data.items.length === 0) {
    listEl.innerHTML = '<div class="state-msg">No questions match the current filters.</div>';
    summaryEl.textContent = '0 questions';
    renderPagination();
    return;
  }

  listEl.innerHTML = '';
  data.items.forEach(q => listEl.appendChild(buildCard(q)));

  const start = page * PAGE_SIZE + 1;
  const end   = Math.min(start + data.items.length - 1, total);
  summaryEl.textContent =
    `Showing ${start}\u2013${end} of ${total} question${total !== 1 ? 's' : ''}`;

  renderPagination();
}

// ── Card ──────────────────────────────────────────────────────────────────

function buildCard(q) {
  const card = document.createElement('div');
  card.className = 'question-card';
  card.dataset.id = q.id;

  const checkRow = document.createElement('div');
  checkRow.className = 'card-select';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'card-checkbox';
  cb.dataset.id = q.id;
  cb.addEventListener('change', () => {
    if (cb.checked) selectedIds.add(q.id);
    else            selectedIds.delete(q.id);
    updateBulkBar();
  });
  checkRow.appendChild(cb);

  const view = buildCardView(q);
  const form = buildEditForm(q);

  card.append(checkRow, view, form);

  view.querySelector('.btn-approve').addEventListener('click', () => doStatusUpdate(card, q, 'approved'));
  view.querySelector('.btn-edit').addEventListener('click',    () => openEdit(card, form, q));
  view.querySelector('.btn-reject').addEventListener('click',  () => doStatusUpdate(card, q, 'rejected'));
  view.querySelector('.btn-delete').addEventListener('click',  () => doDelete(card, q));
  form.querySelector('.btn-save').addEventListener('click',   () => doSave(card, q));
  form.querySelector('.btn-cancel').addEventListener('click', () => closeEdit(card));

  return card;
}

function buildCardView(q) {
  const view = document.createElement('div');
  view.className = 'card-view';

  // Top: badges + actions
  const top = document.createElement('div');
  top.className = 'card-top';

  const badges = document.createElement('div');
  badges.className = 'badges';

  const diffBadge = document.createElement('span');
  diffBadge.className = `badge badge-${q.difficulty}`;
  diffBadge.textContent = q.difficulty;

  const statusBadge = document.createElement('span');
  statusBadge.className = `badge badge-${q.status}`;
  statusBadge.dataset.statusBadge = '';
  statusBadge.textContent = q.status;

  badges.append(diffBadge, statusBadge);

  const actions = document.createElement('div');
  actions.className = 'card-actions';
  actions.innerHTML =
    '<button class="btn btn-approve">Approve</button>' +
    '<button class="btn btn-edit">Edit</button>' +
    '<button class="btn btn-reject">Reject</button>' +
    '<button class="btn btn-delete">Delete</button>';

  top.append(badges, actions);

  // Question
  const qText = document.createElement('p');
  qText.className = 'card-question';
  qText.dataset.field = 'question';
  qText.textContent = q.question;

  // Options
  const opts = document.createElement('ul');
  opts.className = 'card-options';
  opts.dataset.field = 'options';
  renderOptionsList(opts, q.options, q.correct_index);

  // Explanation
  const expl = document.createElement('div');
  expl.className = 'card-explanation';
  const explLabel = document.createElement('strong');
  explLabel.textContent = 'Explanation: ';
  const explText = document.createElement('span');
  explText.dataset.field = 'explanation';
  explText.textContent = q.explanation;
  expl.append(explLabel, explText);

  const hitRate = document.createElement('div');
  if (q.times_answered > 0) {
    const pct = Math.round(q.hit_rate * 100);
    const cls = pct >= 80 ? 'hit-rate-good' : pct >= 50 ? 'hit-rate-mid' : 'hit-rate-bad';
    hitRate.className = `hit-rate ${cls}`;
    hitRate.textContent = `${pct}% hit rate (${q.times_correct}/${q.times_answered})`;
  } else {
    hitRate.className = 'hit-rate hit-rate-none';
    hitRate.textContent = 'Never attempted';
  }

  const meta = document.createElement('div');
  meta.className = 'card-meta';
  const modelCode = document.createElement('code');
  modelCode.textContent = q.model || '—';
  const promptCode = document.createElement('code');
  promptCode.textContent = q.prompt_version || '—';
  meta.append('Model: ', modelCode, ' Prompt: ', promptCode);

  view.append(top, qText, opts, expl, hitRate, meta);
  addNearDupeToggle(view, badges, q.id, nearDupeMap.get(q.id) || []);

  return view;
}

function renderOptionsList(ul, options, correctIndex) {
  ul.innerHTML = '';
  options.forEach((opt, i) => {
    const li = document.createElement('li');
    if (i === correctIndex) li.classList.add('correct');

    const label = document.createElement('span');
    label.className = 'option-label';
    label.textContent = LABELS[i] + '.';

    const text = document.createElement('span');
    text.textContent = opt;

    li.append(label, text);

    if (i === correctIndex) {
      const mark = document.createElement('span');
      mark.className = 'correct-mark';
      mark.textContent = '\u2713';
      li.appendChild(mark);
    }
    ul.appendChild(li);
  });
}

function buildEditForm(q) {
  const form = document.createElement('div');
  form.className = 'card-edit';

  const optFields = LABELS.map((l, i) =>
    `<div class="option-field"><span class="option-field-label">${l}.</span>` +
    `<input class="form-input" name="option_${i}" type="text"></div>`
  ).join('');

  const correctOpts = LABELS.map((l, i) => `<option value="${i}">${l}</option>`).join('');

  form.innerHTML =
    '<div class="form-group"><label class="form-label">Question</label>' +
    '<textarea class="form-input" name="question" rows="3"></textarea></div>' +
    '<div class="form-group"><label class="form-label">Options</label>' +
    `<div class="options-grid">${optFields}</div></div>` +
    '<div class="form-row">' +
    '<div class="form-group"><label class="form-label">Correct answer</label>' +
    `<select class="form-input" name="correct_index">${correctOpts}</select></div>` +
    '<div class="form-group"><label class="form-label">Difficulty</label>' +
    '<select class="form-input" name="difficulty">' +
    '<option value="easy">Easy</option><option value="medium">Medium</option>' +
    '<option value="hard">Hard</option></select></div></div>' +
    '<div class="form-group"><label class="form-label">Explanation</label>' +
    '<textarea class="form-input" name="explanation" rows="3"></textarea></div>' +
    '<div class="form-actions"><button class="btn btn-save">Save</button>' +
    '<button class="btn btn-cancel">Cancel</button></div>';

  prefillForm(form, q);
  return form;
}

function prefillForm(form, q) {
  form.querySelector('[name=question]').value = q.question;
  q.options.forEach((opt, i) => { form.querySelector(`[name=option_${i}]`).value = opt; });
  form.querySelector('[name=correct_index]').value = String(q.correct_index);
  form.querySelector('[name=difficulty]').value = q.difficulty;
  form.querySelector('[name=explanation]').value = q.explanation;
}

// ── Edit open / close ─────────────────────────────────────────────────────

function openEdit(card, form, q) {
  prefillForm(form, q);
  form.classList.add('open');
}

function closeEdit(card) {
  card.querySelector('.card-edit').classList.remove('open');
}

function setAllBtns(card, disabled) {
  card.querySelectorAll('button').forEach(b => { b.disabled = disabled; });
}

// ── Save ──────────────────────────────────────────────────────────────────

async function doSave(card, q) {
  const form        = card.querySelector('.card-edit');
  const question    = form.querySelector('[name=question]').value.trim();
  const options     = LABELS.map((_, i) => form.querySelector(`[name=option_${i}]`).value.trim());
  const correctIdx  = parseInt(form.querySelector('[name=correct_index]').value, 10);
  const difficulty  = form.querySelector('[name=difficulty]').value;
  const explanation = form.querySelector('[name=explanation]').value.trim();

  if (!question || options.some(o => !o)) {
    alert('Question and all four options are required.');
    return;
  }

  setAllBtns(card, true);
  try {
    const res = await fetch(`/api/v1/questions/${q.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, options, correct_index: correctIdx, explanation, difficulty }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }

    // Update card view in place — no reload needed
    const view = card.querySelector('.card-view');
    view.querySelector('[data-field=question]').textContent = question;
    view.querySelector('[data-field=explanation]').textContent = explanation;
    renderOptionsList(view.querySelector('[data-field=options]'), options, correctIdx);

    const badge = view.querySelector('[data-status-badge]');
    badge.textContent = 'edited';
    badge.className = 'badge badge-edited';

    // Sync local state so re-opening edit form shows updated values
    q.question      = question;
    q.options       = options;
    q.correct_index = correctIdx;
    q.difficulty    = difficulty;
    q.explanation   = explanation;
    q.status        = 'edited';

    closeEdit(card);
  } catch (err) {
    alert(`Save failed: ${err.message}`);
  } finally {
    setAllBtns(card, false);
  }
}

// ── Status update (approve / reject) ─────────────────────────────────────

async function doStatusUpdate(card, q, newStatus) {
  setAllBtns(card, true);
  try {
    const res = await fetch(`/api/v1/questions/${q.id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }

    const currentFilter = filterStatus.value;
    if (currentFilter && currentFilter !== newStatus) {
      // Fade out and remove — no longer matches current filter
      card.style.transition = 'opacity 0.2s';
      card.style.opacity = '0';
      setTimeout(() => {
        card.remove();
        total = Math.max(0, total - 1);
        if (listEl.children.length === 0) {
          listEl.innerHTML = '<div class="state-msg">No questions match the current filters.</div>';
          summaryEl.textContent = '0 questions';
          renderPagination();
        }
      }, 200);
    } else {
      // Update badge in place (filter is "all statuses")
      q.status = newStatus;
      const badge = card.querySelector('[data-status-badge]');
      badge.textContent = newStatus;
      badge.className = `badge badge-${newStatus}`;
      setAllBtns(card, false);
    }
    // Rejected questions are excluded from similarity
    if (newStatus === 'rejected') {
      forgetNearDupes(q.id);
      applyNearDupeBadges();
    }
  } catch (err) {
    alert(`Action failed: ${err.message}`);
    setAllBtns(card, false);
  }
}

// ── Delete ────────────────────────────────────────────────────────────────

async function doDelete(card, q) {
  const preview = q.question.length > 80 ? q.question.slice(0, 80) + '…' : q.question;
  if (!confirm(`Permanently delete this question?\n\n"${preview}"\n\nThis cannot be undone.`)) return;
  setAllBtns(card, true);
  try {
    const res = await fetch(`/api/v1/questions/${q.id}`, { method: 'DELETE' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    selectedIds.delete(q.id);
    updateBulkBar();
    card.style.transition = 'opacity 0.2s';
    card.style.opacity = '0';
    setTimeout(() => {
      card.remove();
      total = Math.max(0, total - 1);
      if (listEl.children.length === 0) {
        listEl.innerHTML = '<div class="state-msg">No questions match the current filters.</div>';
        summaryEl.textContent = '0 questions';
        renderPagination();
      }
    }, 200);
    forgetNearDupes(q.id);
    applyNearDupeBadges();
  } catch (err) {
    alert(`Delete failed: ${err.message}`);
    setAllBtns(card, false);
  }
}

// ── Pagination ────────────────────────────────────────────────────────────

function renderPagination() {
  paginationEl.innerHTML = '';
  if (total <= PAGE_SIZE) return;

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const prev = document.createElement('button');
  prev.className = 'page-btn';
  prev.textContent = '\u2190 Prev';
  prev.disabled = page === 0;
  prev.addEventListener('click', () => { page--; loadPage(); });

  const label = document.createElement('span');
  label.textContent = `Page ${page + 1} of ${totalPages}`;

  const next = document.createElement('button');
  next.className = 'page-btn';
  next.textContent = 'Next \u2192';
  next.disabled = page >= totalPages - 1;
  next.addEventListener('click', () => { page++; loadPage(); });

  paginationEl.append(prev, label, next);
}

// ── Select all ────────────────────────────────────────────────────────────

selectAllCb.addEventListener('change', () => {
  listEl.querySelectorAll('.card-checkbox').forEach(cb => {
    cb.checked = selectAllCb.checked;
    if (selectAllCb.checked) selectedIds.add(cb.dataset.id);
    else                     selectedIds.delete(cb.dataset.id);
  });
  updateBulkBar();
});

// ── Bulk approve ──────────────────────────────────────────────────────────

bulkApproveBtn.addEventListener('click', async () => {
  const ids = [...selectedIds];
  if (!ids.length) return;
  bulkApproveBtn.disabled = true;
  try {
    const res = await fetch('/api/v1/questions/bulk-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, status: 'approved' }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const currentFilter = filterStatus.value;
    if (currentFilter && currentFilter !== 'approved') {
      // Fade out cards that no longer match the filter
      const toFade = [...listEl.querySelectorAll('.question-card')]
        .filter(c => ids.includes(c.dataset.id));
      toFade.forEach(c => { c.style.transition = 'opacity 0.2s'; c.style.opacity = '0'; });
      setTimeout(() => {
        toFade.forEach(c => { c.remove(); total = Math.max(0, total - 1); });
        selectedIds.clear();
        updateBulkBar();
        if (listEl.children.length === 0) {
          listEl.innerHTML = '<div class="state-msg">No questions match the current filters.</div>';
          summaryEl.textContent = '0 questions';
          renderPagination();
        }
      }, 220);
    } else {
      // "All statuses" — update badges in place
      listEl.querySelectorAll('.question-card').forEach(c => {
        if (!ids.includes(c.dataset.id)) return;
        const badge = c.querySelector('[data-status-badge]');
        if (badge) { badge.textContent = 'approved'; badge.className = 'badge badge-approved'; }
      });
      selectedIds.clear();
      updateBulkBar();
    }
  } catch (err) {
    alert(`Bulk approve failed: ${err.message}`);
    bulkApproveBtn.disabled = selectedIds.size === 0;
  }
});

// ── Bulk reject ───────────────────────────────────────────────────────────

bulkRejectBtn.addEventListener('click', async () => {
  const ids = [...selectedIds];
  if (!ids.length) return;
  bulkRejectBtn.disabled = true;
  try {
    const res = await fetch('/api/v1/questions/bulk-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, status: 'rejected' }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const currentFilter = filterStatus.value;
    if (currentFilter && currentFilter !== 'rejected') {
      // fade out and remove cards that no longer match the filter
      const toFade = [...listEl.querySelectorAll('.question-card')]
        .filter(c => ids.includes(c.dataset.id));
      toFade.forEach(c => { c.style.transition = 'opacity 0.2s'; c.style.opacity = '0'; });
      setTimeout(() => {
        toFade.forEach(c => { c.remove(); total = Math.max(0, total - 1); });
        selectedIds.clear();
        updateBulkBar();
        if (listEl.children.length === 0) {
          listEl.innerHTML = '<div class="state-msg">No questions match the current filters.</div>';
          summaryEl.textContent = '0 questions';
          renderPagination();
        }
      }, 220);
    } else {
      // "All statuses" — update badges in place
      listEl.querySelectorAll('.question-card').forEach(c => {
        if (!ids.includes(c.dataset.id)) return;
        const badge = c.querySelector('[data-status-badge]');
        if (badge) { badge.textContent = 'rejected'; badge.className = 'badge badge-rejected'; }
      });
      selectedIds.clear();
      updateBulkBar();
    }
  } catch (err) {
    alert(`Bulk reject failed: ${err.message}`);
    bulkRejectBtn.disabled = selectedIds.size === 0;
  }
});

// ── Bulk delete ───────────────────────────────────────────────────────────

bulkDeleteBtn.addEventListener('click', async () => {
  const ids = [...selectedIds];
  if (!ids.length) return;
  if (!confirm(`Permanently delete ${ids.length} question${ids.length !== 1 ? 's' : ''}? This cannot be undone.`)) return;
  bulkDeleteBtn.disabled = true;
  const errors = [];
  await Promise.all(ids.map(async id => {
    try {
      const res = await fetch(`/api/v1/questions/${id}`, { method: 'DELETE' });
      if (!res.ok) errors.push(id);
    } catch (_) {
      errors.push(id);
    }
  }));
  const deleted = ids.filter(id => !errors.includes(id));
  const toFade = [...listEl.querySelectorAll('.question-card')]
    .filter(c => deleted.includes(c.dataset.id));
  toFade.forEach(c => { c.style.transition = 'opacity 0.2s'; c.style.opacity = '0'; });
  setTimeout(() => {
    toFade.forEach(c => { c.remove(); total = Math.max(0, total - 1); });
    deleted.forEach(id => selectedIds.delete(id));
    updateBulkBar();
    if (listEl.children.length === 0) {
      listEl.innerHTML = '<div class="state-msg">No questions match the current filters.</div>';
      summaryEl.textContent = '0 questions';
      renderPagination();
    }
  }, 220);
  if (errors.length) alert(`${errors.length} deletion${errors.length !== 1 ? 's' : ''} failed.`);
});

// ── Filters ───────────────────────────────────────────────────────────────

filterStatus.addEventListener('change', () => { page = 0; loadPage(); });
filterDoc.addEventListener('change', () => {
  reingestBtn.disabled = !filterDoc.value;
  page = 0;
  loadPage();
});
filterDiff.addEventListener('change',   () => { page = 0; loadPage(); });
filterModel.addEventListener('change',  () => { page = 0; loadPage(); });
filterPrompt.addEventListener('change', () => { page = 0; loadPage(); });

reingestBtn.addEventListener('click', async () => {
  const docId = filterDoc.value;
  if (!docId) return;
  reingestBtn.disabled = true;
  reingestBtn.textContent = '\u21BA Starting\u2026';
  try {
    const res = await fetch(`/api/v1/documents/${encodeURIComponent(docId)}/reingest`, { method: 'POST' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    showToast(`Re-ingestion started for \u201C${data.title}\u201D. New questions will appear shortly.`, 'success');
  } catch (err) {
    showToast(`Re-ingest failed: ${err.message}`, 'error');
  } finally {
    reingestBtn.disabled = false;
    reingestBtn.textContent = '\u21BA Re-ingest';
  }
});

let searchDebounce = null;
filterSearch.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => { page = 0; loadPage(); }, 300);
});

// ── Boot ──────────────────────────────────────────────────────────────────

init();
