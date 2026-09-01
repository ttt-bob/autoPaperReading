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
const detailCache = new Map();
let manifest = null;
const pageCache = new Map();
let browseMode = true;
let authApiAvailable = false;
let currentUser = null;
let authConfig = { emailVerification: false, passwordReset: false, githubLogin: false };
let pendingFavoriteAfterLogin = '';

// ========== Init ==========
document.addEventListener('DOMContentLoaded', async () => {
  bindEvents();
  await initializeAuth();
  await loadPapers();
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

// ========== Account and private favorites ==========
async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || '请求失败');
    error.code = payload.code;
    throw error;
  }
  return payload;
}

async function initializeAuth() {
  try {
    authConfig = await apiFetch('api/config');
    authApiAvailable = true;
    const data = await apiFetch('api/auth/me');
    currentUser = data.user;
    await loadFavorites();
  } catch (error) {
    console.info('Account API is unavailable for this static deployment.', error);
    authApiAvailable = false;
    currentUser = null;
    favoriteTags = {};
  }
  updateAccountUi();
  handleGithubLoginResult();
}

function handleGithubLoginResult() {
  const url = new URL(window.location.href);
  const result = url.searchParams.get('github_login');
  if (!result) return;
  const messages = {
    success: 'GitHub 登录成功',
    cancelled: '已取消 GitHub 登录',
    state_error: 'GitHub 登录校验失败，请重试',
    failed: 'GitHub 登录失败，请重试',
  };
  showToast(messages[result] || 'GitHub 登录未完成', result === 'success' ? 'success' : 'error');
  url.searchParams.delete('github_login');
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
}

async function loadFavorites() {
  favoriteTags = {};
  if (!authApiAvailable || !currentUser) {
    updateUsedTags();
    return;
  }
  const data = await apiFetch('api/favorites');
  favoriteTags = data.favorites || {};
  updateUsedTags();
}

function isFavorited(paperId) {
  return Object.prototype.hasOwnProperty.call(favoriteTags, paperId);
}

function getPaperTags(paperId) {
  return favoriteTags[paperId] || [];
}

async function addToFavorites(paperId, tags) {
  const data = await apiFetch(`api/favorites/${encodeURIComponent(paperId)}`, {
    method: 'PUT',
    body: JSON.stringify({ tags }),
  });
  favoriteTags[paperId] = data.tags || [];
  updateUsedTags();
}

