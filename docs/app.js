/**
 * AutoPaperReading Frontend
 * Papers loaded from papers.json, exported by jobs/export_papers.py
 */

const PAGE_SIZE = 10;
const isLocalHost = () => /^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(window.location.hostname);

let allPapers = [];
let filteredPapers = [];
let currentPage = 1;
let selectedDate = '';
let currentTab = 'all';
let selectedFavTag = '';
let selectedSidebarTag = '';
let favoriteTags = {};
let usedTags = [];
let currentSort = 'date-desc';

// ========== Init ==========
document.addEventListener('DOMContentLoaded', () => {
  loadPapers();
  loadFavorites();
  bindEvents();
});

function bindEvents() {
  document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') handleSearch();
  });
  document.getElementById('searchInput').addEventListener('input', () => handleSearch());
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });
  document.getElementById('newTagInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addNewTag(); }
  });
  // Sidebar clear
  document.addEventListener('click', e => {
    if (e.target.matches('.sidebar-clear-btn')) {
      selectedSidebarTag = '';
      currentPage = 1;
      applyFilters();
      buildSidebar();
    }
  });
}

// ========== Favorites (localStorage) ==========
function loadFavorites() {
  try {
    const stored = localStorage.getItem('apr_favorites');
    if (stored) favoriteTags = JSON.parse(stored).tags || {};
  } catch { favoriteTags = {}; }
}

function saveFavorites() {
  try {
    localStorage.setItem('apr_favorites', JSON.stringify({ tags: favoriteTags }));
  } catch {}
}

function isFavorited(paperId) {
  return paperId in favoriteTags && favoriteTags[paperId].length > 0;
}

function getPaperTags(paperId) {
  return favoriteTags[paperId] || [];
}

function addToFavorites(paperId, tags) {
  const existing = favoriteTags[paperId] || [];
  const newTags = tags.filter(t => !existing.includes(t));
  favoriteTags[paperId] = [...existing, ...newTags];
  saveFavorites();
  updateUsedTags();
}

function removeFromFavorites(paperId) {
  delete favoriteTags[paperId];
  saveFavorites();
  updateUsedTags();
}

function updateUsedTags() {
  const counts = {};
  Object.values(favoriteTags).forEach(tags => {
    tags.forEach(tag => {
      counts[tag] = (counts[tag] || 0) + 1;
    });
  });
  usedTags = Object.entries(counts)
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count);
}

function getFavoritePapers() {
  return allPapers.filter(p => isFavorited(p.paper_id));
}

function getFavoritesByTag(tag) {
  return allPapers.filter(p => {
    if (!isFavorited(p.paper_id)) return false;
    if (!tag) return true;
    return getPaperTags(p.paper_id).includes(tag);
  });
}

// ========== Tab Switching ==========
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.nav-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tab);
  });

  const filterRow = document.getElementById('filterRow');
  const favFilterRow = document.getElementById('favFilterRow');

  if (tab === 'favorites') {
    filterRow.style.display = 'none';
    favFilterRow.style.display = 'flex';
    renderFavTagFilters();
  } else {
    filterRow.style.display = 'flex';
    favFilterRow.style.display = 'none';
  }

  // 清除 tab 间残留的筛选状态，避免侧边栏 tag 跨 tab 污染
  selectedSidebarTag = '';
  selectedFavTag = '';
  selectedDate = '';
  currentPage = 1;

  applyFilters();
  buildSidebar();
  updateSortButtons();
  updateFavBadge();
}

// ========== Favorite Tag Filters ==========
function renderFavTagFilters() {
  const container = document.getElementById('favTagsList');
  if (!container) return;

  const total = getFavoritePapers().length;
  let html = `
    <button class="fav-tag-filter-btn ${!selectedFavTag ? 'active' : ''}" onclick="filterByFavTag('')">
      全部 <span class="count">${total}</span>
    </button>
  `;

  usedTags.forEach(({ tag, count }) => {
    html += `
      <button class="fav-tag-filter-btn ${selectedFavTag === tag ? 'active' : ''}" onclick="filterByFavTag('${escHtml(tag)}')">
        ${escHtml(tag)} <span class="count">${count}</span>
      </button>
    `;
  });

  container.innerHTML = html;
}

