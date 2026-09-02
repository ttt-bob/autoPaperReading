const landingAuth = (() => {
  const loginButton = document.querySelector('#landingLoginButton');
  const account = document.querySelector('#landingAccount');
  const accountEmail = document.querySelector('#landingAccountEmail');
  const logoutButton = document.querySelector('#landingLogoutButton');
  const overlay = document.querySelector('#landingAuthOverlay');
  const closeButton = document.querySelector('#landingAuthClose');
  const title = document.querySelector('#landingAuthTitle');
  const body = document.querySelector('#landingAuthBody');
  const toast = document.querySelector('#landingToast');

  let config = { emailVerification: false, passwordReset: false, githubLogin: false };
  let currentUser = null;
  let apiAvailable = false;
  let toastTimer;

  async function apiFetch(path, options = {}) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || '请求失败，请稍后重试');
      error.code = payload.code;
      throw error;
    }
    return payload;
  }

  function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = String(value || '');
    return element.innerHTML;
  }

  function showToast(message, type = 'success') {
    toast.textContent = message;
    toast.className = `landing-toast landing-toast--${type} landing-toast--visible`;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toast.classList.remove('landing-toast--visible');
    }, 3200);
  }

  function maskAccountIdentifier(value) {
    const characters = Array.from(String(value || ''));
    if (characters.length <= 2) return '*'.repeat(characters.length);
    if (characters.length <= 6) {
      return `${characters[0]}***${characters.at(-1)}`;
    }
    return `${characters.slice(0, 3).join('')}***${characters.slice(-3).join('')}`;
  }

  function updateAccountUi() {
    loginButton.hidden = Boolean(currentUser);
    account.hidden = !currentUser;
    accountEmail.textContent = maskAccountIdentifier(currentUser?.email);
  }

  function githubButton(dividerText) {
    if (!config.githubLogin) return '';
    return `
      <a class="landing-auth-github" href="api/auth/github/start">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M12 .7a11.5 11.5 0 0 0-3.64 22.4c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.52-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.27 3.38.97.1-.75.4-1.27.74-1.56-2.57-.3-5.27-1.29-5.27-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.47.11-3.06 0 0 .97-.31 3.16 1.18a10.96 10.96 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.59.23 2.77.11 3.06.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.39-5.28 5.68.42.36.79 1.07.79 2.16v3.2c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z"></path>
        </svg>
        <span>使用 GitHub 直接登录</span>
      </a>
      <div class="landing-auth-divider"><span>${dividerText}</span></div>`;
  }

  function emailField(email = '') {
    return `
      <label class="landing-auth-field">邮箱
        <input name="email" type="email" autocomplete="email" required value="${escapeHtml(email)}" placeholder="name@example.com">
      </label>`;
  }

  function passwordField(name = 'password', label = '密码', autocomplete = 'current-password') {
    return `
      <label class="landing-auth-field">${label}
        <input name="${name}" type="password" autocomplete="${autocomplete}" required minlength="8" placeholder="至少 8 个字符">
      </label>`;
  }

  function render(mode = 'login', email = '') {
    if (mode === 'register') {
      title.textContent = '创建账户';
      body.innerHTML = `
        <p class="landing-auth-note">可以使用 GitHub 直接进入，也可以通过邮箱创建账户。</p>
        ${githubButton('或使用邮箱注册')}
        <form class="landing-auth-form" data-auth-form="register">
          ${emailField(email)}
          ${passwordField('password', '设置密码', 'new-password')}
          ${passwordField('passwordConfirm', '确认密码', 'new-password')}
          <button class="landing-auth-submit" type="submit">注册并继续</button>
        </form>
        <p class="landing-auth-switch">已有账户？<button type="button" data-auth-mode="login">返回登录</button></p>`;
    } else if (mode === 'verify') {
      title.textContent = '验证邮箱';
      body.innerHTML = `
        <p class="landing-auth-note">验证码已发送至 <strong>${escapeHtml(email)}</strong>，有效期 15 分钟。</p>
        <form class="landing-auth-form" data-auth-form="verify">
          ${emailField(email)}
          <label class="landing-auth-field">6 位验证码
            <input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" required placeholder="000000">
          </label>
          <button class="landing-auth-submit" type="submit">验证并登录</button>
        </form>
        <p class="landing-auth-switch">没收到？<button type="button" data-auth-action="resend">重新发送验证码</button></p>`;
    } else if (mode === 'reset-request') {
      title.textContent = '找回密码';
      const hint = config.passwordReset
        ? '我们会向你的邮箱发送 6 位验证码。'
        : '邮件服务暂未配置，当前无法通过邮箱找回密码。';
      body.innerHTML = `
        <p class="landing-auth-note">${hint}</p>
        <form class="landing-auth-form" data-auth-form="reset-request">
          ${emailField(email)}
          <button class="landing-auth-submit" type="submit" ${config.passwordReset ? '' : 'disabled'}>发送验证码</button>
        </form>
        <p class="landing-auth-switch"><button type="button" data-auth-mode="login">返回登录</button></p>`;
    } else if (mode === 'reset-confirm') {
      title.textContent = '设置新密码';
      body.innerHTML = `
        <p class="landing-auth-note">输入邮箱验证码和新密码。</p>
        <form class="landing-auth-form" data-auth-form="reset-confirm">
          ${emailField(email)}
          <label class="landing-auth-field">6 位验证码
            <input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" required placeholder="000000">
          </label>
          ${passwordField('password', '新密码', 'new-password')}
          ${passwordField('passwordConfirm', '确认新密码', 'new-password')}
          <button class="landing-auth-submit" type="submit">更新密码</button>
        </form>`;
    } else {
      title.textContent = '登录或注册';
      body.innerHTML = `
        <p class="landing-auth-note">登录后即可保存私有收藏和自定义标签。</p>
        ${githubButton('或使用邮箱登录')}
        <form class="landing-auth-form" data-auth-form="login">
          ${emailField(email)}
          ${passwordField()}
          <button class="landing-auth-submit" type="submit">邮箱登录</button>
        </form>
        <p class="landing-auth-switch">
          <button type="button" data-auth-mode="register">创建账户</button>
          <span>·</span>
          <button type="button" data-auth-mode="reset-request">忘记密码</button>
        </p>`;
    }
    body.querySelector('input')?.focus();
  }

  function open(mode = 'login') {
    if (!apiAvailable) {
      showToast('账户服务暂时不可用，请稍后重试', 'error');
      return;
    }
    render(mode);
    overlay.classList.add('landing-auth-overlay--active');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function close() {
    overlay.classList.remove('landing-auth-overlay--active');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    loginButton.focus();
  }

  async function finishLogin(user, message) {
    currentUser = user;
    updateAccountUi();
    close();
    showToast(message);
  }

  async function submitAuthForm(form) {
    const formData = new FormData(form);
    const mode = form.dataset.authForm;
    const email = String(formData.get('email') || '').trim();
    const password = String(formData.get('password') || '');
    const submitButton = form.querySelector('[type="submit"]');
    submitButton.disabled = true;

    try {
      if (mode === 'login') {
        const data = await apiFetch('api/auth/login', {
          method: 'POST', body: JSON.stringify({ email, password }),
        });
        await finishLogin(data.user, '登录成功');
      } else if (mode === 'register') {
        if (password !== formData.get('passwordConfirm')) throw new Error('两次输入的密码不一致');
        const data = await apiFetch('api/auth/register', {
          method: 'POST', body: JSON.stringify({ email, password }),
        });
        if (data.verificationRequired) {
          render('verify', data.email);
          showToast('验证码已发送，请检查邮箱');
        } else {
          await finishLogin(data.user, '账户已创建');
        }
      } else if (mode === 'verify') {
        const data = await apiFetch('api/auth/verify-email', {
          method: 'POST', body: JSON.stringify({ email, code: formData.get('code') }),
        });
        await finishLogin(data.user, '邮箱验证完成');
      } else if (mode === 'reset-request') {
        const data = await apiFetch('api/auth/password-reset/request', {
          method: 'POST', body: JSON.stringify({ email }),
        });
        showToast(data.message);
        render('reset-confirm', email);
      } else if (mode === 'reset-confirm') {
        if (password !== formData.get('passwordConfirm')) throw new Error('两次输入的密码不一致');
        await apiFetch('api/auth/password-reset/confirm', {
          method: 'POST',
          body: JSON.stringify({ email, code: formData.get('code'), password }),
        });
        showToast('密码已更新，请使用新密码登录');
        render('login', email);
      }
    } catch (error) {
      showToast(error.message, 'error');
      submitButton.disabled = false;
    }
  }

  async function resendVerification() {
    const email = body.querySelector('[name="email"]')?.value || '';
    try {
      const data = await apiFetch('api/auth/verification/resend', {
        method: 'POST', body: JSON.stringify({ email }),
      });
      showToast(data.message);
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  async function logout() {
    try {
      await apiFetch('api/auth/logout', { method: 'POST', body: JSON.stringify({}) });
    } catch (error) {
      console.info('Logout request did not complete.', error);
    }
    currentUser = null;
    updateAccountUi();
    showToast('已退出登录');
  }

  function bindEvents() {
    loginButton.addEventListener('click', () => open('login'));
    logoutButton.addEventListener('click', logout);
    closeButton.addEventListener('click', close);
    overlay.addEventListener('click', event => {
      if (event.target === overlay) close();
    });
    body.addEventListener('click', event => {
      const modeButton = event.target.closest('[data-auth-mode]');
      if (modeButton) render(modeButton.dataset.authMode);
      if (event.target.closest('[data-auth-action="resend"]')) resendVerification();
    });
    body.addEventListener('submit', event => {
      event.preventDefault();
      submitAuthForm(event.target);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && overlay.classList.contains('landing-auth-overlay--active')) close();
    });
  }

  async function initialize() {
    bindEvents();
    try {
      config = await apiFetch('api/config');
      apiAvailable = true;
      const data = await apiFetch('api/auth/me');
      currentUser = data.user;
    } catch (error) {
      console.info('Account API is unavailable for this static deployment.', error);
      apiAvailable = false;
      currentUser = null;
    }
    updateAccountUi();
    const pageUrl = new URL(window.location.href);
    if (pageUrl.searchParams.get('login') === '1' && !currentUser) {
      pageUrl.searchParams.delete('login');
      window.history.replaceState({}, '', `${pageUrl.pathname}${pageUrl.search}${pageUrl.hash}`);
      open('login');
    }
  }

  return { initialize };
})();

landingAuth.initialize();
