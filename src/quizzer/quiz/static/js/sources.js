let allDocs = [];
let sortCol = 'title';
let sortDir = 1; // 1 = asc, -1 = desc

const tbody = document.getElementById('doc-body');
const summary = document.getElementById('summary');
const searchInput = document.getElementById('search');
const filterSource = document.getElementById('filter-source');
const filterTag = document.getElementById('filter-tag');
const sortSelect = document.getElementById('sort-by');
const statsBar = document.getElementById('stats-bar');

async function load() {
  try {
    allDocs = await api('/api/v1/documents');
    populateFilters();
    renderStats();
    render();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="state-msg">Failed to load documents: ${e.message}</td></tr>`;
  }
}

function populateFilters() {
  const sources = [...new Set(allDocs.map(d => d.source).filter(Boolean))].sort();
  sources.forEach(s => {
    const o = document.createElement('option');
    o.value = s; o.textContent = s;
    filterSource.appendChild(o);
  });

  const tags = [...new Set(allDocs.flatMap(d => d.tags || []))].sort();
  tags.forEach(t => {
    const o = document.createElement('option');
    o.value = t; o.textContent = t;
    filterTag.appendChild(o);
  });
}

function renderStats() {
  const totalDocs = allDocs.length;
  const totalChunks = allDocs.reduce((s, d) => s + (d.chunk_count || 0), 0);
  const totalWords = allDocs.reduce((s, d) => s + (d.word_count || 0), 0);
  const totalQs = allDocs.reduce((s, d) => s + (d.question_count || 0), 0);

  statsBar.classList.remove('hidden');
  statsBar.innerHTML = [
    ['Documents', totalDocs.toLocaleString()],
    ['Chunks', totalChunks.toLocaleString()],
    ['Total words', fmtWords(totalWords)],
    ['Questions', totalQs.toLocaleString()],
  ].map(([label, value]) => `
    <div class="stat-item">
      <span class="stat-value">${value}</span>
      <span class="stat-label">${label}</span>
    </div>
  `).join('');
}

function fmtWords(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return n.toLocaleString();
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function filtered() {
  const q = searchInput.value.trim().toLowerCase();
  const src = filterSource.value;
  const tag = filterTag.value;
  return allDocs.filter(d => {
    if (q && !d.title.toLowerCase().includes(q) && !d.source_path.toLowerCase().includes(q)) return false;
    if (src && d.source !== src) return false;
    if (tag && !(d.tags || []).includes(tag)) return false;
    return true;
  });
}

function sorted(docs) {
  return [...docs].sort((a, b) => {
    let av = a[sortCol] ?? '', bv = b[sortCol] ?? '';
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    if (av < bv) return -sortDir;
    if (av > bv) return sortDir;
    return 0;
  });
}

function updateSortHeaders() {
  document.querySelectorAll('thead th[data-col]').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    const icon = th.querySelector('.sort-icon');
    if (th.dataset.col === sortCol) {
      th.classList.add(sortDir === 1 ? 'sort-asc' : 'sort-desc');
      if (icon) icon.textContent = sortDir === 1 ? '↑' : '↓';
    } else {
      if (icon) icon.textContent = '↕';
    }
  });
}

function render() {
  const docs = sorted(filtered());
  updateSortHeaders();

  summary.textContent = docs.length === allDocs.length
    ? `${allDocs.length} article${allDocs.length !== 1 ? 's' : ''}`
    : `${docs.length} of ${allDocs.length} articles`;

  if (docs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="state-msg">No articles match the current filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = docs.map(d => {
    const tags = (d.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('');
    const qClass = d.question_count === 0 ? 'q-zero' : 'q-count';
    const reviewUrl = `/review/?document_id=${encodeURIComponent(d.id)}`;
    return `
      <tr>
        <td class="doc-title-cell">
          <a class="doc-title" href="${reviewUrl}">${esc(d.title)}</a>
          <div class="doc-path">${esc(d.source_path)}</div>
        </td>
        <td><span class="source-badge">${esc(d.source || '—')}</span></td>
        <td class="tags-cell"><div class="tag-list">${tags || '<span style="color:var(--text-muted);font-size:0.8rem">—</span>'}</div></td>
        <td class="num-cell"><strong>${d.chunk_count ?? 0}</strong></td>
        <td class="num-cell"><strong>${fmtWords(d.word_count ?? 0)}</strong></td>
        <td class="num-cell"><strong class="${qClass}">${d.question_count ?? 0}</strong></td>
        <td class="date-cell">${fmtDate(d.created_at)}</td>
        <td class="action-cell"><a class="btn-review" href="${reviewUrl}">Review →</a></td>
      </tr>
    `;
  }).join('');
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Events
searchInput.addEventListener('input', render);
filterSource.addEventListener('change', render);
filterTag.addEventListener('change', render);
sortSelect.addEventListener('change', () => {
  sortCol = sortSelect.value;
  sortDir = ['question_count', 'word_count', 'chunk_count'].includes(sortCol) ? -1 : 1;
  render();
});

document.querySelectorAll('thead th[data-col]').forEach(th => {
  th.addEventListener('click', () => {
    if (sortCol === th.dataset.col) {
      sortDir = -sortDir;
    } else {
      sortCol = th.dataset.col;
      sortDir = ['question_count', 'word_count', 'chunk_count'].includes(sortCol) ? -1 : 1;
    }
    sortSelect.value = sortCol;
    render();
  });
});

load();