function filterByFavTag(tag) {
  selectedFavTag = tag;
  currentPage = 1;
  applyFilters();
  renderFavTagFilters();
}

// ========== Sidebar ==========
function buildSidebar() {
  const container = document.getElementById('sidebarTags');
  if (!container) return;

  const tagCounts = {};
  allPapers.forEach(p => {
    (p.tags || '').split(',').map(t => t.trim().toLowerCase()).filter(Boolean).forEach(t => {
      tagCounts[t] = (tagCounts[t] || 0) + 1;
    });
  });

  const sorted = Object.entries(tagCounts)
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 20);

  let html = '';
  sorted.forEach(({ tag, count }) => {
    const active = selectedSidebarTag === tag;
    html += `
      <button class="sidebar-tag-btn ${active ? 'active' : ''}" onclick="filterBySidebarTag('${escHtml(tag)}')">
        <span class="sidebar-tag-name">${escHtml(tag)}</span>
        <span class="sidebar-tag-count">${count}</span>
      </button>`;
  });

  if (selectedSidebarTag) {
    html += `
      <button class="sidebar-clear-btn" onclick="clearSidebarTag()">
        ✕ 清除筛选
      </button>`;
  }

  container.innerHTML = html || '<span style="font-size:.8rem;color:var(--text-muted);padding:4px 0;">暂无标签数据</span>';
}

function filterBySidebarTag(tag) {
  selectedSidebarTag = selectedSidebarTag === tag ? '' : tag;
  currentPage = 1;
  applyFilters();
  buildSidebar();
}

function clearSidebarTag() {
  selectedSidebarTag = '';
  currentPage = 1;
  applyFilters();
  buildSidebar();
}

// ========== Data Loading ==========
async function loadPapers() {
  try {
    const resp = await fetch('papers.json?' + Date.now());
    if (!resp.ok) throw new Error('not found: ' + resp.status);
    const data = await resp.json();
    allPapers = data.papers || [];
    updateStats(data.stats);
  } catch (err) {
    console.error('Load papers error:', err);
    const stored = localStorage.getItem('apr_papers');
    if (stored) {
      const data = JSON.parse(stored);
      allPapers = data.papers || [];
      updateStats(data.stats);
    } else {
      showEmpty('暂无论文数据，请先运行每日抓取任务');
      return;
    }
  }

  updateUsedTags();
  buildDateFilter();
  buildSortFilter();
  buildTopicFilter();
  buildSidebar();
  applyFilters();
  console.log('loadPapers completed');
}

function updateStats(stats) {
  if (!stats) return;
  document.getElementById('statPapers').textContent = stats.total || allPapers.length;
  document.getElementById('statTopics').textContent = stats.topics || '—';
  document.getElementById('statDate').textContent = stats.lastUpdated || '—';
}

function updateFavBadge() {
  const count = getFavoritePapers().length;
  const badge = document.getElementById('favCount');
  badge.textContent = count;
  badge.style.display = count > 0 ? 'inline-block' : 'none';
}

// ========== Filters ==========
function buildDateFilter() {
  const dates = [...new Set(allPapers.map(p => (p.published || '').slice(0, 10)))]
    .filter(Boolean).sort().reverse();
  const select = document.getElementById('dateFilter');
  select.innerHTML = '<option value="">全部日期</option>';
  dates.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    select.appendChild(opt);
  });
  select.addEventListener('change', handleFilter);
}

function buildTopicFilter() {
  const tags = new Set();
  allPapers.forEach(p => {
    (p.tags || '').split(',').map(t => t.trim()).filter(Boolean).forEach(t => tags.add(t));
  });
  const select = document.getElementById('topicFilter');
  select.innerHTML = '<option value="">全部方向</option>';
  [...tags].sort().forEach(t => {
    const opt = document.createElement('option');
    opt.value = t; opt.textContent = t;
    select.appendChild(opt);
  });
  select.addEventListener('change', handleFilter);
}

