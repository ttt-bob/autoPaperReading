
const DATA = JSON.parse(document.getElementById('taxonomy-data').textContent);
const $ = (s) => document.querySelector(s);
const el = (tag, cls, html='') => { const n=document.createElement(tag); if(cls) n.className=cls; n.innerHTML=html; return n; };
const stageMap = Object.fromEntries(DATA.stages.map(s => [s.code, s]));
const paperIndex = new Map(DATA.papers.map(p => [p.id, p]));
const detailCache = new Map();
let modalRequestId = 0;
$('#stat-count').textContent = DATA.count;
$('#stat-range').textContent = `${DATA.oldest.slice(0,4)}-${DATA.newest.slice(0,4)}`;

function escHtml(value='') {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function normalizeTitle(value='') {
  return String(value).toLowerCase().replace(/\s+/g, ' ').trim();
}

function paperCard(p) {
  const tags = [...(p.focus||[]).slice(0,4).map(t=>`<span class="tag">${escHtml(t)}</span>`), `<span class="tag stage">${escHtml(p.stageTitle)}</span>`].join('');
  const text = [p.id,p.title,p.date,p.stageTitle,p.modelGroupTitle,(p.focus||[]).join(' ')].join(' ').toLowerCase();
  return `<article class="card paper-card" role="button" tabindex="0" data-paper-id="${escHtml(p.id)}" data-text="${escHtml(text)}">
    <div class="date">${escHtml(p.date || 'no date')}</div>
    <h4>${escHtml(p.title)}</h4>
    <p>${escHtml(p.intro || '点击查看论文总结')}</p>
    <div class="meta">${tags}</div>
  </article>`;
}

function scrollToPaperSection(view, code, behavior='smooth') {
  const target = document.getElementById(`paper-${view}-${code}`);
  if (!target) return;
  target.open = true;
  target.scrollIntoView({ behavior, block: 'start' });
}

function jumpToGroup(view, code, behavior='smooth') {
  activeView = view;
  activeFilter = code;
  $('#search').value = '';
  renderBrowserFilters();
  renderPaperSections();
  updateFilterButtons();
  filterCards();
  requestAnimationFrame(() => scrollToPaperSection(view, code, behavior));
}

function keepScrollPosition(callback) {
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;
  callback();
  requestAnimationFrame(() => window.scrollTo(scrollX, scrollY));
}

function applyBrowserFilter(code) {
  keepScrollPosition(() => {
    activeFilter = code;
    updateFilterButtons();
    filterCards();
  });
}

function renderPipeline() {
  const box = $('#pipeline'); box.innerHTML='';
  DATA.stages.forEach((s,i) => {
    const n = el('a','step'); n.href = '#paper-sections';
    n.onclick = (event) => { event.preventDefault(); jumpToGroup('stage', s.code); };
    n.innerHTML = `<span class="badge">${s.count}</span><div class="num">STEP ${String(i).padStart(2,'0')}</div><h3>${s.title}</h3><p>${s.question}</p><p class="small">${s.artifact}</p>`;
    box.appendChild(n);
  });
}

function renderBars() {
  const max = Math.max(...DATA.stages.map(s=>s.count));
  $('#stage-bars').innerHTML = DATA.stages.map(s => `<div class="bar-row"><b>${s.title}</b><div class="bar"><i style="width:${Math.max(3, s.count/max*100)}%"></i></div><span>${s.count}</span></div>`).join('');
}

function renderModelGroups() {
  const summary = $('#model-group-summary'); summary.innerHTML='';
  DATA.modelGroups.forEach(g => {
    const card = el('div', 'group-card', `<b>${g.title}</b><p>${g.desc}</p><div class="count">${g.count} papers</div>`);
    card.tabIndex = 0;
    card.role = 'button';
    card.onclick = () => jumpToGroup('model', g.code);
    card.onkeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        jumpToGroup('model', g.code);
      }
    };
    summary.appendChild(card);
  });
}

let activeView = 'stage';
let activeFilter = 'all';

function currentGroups() {
  if (activeView === 'model') {
    return DATA.modelGroups.map(g => ({ code: g.code, title: g.title, count: g.count }));
  }
  return DATA.stages.map(s => ({ code: s.code, title: s.title, count: s.count }));
}

