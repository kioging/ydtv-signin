document.querySelectorAll(".refresh-balance").forEach((button) => {
  button.addEventListener("click", async () => {
    const accountId = button.dataset.accountId;
    const balanceNode = document.querySelector(`[data-balance-for="${accountId}"]`);
    const updatedNode = document.querySelector(`[data-updated-for="${accountId}"]`);
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
      if (updatedNode) updatedNode.textContent = `上次更新：${data.updated_at}`;
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