function buildSortFilter() {
  const container = document.getElementById('sortBtnGroup');
  if (!container) return;
  container.innerHTML = `
    <button class="sort-btn active" data-sort="date-desc">最新</button>
    <button class="sort-btn" data-sort="date-asc">最早</button>
    <button class="sort-btn" data-sort="title-asc">A→Z</button>
    <button class="sort-btn" data-sort="title-desc">Z→A</button>
  `;
  container.querySelectorAll('.sort-btn').forEach(btn => {
    btn.addEventListener('click', () => setSort(btn.dataset.sort));
  });
}

function handleSearch() {
  currentPage = 1;
  applyFilters();
}

function handleFilter() {
  selectedDate = document.getElementById('dateFilter').value;
  currentPage = 1;
  applyFilters();
}

function handleSort() {
  currentPage = 1;
  applyFilters();
}

function setSort(value) {
  currentSort = value;
  updateSortButtons();
  handleSort();
}

function updateSortButtons() {
  document.querySelectorAll('.sort-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.sort === currentSort);
  });
}

function clearFilters() {
  document.getElementById('searchInput').value = '';
  document.getElementById('topicFilter').value = '';
  currentSort = 'date-desc';
  document.getElementById('dateFilter').value = '';
  selectedDate = '';
  selectedSidebarTag = '';
  currentPage = 1;
  applyFilters();
  buildSidebar();
  updateSortButtons();
  document.getElementById('searchInput').focus();
}