function updateFilterButtons() {
  document.querySelectorAll('#paper-filter button').forEach((b,i)=>{ b.classList.toggle('active', i===0 ? activeFilter==='all' : b.dataset.filter===activeFilter); });
  $('#view-stage').classList.toggle('active', activeView === 'stage');
  $('#view-model').classList.toggle('active', activeView === 'model');
}

function comparePapers(a, b) {
  const relevance = (b.relevance || 0) - (a.relevance || 0);
  if (relevance) return relevance;
  return (b.date || '').localeCompare(a.date || '');
}

function renderBrowserFilters() {
  const root = $('#paper-filter'); root.innerHTML='';
  const all = el('button','active','全部');
  all.onclick=()=>applyBrowserFilter('all');
  root.appendChild(all);
  currentGroups().forEach(g => {
    const b=el('button','',`${g.title} · ${g.count}`);
    b.dataset.filter=g.code;
    b.onclick=()=>applyBrowserFilter(g.code);
    root.appendChild(b);
  });
}

function sectionPapers(code) {
  if (activeView === 'model') {
    return DATA.papers.filter(p=>p.modelGroup===code).sort(comparePapers);
  }
  return DATA.papers.filter(p=>p.stage===code).sort(comparePapers);
}

function renderPaperSections() {
  const root = $('#paper-sections'); root.innerHTML='';
  currentGroups().forEach(g => {
    const papers = sectionPapers(g.code);
    const d=el('details'); d.open=true; d.dataset.filter=g.code; d.id=`paper-${activeView}-${g.code}`;
    const modeLabel = activeView === 'model' ? 'model direction' : 'pipeline layer';
    d.innerHTML = `<summary>${g.title} <span>${papers.length} papers · ${modeLabel} · relevance first · new → old</span></summary><div class="cards">${papers.map(paperCard).join('') || '<div class="empty">No papers</div>'}</div>`;
    root.appendChild(d);
  });
}

function isLocalContext() {
  return location.protocol === 'file:' || ['localhost', '127.0.0.1', '0.0.0.0', ''].includes(location.hostname);
}

function renderSummary(text) {
  if (!text) return '<p>暂无总结</p>';
  return escHtml(text)
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^---$/gm, '<hr>')
    .split(/\n\n+/)
    .map(block => {
      block = block.trim();
      if (!block) return '';
      if (block.startsWith('<h') || block.startsWith('<li') || block.startsWith('<hr')) return block;
      return `<p>${block.replace(/\n/g, '<br>')}</p>`;
    })
    .join('\n');
}

function linkButton(href, label, className='') {
  if (!href) return '';
  return `<a class="modal-link ${className}" href="${escHtml(href)}" target="_blank" rel="noreferrer">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14,2 14,8 20,8"/>
    </svg>
    ${escHtml(label)}
  </a>`;
}

function sourceLinkLabel(href) {
  return /arxiv\.org\/abs\//i.test(String(href || '')) ? 'arXiv 页面' : '论文页面';
}