async function removeFromFavorites(paperId) {
  await apiFetch(`api/favorites/${encodeURIComponent(paperId)}`, { method: 'DELETE' });
  delete favoriteTags[paperId];
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

function updateAccountUi() {
  const loginButton = document.getElementById('loginButton');
  const accountMenu = document.getElementById('accountMenu');
  const accountEmail = document.getElementById('accountEmail');
  if (!loginButton || !accountMenu || !accountEmail) return;
  loginButton.hidden = Boolean(currentUser);
  accountMenu.hidden = !currentUser;
  accountEmail.textContent = currentUser?.email || '';
}

function openAuthModal(mode = 'login') {
  if (!authApiAvailable) {
    showToast('当前静态页面未启用账户服务，请使用服务器上的 /autopaperreading/ 页面。', 'error');
    return;
  }
  document.getElementById('authModalOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';
  renderAuthForm(mode);
}

function closeAuthModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById('authModalOverlay').classList.remove('active');
  document.body.style.overflow = '';
}

function renderAuthForm(mode, email = '') {
  const title = document.getElementById('authModalTitle');
  const body = document.getElementById('authModalBody');
  const escapedEmail = escHtml(email);
  const emailField = `
    <label class="auth-field">邮箱
      <input id="authEmail" type="email" autocomplete="email" required value="${escapedEmail}" placeholder="name@example.com">
    </label>`;
  const passwordField = (id = 'authPassword', label = '密码', autocomplete = 'current-password') => `
    <label class="auth-field">${label}
      <input id="${id}" type="password" autocomplete="${autocomplete}" required minlength="8" placeholder="至少 8 个字符">
    </label>`;
  const githubLogin = authConfig.githubLogin ? `
    <a class="auth-github" href="api/auth/github/start">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 .7a11.5 11.5 0 0 0-3.64 22.4c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.52-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.27 3.38.97.1-.75.4-1.27.74-1.56-2.57-.3-5.27-1.29-5.27-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.06 0 0 .97-.31 3.16 1.18a10.96 10.96 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.59.23 2.77.11 3.06.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.39-5.28 5.68.42.36.79 1.07.79 2.16v3.2c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z"/>
      </svg>
      使用 GitHub 登录
    </a>
    <div class="auth-divider"><span>或使用邮箱</span></div>` : '';

  if (mode === 'register') {
    title.textContent = '创建账户';
    body.innerHTML = `<p class="auth-note">收藏和个人标签只保存在你的账户中，不会同步给其他人。</p>
      <form class="auth-form" onsubmit="submitRegister(event)">${emailField}${passwordField('authPassword', '设置密码', 'new-password')}${passwordField('authPasswordConfirm', '确认密码', 'new-password')}
      <button class="btn-primary auth-submit" type="submit">注册并继续</button></form>
      <p class="auth-switch">已有账户？<button type="button" onclick="renderAuthForm('login')">登录</button></p>`;
  } else if (mode === 'verify') {
    title.textContent = '验证邮箱';
    body.innerHTML = `<p class="auth-note">验证码已发送至 <strong>${escapedEmail}</strong>，有效期 15 分钟。</p>
      <form class="auth-form" onsubmit="submitEmailVerification(event)">${emailField}
      <label class="auth-field">6 位验证码<input id="authCode" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" required placeholder="000000"></label>
      <button class="btn-primary auth-submit" type="submit">验证并登录</button></form>`;
      body.innerHTML += `<p class="auth-switch">没收到？<button type="button" onclick="resendVerification()">重新发送验证码</button></p>`;
  } else if (mode === 'reset-request') {
    title.textContent = '找回密码';
    const hint = authConfig.passwordReset ? '我们会向你的邮箱发送 6 位验证码。' : '邮件服务暂未配置，当前无法通过邮箱找回密码。';
    body.innerHTML = `<p class="auth-note">${hint}</p><form class="auth-form" onsubmit="submitResetRequest(event)">${emailField}
      <button class="btn-primary auth-submit" type="submit" ${authConfig.passwordReset ? '' : 'disabled'}>发送验证码</button></form>
      <p class="auth-switch"><button type="button" onclick="renderAuthForm('login')">返回登录</button></p>`;
  } else if (mode === 'reset-confirm') {
    title.textContent = '设置新密码';
    body.innerHTML = `<p class="auth-note">输入邮箱验证码和新密码。</p><form class="auth-form" onsubmit="submitResetConfirm(event)">${emailField}
      <label class="auth-field">6 位验证码<input id="authCode" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" required placeholder="000000"></label>
      ${passwordField('authPassword', '新密码', 'new-password')}${passwordField('authPasswordConfirm', '确认新密码', 'new-password')}
      <button class="btn-primary auth-submit" type="submit">更新密码</button></form>`;
  } else {
    title.textContent = '登录';
    body.innerHTML = `<p class="auth-note">登录后即可保存私有收藏和自定义标签。</p>${githubLogin}<form class="auth-form" onsubmit="submitLogin(event)">${emailField}${passwordField()}
      <button class="btn-primary auth-submit" type="submit">登录</button></form>
      <p class="auth-switch"><button type="button" onclick="renderAuthForm('register')">创建账户</button><span>·</span><button type="button" onclick="renderAuthForm('reset-request')">忘记密码</button></p>`;
  }
  document.getElementById('authEmail')?.focus();
}

async function submitLogin(event) {
  event.preventDefault();
  const email = document.getElementById('authEmail').value;
  const password = document.getElementById('authPassword').value;
  try {
    const data = await apiFetch('api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    await finishLogin(data.user);
  } catch (error) { showToast(error.message, 'error'); }
}

async function submitRegister(event) {
  event.preventDefault();
  const email = document.getElementById('authEmail').value;
  const password = document.getElementById('authPassword').value;
  if (password !== document.getElementById('authPasswordConfirm').value) {
    showToast('两次输入的密码不一致', 'error');
    return;
  }
  try {
    const data = await apiFetch('api/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) });
    if (data.verificationRequired) {
      renderAuthForm('verify', data.email);
      showToast('验证码已发送，请检查邮箱');
    } else {
      await finishLogin(data.user);
      showToast('账户已创建');
    }
  } catch (error) { showToast(error.message, 'error'); }
}

async function submitEmailVerification(event) {
  event.preventDefault();
  const email = document.getElementById('authEmail').value;
  const code = document.getElementById('authCode').value;
  try {
    const data = await apiFetch('api/auth/verify-email', { method: 'POST', body: JSON.stringify({ email, code }) });
    await finishLogin(data.user);
    showToast('邮箱验证完成');
  } catch (error) { showToast(error.message, 'error'); }
}

async function resendVerification() {
  const email = document.getElementById('authEmail').value;
  try {
    const data = await apiFetch('api/auth/verification/resend', {
      method: 'POST', body: JSON.stringify({ email }),
    });
    showToast(data.message);
  } catch (error) { showToast(error.message, 'error'); }
}

async function submitResetRequest(event) {
  event.preventDefault();
  const email = document.getElementById('authEmail').value;
  try {
    const data = await apiFetch('api/auth/password-reset/request', { method: 'POST', body: JSON.stringify({ email }) });
    showToast(data.message);
    renderAuthForm('reset-confirm', email);
  } catch (error) { showToast(error.message, 'error'); }
}

async function submitResetConfirm(event) {
  event.preventDefault();
  const email = document.getElementById('authEmail').value;
  const password = document.getElementById('authPassword').value;
  if (password !== document.getElementById('authPasswordConfirm').value) {
    showToast('两次输入的密码不一致', 'error');
    return;
  }
  try {
    await apiFetch('api/auth/password-reset/confirm', {
      method: 'POST', body: JSON.stringify({ email, code: document.getElementById('authCode').value, password }),
    });
    showToast('密码已更新，请使用新密码登录');
    renderAuthForm('login', email);
  } catch (error) { showToast(error.message, 'error'); }
}

async function finishLogin(user) {
  currentUser = user;
  await loadFavorites();
  updateAccountUi();
  closeAuthModal();
  updateFavBadge();
  renderPapers();
  if (pendingFavoriteAfterLogin) {
    const paperId = pendingFavoriteAfterLogin;
    pendingFavoriteAfterLogin = '';
    openFavoriteModal(paperId);
  }
}

async function logout() {
  try { await apiFetch('api/auth/logout', { method: 'POST', body: JSON.stringify({}) }); } catch (error) { console.error(error); }
  currentUser = null;
  favoriteTags = {};
  updateUsedTags();
  updateAccountUi();
  updateFavBadge();
  if (currentTab === 'favorites') switchTab('all');
  else renderPapers();
  showToast('已退出登录');
}

function showToast(message, type = 'success') {
  const toast = document.getElementById('appToast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `app-toast ${type} visible`;
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => toast.classList.remove('visible'), 3200);
}

// ========== Tab Switching ==========
async function switchTab(tab) {
  if (tab === 'favorites' && !currentUser) {
    openAuthModal('login');
    showToast('登录后查看你的收藏与标签', 'error');
    return;
  }
  if (tab === 'favorites') await enableSearchMode();
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

  const tagCounts = manifest?.stats?.tagCounts || {};

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

async function filterBySidebarTag(tag) {
  selectedSidebarTag = selectedSidebarTag === tag ? '' : tag;
  currentPage = 1;
  if (selectedSidebarTag) await enableSearchMode();
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
    const resp = await fetch('paper-data/manifest.json');
    if (!resp.ok) throw new Error('not found: ' + resp.status);
    manifest = await resp.json();
    updateStats(manifest.stats);
    await loadBrowsePage(1);
  } catch (err) {
    console.error('Load papers error:', err);
    const stored = localStorage.getItem('apr_papers');
    showEmpty('暂无论文数据，请先运行每日抓取任务');
    return;
  }

  updateUsedTags();
  buildDateFilter();
  buildSortFilter();
  buildTopicFilter();
  buildSidebar();
  const initialQuery = new URLSearchParams(window.location.search).get('q');
  if (initialQuery) {
    document.getElementById('searchInput').value = initialQuery;
    await enableSearchMode();
  }
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
  const count = Object.keys(favoriteTags).length;
  const badge = document.getElementById('favCount');
  badge.textContent = count;
  badge.style.display = count > 0 ? 'inline-block' : 'none';
}

// ========== Filters ==========
function buildDateFilter() {
  const dates = manifest?.stats?.dates || [];
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
  const tags = Object.keys(manifest?.stats?.tagCounts || {});
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

async function handleSearch() {
  currentPage = 1;
  if (document.getElementById('searchInput').value.trim()) await enableSearchMode();
  applyFilters();
}

async function handleFilter() {
  selectedDate = document.getElementById('dateFilter').value;
  currentPage = 1;
  if (selectedDate || document.getElementById('topicFilter').value) await enableSearchMode();
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
  if (browseMode) loadBrowsePage(1);
  else applyFilters();
  buildSidebar();
  updateSortButtons();
  document.getElementById('searchInput').focus();
}

async function loadBrowsePage(pageNumber) {
  if (!manifest) return;
  try {
    let page = pageCache.get(pageNumber);
    if (!page) {
      const resp = await fetch(`paper-data/pages/${pageNumber}.json`);
      if (!resp.ok) throw new Error(`page request failed: ${resp.status}`);
      page = await resp.json();
      pageCache.set(pageNumber, page);
    }
    browseMode = true;
    currentPage = pageNumber;
    allPapers = page.papers || [];
    filteredPapers = allPapers;
    renderPapers();
    updateFavBadge();
  } catch (err) {
    console.error('Load paper page error:', err);
    showEmpty('论文列表加载失败，请稍后重试');
  }
}

async function enableSearchMode() {
  if (!browseMode) return;
  const resp = await fetch('paper-data/search-index.json');
  if (!resp.ok) throw new Error(`search index request failed: ${resp.status}`);
  const data = await resp.json();
  allPapers = data.papers || [];
  browseMode = false;
}

function normalizeSearchText(value) {
  return String(value || '').toLocaleLowerCase().replace(/[\s，,。；;：:、/_-]+/g, '');
}

function extractSearchArxivId(value) {
  const match = String(value || '').match(
    /(?:arxiv\.org\/(?:abs|pdf|html)\/)?(\d{4}\.\d{4,5})(?:v\d+)?/i,
  );
  return match ? match[1].toLocaleLowerCase() : '';
}

function canonicalSearchUrl(value) {
  try {
    const url = new URL(String(value || '').trim());
    if (!['http:', 'https:'].includes(url.protocol)) return '';
    const path = url.pathname.replace(/\/$/, '');
    return `${url.hostname.toLocaleLowerCase()}${path}${url.search}`;
  } catch {
    return '';
  }
}

function isExactSearchMatch(paper, rawQuery) {
  const arxivId = extractSearchArxivId(rawQuery);
  const paperId = String(paper.paper_id || '').toLocaleLowerCase();
  if (arxivId && (paperId === arxivId || paperId.startsWith(`${arxivId}v`))) return true;
  const queryUrl = canonicalSearchUrl(rawQuery);
  if (!queryUrl) return false;
  return [paper.entry_url, paper.code_url].some(value => canonicalSearchUrl(value) === queryUrl);
}

function isSubmissionSearchQuery(value) {
  const query = String(value || '').trim();
  if (/^\d{4}\.\d{4,5}(?:v\d+)?$/i.test(query)) return true;
  return Boolean(canonicalSearchUrl(query));
}

function updateSearchSubmissionPrompt() {
  const prompt = document.getElementById('searchSubmissionPrompt');
  const link = document.getElementById('searchSubmissionLink');
  const query = document.getElementById('searchInput').value.trim();
  const hasExactMatch = query && allPapers.some(paper => isExactSearchMatch(paper, query));
  const shouldOfferSubmission = isSubmissionSearchQuery(query) && !hasExactMatch;
  prompt.hidden = !shouldOfferSubmission;
  if (shouldOfferSubmission) {
    link.href = `submit-paper.html?url=${encodeURIComponent(query)}`;
  }
}

function paperRelevanceScore(paper, rawQuery) {
  const query = normalizeSearchText(rawQuery);
  if (!query) return 0;

  const title = normalizeSearchText(paper.title);
  const authors = normalizeSearchText(paper.authors);
  const tags = normalizeSearchText(paper.tags);
  const details = normalizeSearchText(
    `${paper.intro || ''} ${paper.abstract || ''} ${paper.summary || ''}`,
  );
  const identifiers = normalizeSearchText(
    `${paper.paper_id || ''} ${paper.entry_url || ''} ${paper.code_url || ''}`,
  );
  const ignoredTokens = new Set([
    'a', 'an', 'and', 'are', 'for', 'in', 'is', 'of', 'on', 'the', 'to', 'with',
    'http', 'https', 'www', 'org', 'com', 'arxiv', 'abs', 'pdf', 'html',
  ]);
  const arxivId = extractSearchArxivId(rawQuery);
  const tokens = arxivId
    ? [normalizeSearchText(arxivId)]
    : String(rawQuery)
      .split(/[\s，,。；;：:、/_.?&=#-]+/)
      .map(normalizeSearchText)
      .filter(token => token.length > 1 && !ignoredTokens.has(token));
  let score = 0;

  if (isExactSearchMatch(paper, rawQuery)) score += 2500;
  if (title === query) score += 1000;
  if (title.includes(query)) score += 500;
  if (identifiers.includes(query)) score += 420;
  if (tags.includes(query)) score += 320;
  if (authors.includes(query)) score += 240;
  if (details.includes(query)) score += 100;
  tokens.forEach(token => {
    if (title.includes(token)) score += 80;
    if (identifiers.includes(token)) score += 70;
    if (tags.includes(token)) score += 45;
    if (authors.includes(token)) score += 35;
    if (details.includes(token)) score += 15;
  });
  return score;
}

function applyFilters() {
  const query = document.getElementById('searchInput').value.trim();
  const topic = document.getElementById('topicFilter').value;
  const sort = currentSort;
  const date = document.getElementById('dateFilter').value || selectedDate;
  const scores = new Map();

  if (currentTab === 'favorites') {
    filteredPapers = getFavoritesByTag(selectedFavTag);
    if (query) {
      filteredPapers = filteredPapers.filter(paper => {
        const score = paperRelevanceScore(paper, query);
        scores.set(paper.paper_id, score);
        return score > 0;
      });
    }
  } else {
    filteredPapers = allPapers.filter(p => {
      if (query) {
        const score = paperRelevanceScore(p, query);
        scores.set(p.paper_id, score);
        if (score <= 0) return false;
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

  if (query) {
    filteredPapers.sort((a, b) => (scores.get(b.paper_id) || 0) - (scores.get(a.paper_id) || 0)
      || (b.published || '').localeCompare(a.published || ''));
  } else if (sort === 'date-desc') filteredPapers.sort((a, b) => (b.published || '').localeCompare(a.published || ''));
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
  updateSearchSubmissionPrompt();
  const totalPages = browseMode && currentTab === 'all'
    ? (manifest?.page_count || 1)
    : (Math.ceil(filteredPapers.length / PAGE_SIZE) || 1);
  if (currentPage > totalPages) currentPage = totalPages;

  const tabLabel = currentTab === 'favorites' ? '（收藏）' : '';
  const countTotal = browseMode && currentTab === 'all'
    ? (manifest?.stats?.total || 0)
    : filteredPapers.length;
  count.textContent = `${countTotal} 篇论文${tabLabel}`;
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

  const pagePapers = browseMode && currentTab === 'all'
    ? filteredPapers
    : filteredPapers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  list.innerHTML = pagePapers.map(paper => {
    const tags = (paper.tags || '').split(',').map(t => t.trim()).filter(Boolean);
    const intro = paper.intro || '暂无总结';
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
  if (browseMode && currentTab === 'all') {
    loadBrowsePage(currentPage - 1).then(scrollToTop);
    return;
  }
  currentPage--;
  renderPapers();
  scrollToTop();
}

function nextPage() {
  const totalPages = browseMode && currentTab === 'all'
    ? (manifest?.page_count || 1)
    : (Math.ceil(filteredPapers.length / PAGE_SIZE) || 1);
  if (currentPage >= totalPages) return;
  if (browseMode && currentTab === 'all') {
    loadBrowsePage(currentPage + 1).then(scrollToTop);
    return;
  }
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
  if (!currentUser) {
    pendingFavoriteAfterLogin = paperId;
    openAuthModal('login');
    showToast('收藏前请先登录', 'error');
    return;
  }
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

async function confirmFavorite() {
  try {
    if (pendingSelectedTags.length === 0 && isFavorited(currentFavPaperId)) {
      await removeFromFavorites(currentFavPaperId);
      showToast('已取消收藏');
    } else {
      await addToFavorites(currentFavPaperId, pendingSelectedTags);
      showToast('已保存到你的收藏');
    }
    closeFavoriteModal();
    renderPapers();
    updateFavBadge();
    if (currentTab === 'favorites') renderFavTagFilters();
  } catch (error) {
    if (error.code === 'login_required') {
      closeFavoriteModal();
      openAuthModal('login');
    }
    showToast(error.message, 'error');
  }
}

// ========== Paper Detail Modal ==========
async function openModal(paperId) {
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
  linksHtml += `
    <a class="modal-link" href="paper.html?id=${encodeURIComponent(paperId)}">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14,2 14,8 20,8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/>
      </svg>
      独立详情页
    </a>`;
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
  const summaryEl = document.getElementById('modalSummary');
  summaryEl.innerHTML = '<p>正在加载论文详情…</p>';
  document.getElementById('modalOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';

  try {
    const detail = await loadPaperDetail(paper);
    // The user may have opened a different paper while this request was in flight.
    if (!document.getElementById('modalOverlay').classList.contains('active')) return;
    summaryEl.innerHTML = renderSummary(detail.summary || '暂无总结');
  } catch (err) {
    console.error('Load paper detail error:', err);
    summaryEl.innerHTML = '<p>论文详情加载失败，请稍后重试。</p>';
  }
}

async function loadPaperDetail(paper) {
  if (!paper.detail_path) return paper;
  if (detailCache.has(paper.paper_id)) return detailCache.get(paper.paper_id);

  const resp = await fetch(paper.detail_path);
  if (!resp.ok) throw new Error(`detail request failed: ${resp.status}`);
  const detail = await resp.json();
  detailCache.set(paper.paper_id, detail);
  return detail;
}

function closeModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('modalOverlay').classList.remove('active');
  document.body.style.overflow = '';
}

// ========== Summary Render ==========
const SUMMARY_METADATA_FIELDS = new Set([
  '标题',
  '作者列表',
  '作者列表（原文）',
  '所属机构',
  '发表时间',
  '开源代码地址',
  '开源许可证',
  '开源许可证类型',
]);

const SUMMARY_BREAK_FIELDS = [
  ...SUMMARY_METADATA_FIELDS,
  '该研究要解决什么问题',
  '目前最好的方法存在哪些不足',
  '为什么这个问题重要',
  '数据集（全称）',
  '数据集规模',
  'Baseline 方法（全称）',
  'Baseline方法（全称）',
  '评估指标',
];

function escapeSummaryHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderSummaryInline(value) {
  return escapeSummaryHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+?)\*/g, '<em>$1</em>')
    .replace(
      /https?:\/\/[^\s<，。；、）》）\]]+/g,
      url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`,
    );
}

function normalizeSummaryText(text) {
  let normalized = String(text).replace(/\r\n?/g, '\n').trim();
  // 兼容旧总结中被模型合并到同一物理行的固定字段。
  SUMMARY_BREAK_FIELDS.forEach(field => {
    const escapedField = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    normalized = normalized.replace(
      // 不拆分标准 Markdown 列表中的 "- 字段：内容" 和 "* 字段：内容"。
      new RegExp(`([^\\n*-])\\s+(?=${escapedField}[：:])`, 'g'),
      '$1\n',
    );
  });
  return normalized;
}

function splitSummaryField(value, metadataOnly = false) {
  const match = value.match(/^(.{1,48}?)[：:]\s*(.+)$/);
  if (!match) return null;
  const label = match[1].replace(/\*\*/g, '').trim();
  if (metadataOnly && !SUMMARY_METADATA_FIELDS.has(label)) return null;
  if (!metadataOnly && /[。！？；]/.test(label)) return null;
  return { label, content: match[2].trim() };
}

function renderSummary(text) {
  if (!text) return '<p>暂无总结</p>';
  const lines = normalizeSummaryText(text).split('\n');
  const html = ['<div class="summary-document">'];
  let sectionOpen = false;
  let sectionKind = '';
  let listTag = '';

  const closeList = () => {
    if (!listTag) return;
    html.push(`</${listTag}>`);
    listTag = '';
  };
  const closeSection = () => {
    if (!sectionOpen) return;
    closeList();
    html.push('</div></section>');
    sectionOpen = false;
    sectionKind = '';
  };
  const openList = tag => {
    if (listTag === tag) return;
    closeList();
    listTag = tag;
    html.push(`<${tag} class="summary-list">`);
  };

  lines.forEach(rawLine => {
    const line = rawLine.trim().replace(/\s{2,}$/, '');
    if (!line) {
      closeList();
      return;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      closeList();
      const level = headingMatch[1].length;
      const heading = headingMatch[2].trim();
      const isNumberedSubheading = level === 2 && /^\d+[.、]\s*/.test(heading) && sectionOpen;

      if (level === 2 && !isNumberedSubheading) {
        closeSection();
        sectionKind = /论文基本信息/.test(heading)
          ? 'metadata'
          : (/一句话总结/.test(heading) ? 'highlight' : '');
        const kindClass = sectionKind ? ` summary-section--${sectionKind}` : '';
        html.push(
          `<section class="summary-section${kindClass}">`,
          `<h2>${renderSummaryInline(heading)}</h2>`,
          '<div class="summary-section-body">',
        );
        sectionOpen = true;
        return;
      }

      if (level === 1) {
        closeSection();
        html.push(`<h1>${renderSummaryInline(heading)}</h1>`);
        return;
      }

      const insight = heading.match(/^(\d+[.、]\s*)?\*\*(.+?)\*\*[：:]\s*(.+)$/);
      if (insight) {
        html.push(
          '<div class="summary-insight">',
          `<h3>${renderSummaryInline(`${insight[1] || ''}${insight[2]}`)}</h3>`,
          `<p>${renderSummaryInline(insight[3])}</p>`,
          '</div>',
        );
      } else {
        html.push(`<h3>${renderSummaryInline(heading)}</h3>`);
      }
      return;
    }

    if (/^---+$/.test(line)) {
      closeList();
      html.push('<hr>');
      return;
    }

    const listMatch = line.match(/^[-*]\s+(.+)$/);
    const orderedMatch = line.match(/^\d+[.)、]\s+(.+)$/);
    if (listMatch || orderedMatch) {
      openList(orderedMatch ? 'ol' : 'ul');
      const content = (listMatch || orderedMatch)[1].trim();
      const field = splitSummaryField(content);
      if (field) {
        html.push(
          '<li class="summary-list-field">',
          `<strong class="summary-field-label">${renderSummaryInline(field.label)}：</strong>`,
          `<span>${renderSummaryInline(field.content)}</span>`,
          '</li>',
        );
      } else {
        html.push(`<li>${renderSummaryInline(content)}</li>`);
      }
      return;
    }

    closeList();
    const field = splitSummaryField(line, sectionKind === 'metadata');
    if (field) {
      html.push(
        '<div class="summary-field">',
        `<strong class="summary-field-label">${renderSummaryInline(field.label)}</strong>`,
        `<div class="summary-field-value">${renderSummaryInline(field.content)}</div>`,
        '</div>',
      );
      return;
    }

    html.push(`<p>${renderSummaryInline(line)}</p>`);
  });

  closeSection();
  closeList();
  html.push('</div>');
  return html.join('\n');
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