function applyFilters() {
  const query = document.getElementById('searchInput').value.trim().toLowerCase();
  const topic = document.getElementById('topicFilter').value;
  const sort = currentSort;
  const date = document.getElementById('dateFilter').value || selectedDate;

  if (currentTab === 'favorites') {
    filteredPapers = getFavoritesByTag(selectedFavTag);
    if (query) {
      filteredPapers = filteredPapers.filter(p => {
        const haystack = [p.title, p.authors, p.tags || '', p.summary || ''].join(' ').toLowerCase();
        return haystack.includes(query);
      });
    }
  } else {
    filteredPapers = allPapers.filter(p => {
      if (query) {
        const haystack = [p.title, p.authors, p.tags || '', p.summary || ''].join(' ').toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      if (topic) {
        if (!(p.tags || '').split(',').map(t => t.trim()).includes(topic)) return false;
      }
      if (date) {
        if ((p.published || '').slice(0, 10) !== date) return false;
      }
      if (selectedSidebarTag) {
        if (!(p.tags || '').split(',').map(t => t.trim().toLowerCase()).includes(selectedSidebarTag.toLowerCase())) return false;
      }
      return true;
    });
  }

  if (sort === 'date-desc') filteredPapers.sort((a, b) => (b.published || '').localeCompare(a.published || ''));
  else if (sort === 'date-asc') filteredPapers.sort((a, b) => (a.published || '').localeCompare(b.published || ''));
  else if (sort === 'title-asc') filteredPapers.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
  else if (sort === 'title-desc') filteredPapers.sort((a, b) => (b.title || '').localeCompare(a.title || ''));

  renderPapers();
  updateFavBadge();
}

// ========== Render ==========
function renderPapers() {
  const list = document.getElementById('paperList');
  const empty = document.getElementById('emptyState');
  const count = document.getElementById('resultsCount');
  const totalPages = Math.ceil(filteredPapers.length / PAGE_SIZE) || 1;
  if (currentPage > totalPages) currentPage = totalPages;

  const tabLabel = currentTab === 'favorites' ? '（收藏）' : '';
  count.textContent = `${filteredPapers.length} 篇论文${tabLabel}`;
  empty.style.display = filteredPapers.length === 0 ? 'block' : 'none';

  if (filteredPapers.length === 0) {
    list.innerHTML = '';
    document.getElementById('pagination').style.display = 'none';
    if (currentTab === 'favorites') {
      empty.querySelector('h3').textContent = '暂无收藏';
      empty.querySelector('p').textContent = '点击论文卡片上的收藏按钮添加收藏';
    } else {
      empty.querySelector('h3').textContent = '没有找到相关论文';
      empty.querySelector('p').textContent = '试试其他关键词，或调整筛选条件';
    }
    return;
  }

  const pagePapers = filteredPapers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  list.innerHTML = pagePapers.map(paper => {
    const tags = (paper.tags || '').split(',').map(t => t.trim()).filter(Boolean);
    const intro = extractIntro(paper.summary);
    const date = formatDate(paper.published);
    const faved = isFavorited(paper.paper_id);
    const favPaperTags = getPaperTags(paper.paper_id);

    return `
    <div class="paper-card" onclick="openModal('${paper.paper_id}')">
      <div class="paper-card-header">
        <div class="paper-title">${renderLatex(paper.title)}</div>
        <span class="paper-date-badge">${date}</span>
      </div>
      <div class="paper-authors">👥 ${escHtml(paper.authors || '未知')}</div>
      ${paper.affiliations ? `<div class="paper-affiliations">🏛️ ${escHtml(paper.affiliations)}</div>` : ''}
      <div class="paper-card-intro">
        <span class="intro-label">📖</span>
        <span class="intro-text">${escHtml(intro)}</span>
      </div>
      <div class="paper-footer">
        <div class="paper-tags">
          ${tags.slice(0, 5).map(t => `<span class="tag">${escHtml(t)}</span>`).join('')}
          ${tags.length > 5 ? `<span class="tag">+${tags.length - 5}</span>` : ''}
          ${faved ? favPaperTags.slice(0, 3).map(t => `<span class="fav-tag-chip">❤️ ${escHtml(t)}</span>`).join('') : ''}
          ${faved && favPaperTags.length > 3 ? `<span class="fav-tag-chip">+${favPaperTags.length - 3}</span>` : ''}
        </div>
        <div class="paper-actions">
          ${faved ? `
            <button class="fav-btn favorited" onclick="event.stopPropagation(); openFavoriteModal('${paper.paper_id}')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
              已收藏
            </button>` : `
            <button class="fav-btn" onclick="event.stopPropagation(); openFavoriteModal('${paper.paper_id}')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
              收藏
            </button>`}
          ${paper.local_pdf_path && isLocalHost() ? `
            <a class="btn-ghost local-pdf-link-card" href="${paper.local_pdf_path}" target="_blank" onclick="event.stopPropagation()" title="本地 PDF（离线可用）">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14,2 14,8 20,8"/>
              </svg>
              PDF
            </a>` : ''}
          ${paper.code_url ? `
            <a class="btn-ghost code-link-card" href="${paper.code_url}" target="_blank" onclick="event.stopPropagation()" title="开源代码">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
              </svg>
              代码
            </a>` : ''}
          <a class="btn-ghost" href="${paper.entry_url || '#'}" target="_blank" onclick="event.stopPropagation()" style="text-decoration:none;">
            arXiv ↗
          </a>
        </div>
      </div>
    </div>`;
  }).join('');

  renderPagination(totalPages);

  // 渲染 LaTeX 公式
  if (window.MathJax && window.MathJax.typesetPromise) {
    MathJax.typesetPromise([list]).catch(console.warn);
  }
}

function renderPagination(totalPages) {
  const pagination = document.getElementById('pagination');
  if (totalPages <= 1) { pagination.style.display = 'none'; return; }
  pagination.style.display = 'flex';
  document.getElementById('prevBtn').disabled = currentPage <= 1;
  document.getElementById('nextBtn').disabled = currentPage >= totalPages;
  document.getElementById('pageInfo').textContent = `第 ${currentPage} / ${totalPages} 页，共 ${filteredPapers.length} 篇`;
}

function prevPage() {
  if (currentPage <= 1) return;
  currentPage--;
  renderPapers();
  scrollToTop();
}

function nextPage() {
  const totalPages = Math.ceil(filteredPapers.length / PAGE_SIZE) || 1;
  if (currentPage >= totalPages) return;
  currentPage++;
  renderPapers();
  scrollToTop();
}

function scrollToTop() {
  document.getElementById('paperList').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ========== Favorite Modal ==========
let currentFavPaperId = '';
let pendingSelectedTags = [];

function openFavoriteModal(paperId) {
  currentFavPaperId = paperId;
  const paper = allPapers.find(p => p.paper_id === paperId);
  if (!paper) return;

  document.getElementById('favoriteModalTitle').textContent = paper.title;
  pendingSelectedTags = [...getPaperTags(paperId)];
  renderExistingTags();
  renderSelectedTags();

  document.getElementById('favoriteModalOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';
  document.getElementById('newTagInput').focus();
}

function closeFavoriteModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('favoriteModalOverlay').classList.remove('active');
  document.body.style.overflow = '';
  currentFavPaperId = '';
  pendingSelectedTags = [];
}

function renderExistingTags() {
  const container = document.getElementById('existingTags');
  const paperTags = (allPapers.find(p => p.paper_id === currentFavPaperId)?.tags || '')
    .split(',').map(t => t.trim()).filter(Boolean);
  const allTagSet = new Set([...usedTags.map(t => t.tag), ...paperTags]);

  if (allTagSet.size === 0) {
    container.innerHTML = '<span style="font-size:.82rem;color:var(--text-muted);">暂无标签，请添加新标签</span>';
    return;
  }

  container.innerHTML = [...allTagSet].map(tag => {
    const sel = pendingSelectedTags.includes(tag);
    return `<button class="tag-option ${sel ? 'selected' : ''}" onclick="toggleTag('${escHtml(tag)}')">${escHtml(tag)}</button>`;
  }).join('');
}

function renderSelectedTags() {
  const container = document.getElementById('selectedTags');
  if (pendingSelectedTags.length === 0) { container.innerHTML = ''; return; }
  container.innerHTML = pendingSelectedTags.map(tag => `
    <span class="selected-tag">
      ${escHtml(tag)}
      <span class="selected-tag-remove" onclick="toggleTag('${escHtml(tag)}')">✕</span>
    </span>`).join('');
}

function toggleTag(tag) {
  const idx = pendingSelectedTags.indexOf(tag);
  if (idx >= 0) pendingSelectedTags.splice(idx, 1);
  else pendingSelectedTags.push(tag);
  renderExistingTags();
  renderSelectedTags();
}

function addNewTag() {
  const input = document.getElementById('newTagInput');
  const tag = input.value.trim();
  if (!tag) return;
  if (!pendingSelectedTags.includes(tag)) {
    pendingSelectedTags.push(tag);
    renderExistingTags();
    renderSelectedTags();
  }
  input.value = '';
  input.focus();
}

function confirmFavorite() {
  if (pendingSelectedTags.length === 0) removeFromFavorites(currentFavPaperId);
  else addToFavorites(currentFavPaperId, pendingSelectedTags);
  closeFavoriteModal();
  renderPapers();
  if (currentTab === 'favorites') renderFavTagFilters();
}

// ========== Paper Detail Modal ==========
function openModal(paperId) {
  const paper = allPapers.find(p => p.paper_id === paperId);
  if (!paper) return;

  document.getElementById('modalTitle').innerHTML = renderLatex(paper.title);
  document.getElementById('modalAuthors').textContent = `👥 ${paper.authors || '未知'}`;
  document.getElementById('modalDate').textContent = `📅 ${formatDate(paper.published)}`;

  // 机构信息
  const affiliationsEl = document.getElementById('modalAffiliations');
  const aff = paper.affiliations || '';
  if (aff) {
    affiliationsEl.innerHTML = `<strong>🏛️ 机构：</strong>${escHtml(aff)}`;
    affiliationsEl.style.display = 'block';
  } else {
    affiliationsEl.textContent = '';
    affiliationsEl.style.display = 'none';
  }

  const tags = (paper.tags || '').split(',').map(t => t.trim()).filter(Boolean);
  const favTags = getPaperTags(paperId);
  const allTags = [...new Set([...tags, ...favTags])];
  document.getElementById('modalTags').innerHTML = allTags.map(t => {
    const isFav = favTags.includes(t);
    return `<span class="tag ${isFav ? 'fav-tag-chip' : ''}">${escHtml(t)}</span>`;
  }).join('');

  const faved = isFavorited(paperId);
  let linksHtml = '';
  if (faved) {
    linksHtml += `
      <button class="fav-btn favorited" onclick="openFavoriteModal('${paperId}')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
        已收藏${favTags.length > 0 ? ` (${favTags.length})` : ''}
      </button>`;
  } else {
    linksHtml += `
      <button class="fav-btn" onclick="openFavoriteModal('${paperId}')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
        收藏
      </button>`;
  }
  // 本地 PDF 链接
  if (paper.local_pdf_path && isLocalHost()) {
    linksHtml += `
      <a class="modal-link local-pdf-link" href="${paper.local_pdf_path}" target="_blank" title="离线可用">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14,2 14,8 20,8"/>
        </svg>
        本地 PDF
      </a>`;
  }
  // 代码链接
  if (paper.code_url) {
    linksHtml += `
      <a class="modal-link code-link" href="${paper.code_url}" target="_blank" title="开源代码">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
        </svg>
        代码
      </a>`;
  }
  // arXiv 页面
  linksHtml += `
    <a class="modal-link" href="${paper.entry_url || '#'}" target="_blank">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
        <polyline points="15,3 21,3 21,9"/><line x1="10" y1="14" x2="21" y2="3"/>
      </svg>
      arXiv 页面
    </a>`;
  document.getElementById('modalLinks').innerHTML = linksHtml;

  document.getElementById('modalSummary').innerHTML = renderSummary(paper.summary || '暂无总结');
  document.getElementById('modalOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';
  // 通知 MathJax 渲染新内容
  // Typeset LaTeX in the modal
  if (window.MathJax && window.MathJax.typesetPromise) {
    MathJax.typesetPromise([document.getElementById('modalSummary')]).catch(console.warn);
  }
}

function closeModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('modalOverlay').classList.remove('active');
  document.body.style.overflow = '';
}

// ========== Summary Render ==========
function renderSummary(text) {
  if (!text) return '<p>暂无总结</p>';
  return text
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

function showEmpty(msg) {
  document.getElementById('resultsCount').textContent = '0 篇论文';
  document.getElementById('paperList').innerHTML = '';
  document.getElementById('pagination').style.display = 'none';
  const empty = document.getElementById('emptyState');
  empty.style.display = 'block';
  empty.querySelector('h3').textContent = msg;
  empty.querySelector('p').textContent = '请先运行每日抓取任务';
}

// ========== Helpers ==========
function extractIntro(summary) {
  if (!summary) return '暂无总结';
  const lines = summary.split('\n');
  let inSection = false;
  const sectionLines = [];
  for (const line of lines) {
    const stripped = line.trim();
    if (/^##\s*三[.、]一句话总结/.test(stripped)) { inSection = true; continue; }
    if (inSection && stripped.startsWith('##')) break;
    if (inSection && stripped) sectionLines.push(stripped);
  }
  if (sectionLines.length > 0) {
    const text = sectionLines.join(' ').replace(/[#*`_\[\]]/g, '').trim();
    return text.length > 150 ? text.slice(0, 150) + '…' : text;
  }
  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped) continue;
    if (/^#{1,3}\s/.test(stripped)) continue;
    if (/^[-*]\s/.test(stripped)) continue;
    if (/^\d+[.、)]/.test(stripped)) continue;
    const clean = stripped.replace(/[#*`_\[\]]/g, '').replace(/\n/g, ' ').trim();
    return clean.length > 150 ? clean.slice(0, 150) + '…' : clean;
  }
  return '暂无总结';
}

function formatDate(dateStr) {
  if (!dateStr) return '未知日期';
  return dateStr.slice(0, 10);
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Escape HTML special chars but preserve LaTeX commands intact for MathJax
function renderLatex(str) {
  if (!str) return '';
  // Replace HTML special chars INSIDE LaTeX math mode only, leave LaTeX commands alone
  // Process display math $$...$$ → \[...\] and inline $...$ → \(...\)
  return str
    .replace(/\$\$([\s\S]+?)\$\$/g, (match, math) => {
      return '\\[' + escapeHtmlForLatex(math) + '\\]';
    })
    .replace(/\$([^$\n]+?)\$/g, (match, math) => {
      return '\\(' + escapeHtmlForLatex(math) + '\\)';
    });
}

// Escape HTML only for content that should be escaped, preserving LaTeX syntax
function escapeHtmlForLatex(str) {
  return String(str)
    .replace(/&(?!amp;|lt;|gt;|quot;|#[0-9]+;|#x[0-9a-fA-F]+;)/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