async function openPaperModal(paperId, updateLocation=true) {
  const base = paperIndex.get(paperId);
  if (!base) return;
  const requestId = ++modalRequestId;
  if (updateLocation && location.hash !== `#paper=${encodeURIComponent(paperId)}`) {
    history.replaceState(null, '', `#paper=${encodeURIComponent(paperId)}`);
  }
  const p = base;
  const tagItems = [
    ...(p.focus || []),
    ...(p.stageTags || []),
    ...(p.tagsText || '').split(','),
    p.stageTitle,
    p.modelGroupTitle,
  ].map(t => String(t || '').trim()).filter(Boolean);
  const uniqueTags = [...new Set(tagItems)];

  $('#paper-modal-kicker').textContent = p.stageTitle || 'video-search paper';
  $('#paper-modal-title').textContent = p.title || 'Untitled';
  $('#paper-modal-meta').innerHTML = [
    p.authors ? `Authors: ${escHtml(p.authors)}` : '',
    p.date ? `Date: ${escHtml(p.date)}` : '',
    p.modelGroupTitle ? `Direction: ${escHtml(p.modelGroupTitle)}` : '',
    p.affiliations ? `Affiliations: ${escHtml(p.affiliations)}` : '',
  ].filter(Boolean).map(x => `<span>${x}</span>`).join('');
  $('#paper-modal-tags').innerHTML = uniqueTags.map(t => `<span class="tag">${escHtml(t)}</span>`).join('');

  const sourceUrl = p.url || p.entry_url || p.pdf_url || p.pdf;
  const links = [
    isLocalContext() ? linkButton(p.local_pdf_path, '本地 PDF', 'local-pdf') : '',
    linkButton(sourceUrl, sourceLinkLabel(sourceUrl)),
    linkButton(p.code_url, '代码'),
  ].join('');
  $('#paper-modal-links').innerHTML = links || '<span class="small">暂无可用链接</span>';
  $('#paper-modal-summary').innerHTML = '<p>正在加载论文总结…</p>';
  $('#paper-modal-overlay').classList.add('active');
  document.body.style.overflow = 'hidden';

  try {
    const detail = await loadPaperDetail(p);
    if (requestId !== modalRequestId) return;
    $('#paper-modal-summary').innerHTML = renderSummary(detail.summary || '暂无总结');
  } catch (err) {
    console.warn('Could not load paper detail', err);
    if (requestId !== modalRequestId) return;
    // Keep the modal useful during a CDN/deployment race. The inline summary
    // is intentionally short, while the normal path still loads the full JSON.
    $('#paper-modal-summary').innerHTML = renderSummary(
      p.summary || '论文总结暂时无法加载，请稍后重试。',
    );
  }
}

async function loadPaperDetail(paper) {
  if (!paper.detailPath) return paper;
  if (!detailCache.has(paper.id)) {
    const request = fetch(new URL(paper.detailPath, document.baseURI), {
      cache: 'force-cache',
    })
      .then(res => {
        if (!res.ok) throw new Error(`detail request failed: ${res.status}`);
        return res.json();
      })
      .catch(error => {
        detailCache.delete(paper.id);
        throw error;
      });
    detailCache.set(paper.id, request);
  }
  return detailCache.get(paper.id);
}

function closePaperModal(e) {
  if (e && e.target !== e.currentTarget) return;
  modalRequestId++;
  $('#paper-modal-overlay').classList.remove('active');
  document.body.style.overflow = '';
  if (location.hash.startsWith('#paper=')) {
    history.replaceState(null, '', `${location.pathname}${location.search}`);
  }
}

function openPaperFromLocation() {
  if (!location.hash.startsWith('#paper=')) return;
  const paperId = decodeURIComponent(location.hash.slice('#paper='.length));
  openPaperModal(paperId, false);
}

function filterCards() {
  const q = $('#search').value.trim().toLowerCase();
  document.querySelectorAll('#paper-sections details').forEach(sec => {
    const groupOk = activeFilter === 'all' || sec.dataset.filter === activeFilter;
    let visible = 0;
    sec.querySelectorAll('.card').forEach(card => {
      const ok = groupOk && (!q || card.dataset.text.includes(q));
      card.style.display = ok ? '' : 'none';
      if(ok) visible++;
    });
    sec.style.display = groupOk && (visible>0 || !q) ? '' : 'none';
  });
}

function setView(view) {
  keepScrollPosition(() => {
    activeView = view;
    activeFilter = 'all';
    renderBrowserFilters();
    renderPaperSections();
    updateFilterButtons();
    filterCards();
  });
}

$('#search').addEventListener('input', filterCards);
$('#clear').onclick = () => keepScrollPosition(() => { $('#search').value=''; activeFilter='all'; updateFilterButtons(); filterCards(); });
$('#view-stage').onclick = () => setView('stage');
$('#view-model').onclick = () => setView('model');
document.addEventListener('click', event => {
  const card = event.target.closest('.paper-card');
  if (!card || !$('#paper-sections').contains(card)) return;
  openPaperModal(card.dataset.paperId);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closePaperModal();
  if ((event.key === 'Enter' || event.key === ' ') && event.target.classList.contains('paper-card')) {
    event.preventDefault();
    openPaperModal(event.target.dataset.paperId);
  }
});
window.addEventListener('hashchange', openPaperFromLocation);
renderPipeline(); renderBars(); renderModelGroups(); renderBrowserFilters(); renderPaperSections(); filterCards(); openPaperFromLocation();
