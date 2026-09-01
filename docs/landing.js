const form = document.querySelector('#paperSearchForm');
const input = document.querySelector('#paperSearchInput');
const resultsElement = document.querySelector('#searchResults');
const statusElement = document.querySelector('#searchStatus');

let papers = [];
let searchTimer;
let canvasNest;

const darkMode = window.matchMedia('(prefers-color-scheme: dark)');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

function updateCanvasEffect() {
  canvasNest?.destroy();
  canvasNest = undefined;

  const effect = document.querySelector('#landingEffect');
  if (!effect || reducedMotion.matches || typeof window.CanvasNest !== 'function') return;

  const color = darkMode.matches ? '94,230,168' : '11,110,79';
  canvasNest = new window.CanvasNest(effect, {
    color,
    pointColor: color,
    opacity: darkMode.matches ? 0.24 : 0.22,
    count: window.innerWidth < 600 ? 42 : 72,
    zIndex: 0,
  });
}

function normalize(value) {
  return String(value || '').toLocaleLowerCase().replace(/[\s，,。；;：:、/_-]+/g, '');
}

function paperScore(paper, rawQuery) {
  const query = normalize(rawQuery);
  if (!query) return 0;
  const title = normalize(paper.title);
  const authors = normalize(paper.authors);
  const tags = normalize(paper.tags);
  const details = normalize(`${paper.intro || ''} ${paper.abstract || ''} ${paper.summary || ''}`);
  const tokens = rawQuery.split(/[\s，,。；;：:、/_-]+/).filter(Boolean).map(normalize);
  let score = 0;

  if (title === query) score += 1000;
  if (title.includes(query)) score += 500;
  if (tags.includes(query)) score += 320;
  if (authors.includes(query)) score += 240;
  if (details.includes(query)) score += 100;
  tokens.forEach(token => {
    if (title.includes(token)) score += 80;
    if (tags.includes(token)) score += 45;
    if (details.includes(token)) score += 15;
  });
  return score;
}

function clearResults() {
  resultsElement.replaceChildren();
  statusElement.textContent = '';
}

function buildResult(paper, query) {
  const link = document.createElement('a');
  const content = document.createElement('div');
  const meta = document.createElement('div');
  const title = document.createElement('h2');
  const summary = document.createElement('p');
  const open = document.createElement('span');

  link.className = 'search-result';
  link.href = paper.paper_id
    ? `paper.html?id=${encodeURIComponent(paper.paper_id)}`
    : `papers.html?q=${encodeURIComponent(paper.title || query)}`;
  content.className = 'search-result__content';
  meta.className = 'search-result__meta';
  title.textContent = paper.title || '未命名论文';
  summary.textContent = paper.intro || paper.abstract || paper.summary || '进入论文主页查看详情';
  open.className = 'search-result__open';
  open.textContent = '查看 →';

  const date = document.createElement('span');
  date.textContent = (paper.published || '').slice(0, 10) || '论文';
  meta.append(date);
  if (paper.tags) {
    const tag = document.createElement('span');
    tag.textContent = paper.tags.split(',').slice(0, 2).join(' · ');
    meta.append(tag);
  }

  content.append(meta, title, summary);
  link.append(content, open);
  return link;
}

function renderResults() {
  const query = input.value.trim();
  if (!query) {
    clearResults();
    return;
  }
  if (!papers.length) {
    statusElement.textContent = '论文数据加载中…';
    return;
  }

  const matches = papers
    .map(paper => ({ paper, score: paperScore(paper, query) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 8);

  resultsElement.replaceChildren(...matches.map(item => buildResult(item.paper, query)));
  statusElement.textContent = matches.length
    ? `找到 ${matches.length} 个优先结果，按 Enter 查看全部匹配`
    : '没有找到相关论文，可以换一个关键词试试';
}

form.addEventListener('submit', event => {
  event.preventDefault();
  const query = input.value.trim();
  if (query) window.location.href = `papers.html?q=${encodeURIComponent(query)}`;
});

input.addEventListener('input', () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(renderResults, 120);
});

darkMode.addEventListener('change', updateCanvasEffect);
reducedMotion.addEventListener('change', updateCanvasEffect);
updateCanvasEffect();

fetch('paper-data/search-index.json')
  .then(response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then(data => {
    papers = Array.isArray(data) ? data : (data.papers || []);
    renderResults();
  })
  .catch(() => {
    papers = [];
    if (input.value.trim()) statusElement.textContent = '暂时无法加载论文数据，请进入论文主页搜索';
  });
