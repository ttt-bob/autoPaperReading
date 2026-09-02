const accessElement = document.querySelector('#accessState');
const workspaceElement = document.querySelector('#submissionWorkspace');
const formElement = document.querySelector('#submissionForm');
const submitButton = document.querySelector('#submitButton');
const listElement = document.querySelector('#submissionList');
const emptyElement = document.querySelector('#submissionEmpty');
const paperUrlInput = document.querySelector('#paperUrlInput');
const prefillNotice = document.querySelector('#prefillNotice');

const stageProgress = {
  queued: 4,
  starting: 10,
  metadata: 22,
  downloading: 36,
  parsing: 50,
  summarizing: 68,
  exporting: 82,
  publishing: 93,
  completed: 100,
  failed: 100,
};

const statusText = {
  queued: '等待中',
  running: '处理中',
  completed: '已上线',
  failed: '失败',
};

let pollTimer;
let submissionAllowed = false;

function initializePrefill() {
  const value = new URLSearchParams(window.location.search).get('url')?.trim() || '';
  if (!value || value.length > 2000) return;
  const isArxivId = /^\d{4}\.\d{4,5}(?:v\d+)?$/i.test(value);
  let isHttpUrl = false;
  try {
    isHttpUrl = ['http:', 'https:'].includes(new URL(value).protocol);
  } catch {
    isHttpUrl = false;
  }
  if (!isArxivId && !isHttpUrl) return;
  paperUrlInput.value = value;
  prefillNotice.hidden = false;
}

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
    error.paperId = payload.paperId;
    error.paperTitle = payload.paperTitle;
    throw error;
  }
  return payload;
}

function showAccessMessage(title, message, actionLabel = '', actionUrl = '') {
  accessElement.classList.remove('submission-access--notice');
  accessElement.replaceChildren();
  const heading = document.createElement('h2');
  const description = document.createElement('p');
  heading.textContent = title;
  description.textContent = message;
  accessElement.append(heading, description);
  if (actionLabel && actionUrl) {
    const link = document.createElement('a');
    link.href = actionUrl;
    link.textContent = actionLabel;
    accessElement.append(link);
  }
  accessElement.hidden = false;
  workspaceElement.hidden = true;
}

function showLoginRequired() {
  submissionAllowed = false;
  showAccessMessage(
    '请先登录或注册',
    '你仍可浏览全部论文和总结；登录后才能提交自己的论文进行处理。',
    '前往首页登录 / 注册',
    'index.html?login=1',
  );
  accessElement.classList.add('submission-access--notice');
  workspaceElement.hidden = false;
  submitButton.disabled = true;
  submitButton.textContent = '登录后才能提交';
  listElement.replaceChildren();
  emptyElement.hidden = false;
  emptyElement.textContent = '登录后可查看自己的处理记录';
}

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function buildSubmissionItem(task) {
  const item = document.createElement('article');
  const top = document.createElement('div');
  const title = document.createElement('h3');
  const status = document.createElement('span');
  const progress = document.createElement('div');
  const progressValue = document.createElement('span');
  const message = document.createElement('p');
  const meta = document.createElement('div');
  const time = document.createElement('span');

  item.className = 'submission-item';
  top.className = 'submission-item-top';
  title.textContent = task.title;
  status.className = `submission-status submission-status--${task.status}`;
  status.textContent = statusText[task.status] || task.status;
  progress.className = 'submission-progress';
  progressValue.style.setProperty('--progress', `${stageProgress[task.stage] || 4}%`);
  message.className = 'submission-item-message';
  message.textContent = task.message || '等待处理';
  meta.className = 'submission-item-meta';
  time.textContent = `提交于 ${formatTime(task.createdAt)}`;

  top.append(title, status);
  progress.append(progressValue);
  meta.append(time);
  item.append(top, progress, message);

  if (task.error) {
    const error = document.createElement('p');
    error.className = 'submission-item-error';
    error.textContent = task.error;
    item.append(error);
  }

  if (task.status === 'completed' && task.paperId) {
    const detailLink = document.createElement('a');
    detailLink.className = 'submission-detail-link';
    detailLink.href = `paper.html?id=${encodeURIComponent(task.paperId)}`;
    detailLink.textContent = '查看论文总结 →';
    meta.append(detailLink);
  }
  item.append(meta);
  return item;
}

function renderSubmissions(submissions) {
  listElement.replaceChildren(...submissions.map(buildSubmissionItem));
  emptyElement.hidden = submissions.length > 0;
  const hasActiveTask = submissions.some(task => ['queued', 'running'].includes(task.status));
  window.clearTimeout(pollTimer);
  if (hasActiveTask) pollTimer = window.setTimeout(loadSubmissions, 2000);
}

async function loadSubmissions() {
  try {
    const data = await apiFetch('api/paper-submissions');
    renderSubmissions(data.submissions || []);
  } catch (error) {
    window.clearTimeout(pollTimer);
    if (error.code === 'login_required') showLoginRequired();
    else showAccessMessage('暂时无法读取任务', error.message);
  }
}

async function initializePage() {
  try {
    const auth = await apiFetch('api/auth/me');
    if (!auth.user || !auth.permissions?.submitPapers) {
      showLoginRequired();
      return;
    }
    submissionAllowed = true;
    accessElement.hidden = true;
    workspaceElement.hidden = false;
    submitButton.disabled = false;
    submitButton.textContent = '确认并开始下载总结';
    await loadSubmissions();
  } catch (error) {
    showAccessMessage('服务暂时不可用', error.message);
  }
}

formElement.addEventListener('submit', async event => {
  event.preventDefault();
  if (!submissionAllowed) {
    showLoginRequired();
    return;
  }
  submitButton.disabled = true;
  submitButton.textContent = '正在提交…';
  try {
    await apiFetch('api/paper-submissions', {
      method: 'POST',
      body: JSON.stringify({
        url: paperUrlInput.value,
      }),
    });
    formElement.reset();
    await loadSubmissions();
  } catch (error) {
    if (error.code === 'duplicate_paper' && error.paperId) {
      const openExisting = window.confirm(`${error.message}\n\n点击“确定”查看已有总结。`);
      if (openExisting) {
        window.location.href = `paper.html?id=${encodeURIComponent(error.paperId)}`;
      }
    } else if (error.code === 'login_required') {
      showLoginRequired();
    } else {
      window.alert(error.message);
    }
  } finally {
    submitButton.disabled = !submissionAllowed;
    submitButton.textContent = submissionAllowed ? '确认并开始下载总结' : '登录后才能提交';
  }
});

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && !workspaceElement.hidden) loadSubmissions();
});

initializePrefill();
initializePage();
