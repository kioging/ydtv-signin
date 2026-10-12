const statusBox = document.getElementById("auth-status");
let activeFlow = null;
let pollStartedAt = 0;

async function startAuthorization(accountId, label) {
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const response = await fetch("/dashboard/api/auth/start", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ account_id: accountId || "", label: label || "" }),
  });
  if (!response.ok) {
    showStatus("error", "授权请求失败");
    return;
  }
  const data = await response.json();
  activeFlow = data.flow_id;
  pollStartedAt = Date.now();
  showStatus("pending", "等待登录完成");
  pollStatus();
}

async function pollStatus() {
  if (!activeFlow) return;
  if (Date.now() - pollStartedAt > 600000) {
    showStatus("error", "授权状态等待超时");
    activeFlow = null;
    return;
  }
  const response = await fetch(`/dashboard/api/auth/status/${activeFlow}`);
  if (!response.ok) {
    showStatus("error", "授权状态已失效");
    activeFlow = null;
    return;
  }
  const data = await response.json();
  if (data.state === "success") {
    showStatus("success", data.message);
    setTimeout(() => window.location.reload(), 2500);
    return;
  }
  if (data.state === "failed" || data.state === "timeout") {
    showStatus("error", data.message);
    activeFlow = null;
    return;
  }
  showStatus("pending", data.message);
  setTimeout(pollStatus, 1500);
}

function showStatus(state, message) {
  if (!statusBox) return;
  statusBox.hidden = false;
  statusBox.className = `auth-status ${state}`;
  statusBox.textContent = message;
}

const authorizeButton = document.getElementById("authorize-button");
if (authorizeButton) {
  authorizeButton.addEventListener("click", async () => {
    await startAuthorization("", "");
  });
}

document.querySelectorAll("[data-authorize]").forEach((button) => {
  button.addEventListener("click", async () => {
    await startAuthorization(button.dataset.authorize, button.dataset.label);
  });
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
      const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
      const response = await fetch(`/dashboard/api/accounts/${encodeURIComponent(accountId)}/balance/refresh`, {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
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
