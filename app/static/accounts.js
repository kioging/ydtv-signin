const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const loginModal = document.getElementById("login-modal");
const loginMessage = document.getElementById("login-message");
const captchaBlock = document.getElementById("credential-captcha");
const captchaImage = document.getElementById("captcha-image");
const captchaAnswer = document.getElementById("captcha-answer");
let activeLoginType = "password";
let captchaId = "";

function showLoginMessage(state, message) {
  loginMessage.hidden = false;
  loginMessage.className = `auth-status ${state}`;
  loginMessage.textContent = message;
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      ...(options.headers || {}),
    },
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `HTTP ${response.status}`);
  }
  return payload;
}

async function refreshCaptcha() {
  captchaAnswer.value = "";
  captchaImage.removeAttribute("src");
  try {
    const data = await apiFetch("/dashboard/api/account-login/captcha");
    captchaId = data.captcha_id;
    captchaImage.src = data.image;
  } catch (error) {
    captchaId = "";
    showLoginMessage("error", error.message);
  }
}

function selectLoginType(type) {
  activeLoginType = type;
  document.querySelectorAll("[data-login-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.loginTab === type);
  });
  document.querySelectorAll("[data-login-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.loginPanel !== type;
  });
  captchaBlock.hidden = type === "wechat";
  document.getElementById("submit-account-login").hidden = type === "wechat";
}

function openWizard() {
  loginModal.hidden = false;
  loginMessage.hidden = true;
  selectLoginType(activeLoginType);
  if (activeLoginType !== "wechat" && !captchaId) refreshCaptcha();
}

function closeWizard() {
  loginModal.hidden = true;
}

async function sendCode(type) {
  const account = document.getElementById(`${type}-account`).value.trim();
  const captcha = captchaAnswer.value.trim();
  if (!captchaId || !captcha) {
    showLoginMessage("error", "请先填写图形验证码");
    return;
  }
  try {
    const result = await apiFetch("/dashboard/api/account-login/send-code", {
      method: "POST",
      body: JSON.stringify({
        type,
        account,
        captcha_id: captchaId,
        captcha_answer: captcha,
      }),
    });
    showLoginMessage("success", result.message || "验证码已发送");
  } catch (error) {
    showLoginMessage("error", error.message);
  }
}

async function submitCredentialLogin() {
  if (!document.getElementById("login-agreement").checked) {
    showLoginMessage("error", "请先同意用户协议和隐私政策");
    return;
  }
  const captcha = captchaAnswer.value.trim();
  if (!captchaId || !captcha) {
    showLoginMessage("error", "请先填写图形验证码");
    return;
  }
  let account = "";
  let password = "";
  let code = "";
  if (activeLoginType === "password") {
    account = document.getElementById("password-account").value.trim();
    password = document.getElementById("password-value").value;
  } else if (activeLoginType === "phone") {
    account = document.getElementById("phone-account").value.trim();
    code = document.getElementById("phone-code").value.trim();
  } else {
    account = document.getElementById("email-account").value.trim();
    code = document.getElementById("email-code").value.trim();
  }
  showLoginMessage("pending", "正在登录并验证账号…");
  try {
    const result = await apiFetch("/dashboard/api/account-login/login", {
      method: "POST",
      body: JSON.stringify({
        type: activeLoginType,
        account,
        password,
        code,
        captcha_id: captchaId,
        captcha_answer: captcha,
      }),
    });
    showLoginMessage("success", result.created ? `新账号 ${result.name} 已添加` : `账号 ${result.name} 已存在，凭证已更新`);
    setTimeout(() => window.location.reload(), 2200);
  } catch (error) {
    showLoginMessage("error", error.message);
    captchaId = "";
    refreshCaptcha();
  }
}

async function completeWeChatLogin() {
  const callback = document.getElementById("wechat-callback").value.trim();
  if (!callback) {
    showLoginMessage("error", "请粘贴微信登录后的最终回调地址");
    return;
  }
  showLoginMessage("pending", "正在导入微信登录结果…");
  try {
    const result = await apiFetch("/dashboard/api/account-login/wechat/callback", {
      method: "POST",
      body: JSON.stringify({ callback }),
    });
    showLoginMessage("success", result.created ? `新账号 ${result.name} 已添加` : `账号 ${result.name} 已存在，凭证已更新`);
    setTimeout(() => window.location.reload(), 2200);
  } catch (error) {
    showLoginMessage("error", error.message);
  }
}

document.getElementById("authorize-button").addEventListener("click", openWizard);
document.getElementById("cancel-account-login").addEventListener("click", closeWizard);
document.getElementById("close-account-login").addEventListener("click", closeWizard);
loginModal.addEventListener("click", (event) => {
  if (event.target === loginModal) closeWizard();
});
document.getElementById("refresh-captcha").addEventListener("click", refreshCaptcha);
document.getElementById("submit-account-login").addEventListener("click", submitCredentialLogin);
document.getElementById("send-phone-code").addEventListener("click", () => sendCode("phone"));
document.getElementById("send-email-code").addEventListener("click", () => sendCode("email"));
document.getElementById("complete-wechat-login").addEventListener("click", completeWeChatLogin);
document.querySelectorAll("[data-login-tab]").forEach((button) => {
  button.addEventListener("click", () => selectLoginType(button.dataset.loginTab));
});
document.querySelectorAll("[data-authorize]").forEach((button) => {
  button.addEventListener("click", openWizard);
});

document.querySelectorAll(".refresh-account-balance").forEach((button) => {
  button.addEventListener("click", async () => {
    const accountId = button.dataset.accountId;
    const balanceNode = document.querySelector(`[data-account-balance="${accountId}"]`);
    const expiryNode = document.querySelector(`[data-token-expiry="${accountId}"]`);
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "刷新中";
    try {
      const data = await apiFetch(`/dashboard/api/accounts/${encodeURIComponent(accountId)}/balance/refresh`, {
        method: "POST",
        body: "{}",
      });
      if (balanceNode) balanceNode.textContent = Number(data.balance).toFixed(2);
      if (expiryNode) expiryNode.textContent = `Token 有效期：${data.token_expires_at}`;
      button.textContent = "已刷新";
    } catch {
      button.textContent = "刷新失败";
    } finally {
      button.disabled = false;
      setTimeout(() => {
        button.textContent = originalText;
      }, 1800);
    }
  });
});

document.querySelectorAll(".delete-account").forEach((button) => {
  button.addEventListener("click", async () => {
    const accountId = button.dataset.accountId;
    const confirmed = window.confirm(`确定删除账号 ${accountId}？历史记录会保留。`);
    if (!confirmed) return;
    button.disabled = true;
    button.textContent = "删除中";
    try {
      await apiFetch(`/dashboard/api/accounts/${encodeURIComponent(accountId)}/delete`, {
        method: "POST",
        body: "{}",
      });
      window.location.reload();
    } catch (error) {
      button.disabled = false;
      button.textContent = "删除失败";
      window.alert(error.message);
    }
  });
});
