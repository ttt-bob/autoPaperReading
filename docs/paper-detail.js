const loadingElement = document.querySelector('#paperLoading');
const errorElement = document.querySelector('#paperError');
const articleElement = document.querySelector('#paperArticle');
const retryButton = document.querySelector('#retryButton');

const paperId = new URLSearchParams(window.location.search).get('id') || '';

function formatPaperDate(value) {
  if (!value) return '未知日期';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

function safeExternalUrl(value) {
  if (!value) return '';
  try {
    const url = new URL(value, window.location.href);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

function createAction(label, url, secondary = false) {
  const link = document.createElement('a');
  link.className = `paper-detail-button${secondary ? ' paper-detail-button--secondary' : ''}`;
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = `${label} ↗`;
  return link;
}

function showError(title, message, allowRetry = false) {
  loadingElement.hidden = true;
  articleElement.hidden = true;
  errorElement.hidden = false;
  document.querySelector('#paperErrorTitle').textContent = title;
  document.querySelector('#paperErrorMessage').textContent = message;
  retryButton.hidden = !allowRetry;
}

function updateDocumentMetadata(paper) {
  const title = paper.title || '论文详情';
  document.title = `${title} · AutoPaperReading`;
  const description = String(paper.abstract || paper.summary || 'AutoPaperReading 论文总结')
    .replace(/[#*`\n]+/g, ' ')
    .trim()
    .slice(0, 155);
  document.querySelector('meta[name="description"]').setAttribute('content', description);
}

function renderPaper(paper) {
  updateDocumentMetadata(paper);
  document.querySelector('#paperId').textContent = paper.paper_id || paperId;
  document.querySelector('#paperTitle').textContent = paper.title || '未命名论文';
  document.querySelector('#paperAuthors').textContent = paper.authors || '未知作者';
  const dateElement = document.querySelector('#paperDate');
  dateElement.textContent = formatPaperDate(paper.published);
  if (paper.published) dateElement.dateTime = paper.published;

  const affiliationsElement = document.querySelector('#paperAffiliations');
  if (paper.affiliations) {
    affiliationsElement.textContent = `机构 · ${paper.affiliations}`;
    affiliationsElement.hidden = false;
  }

  const tagsElement = document.querySelector('#paperTags');
  const tags = String(paper.tags || '').split(',').map(tag => tag.trim()).filter(Boolean);
  tags.forEach(tag => {
    const chip = document.createElement('span');
    chip.className = 'tag';
    chip.textContent = tag;
    tagsElement.append(chip);
  });

  const actionsElement = document.querySelector('#paperActions');
  const entryUrl = safeExternalUrl(paper.entry_url);
  const pdfUrl = safeExternalUrl(paper.pdf_url);
  const codeUrl = safeExternalUrl(paper.code_url);
  if (entryUrl) actionsElement.append(createAction('论文原页', entryUrl));
  if (pdfUrl) actionsElement.append(createAction('PDF', pdfUrl, true));
  if (codeUrl) actionsElement.append(createAction('开源代码', codeUrl, true));

  const abstractSection = document.querySelector('#paperAbstractSection');
  if (paper.abstract) {
    document.querySelector('#paperAbstract').textContent = paper.abstract;
    abstractSection.hidden = false;
  }

  document.querySelector('#paperSummary').innerHTML = window.AutoPaperSummary.render(
    paper.summary || '暂无总结',
  );
  loadingElement.hidden = true;
  errorElement.hidden = true;
  articleElement.hidden = false;

  typesetArticle();
}

function typesetArticle() {
  if (window.MathJax?.typesetPromise && !articleElement.hidden) {
    window.MathJax.typesetPromise([articleElement]).catch(console.warn);
  }
}

async function loadPaper() {
  if (!paperId) {
    showError('缺少论文 ID', '请从搜索首页或论文库选择一篇论文。');
    return;
  }
  if (!/^[A-Za-z0-9._-]{1,120}$/.test(paperId)) {
    showError('论文链接无效', '链接中的论文 ID 格式不正确，请返回搜索首页重新选择。');
    return;
  }

  loadingElement.hidden = false;
  errorElement.hidden = true;
  articleElement.hidden = true;
  try {
    const response = await fetch(`paper-data/details/${encodeURIComponent(paperId)}.json`);
    if (!response.ok) {
      if (response.status === 404) {
        showError('没有找到这篇论文', '该论文可能尚未生成总结，或链接已经失效。');
        return;
      }
      throw new Error(`HTTP ${response.status}`);
    }
    const detail = await response.json();
    let paper = detail;
    if (!detail.title) {
      const indexResponse = await fetch('paper-data/search-index.json');
      if (!indexResponse.ok) throw new Error(`index request failed: ${indexResponse.status}`);
      const indexData = await indexResponse.json();
      const indexPapers = Array.isArray(indexData) ? indexData : (indexData.papers || []);
      const metadata = indexPapers.find(item => item.paper_id === paperId);
      if (metadata) paper = { ...metadata, ...detail };
    }
    renderPaper(paper);
  } catch (error) {
    console.error('Load paper detail failed:', error);
    showError('论文详情加载失败', '网络暂时不可用，请稍后重新加载。', true);
  }
}

retryButton.addEventListener('click', loadPaper);
window.addEventListener('mathjax-ready', typesetArticle);
loadPaper();
