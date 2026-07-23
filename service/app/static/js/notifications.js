/* The notification bell: unread badge, dropdown inbox, mark read.
   All text goes through textContent, never innerHTML. */
(function () {
  "use strict";

  const bell = document.getElementById("notify-bell");
  const badge = document.getElementById("notify-badge");
  const panel = document.getElementById("notify-panel");
  const list = document.getElementById("notify-list");
  const markAll = document.getElementById("notify-mark-read");
  if (!bell || !badge || !panel || !list || !markAll) return;

  function setBadge(n) {
    badge.hidden = !n;
    badge.textContent = n > 99 ? "99+" : String(n);
  }

  async function refreshCount() {
    try {
      const resp = await fetch("/api/notifications?unread_only=true");
      if (!resp.ok) return;
      setBadge((await resp.json()).unread);
    } catch (e) { /* the next poll retries */ }
  }

  function render(items) {
    list.textContent = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "notify-empty";
      empty.textContent = "Nothing yet. Quiet is good.";
      list.appendChild(empty);
      return;
    }
    items.forEach((n) => {
      const row = document.createElement("a");
      row.className = "notify-item" + (n.read ? "" : " unread");
      row.href = n.url || "#";
      const text = document.createElement("div");
      text.textContent = n.text;
      const when = document.createElement("div");
      when.className = "notify-when";
      when.textContent = n.created_at || "";
      row.appendChild(text);
      row.appendChild(when);
      if (!n.read) {
        // Best effort on the way out; the navigation happens regardless.
        row.addEventListener("click", () => {
          fetch("/api/notifications/read", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: [n.id] }),
            keepalive: true,
          }).catch(() => {});
        });
      }
      list.appendChild(row);
    });
  }

  async function openPanel() {
    panel.hidden = false;
    try {
      const resp = await fetch("/api/notifications");
      if (!resp.ok) return;
      const data = await resp.json();
      setBadge(data.unread);
      render(data.items);
    } catch (e) { /* leave the panel as it was */ }
  }

  bell.addEventListener("click", (e) => {
    e.preventDefault();
    if (panel.hidden) openPanel();
    else panel.hidden = true;
  });

  document.addEventListener("click", (e) => {
    if (!panel.hidden && !panel.contains(e.target) && !bell.contains(e.target)) {
      panel.hidden = true;
    }
  });

  markAll.addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      const resp = await fetch("/api/notifications/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ all: true }),
      });
      if (!resp.ok) return;
      setBadge((await resp.json()).unread);
      list.querySelectorAll(".notify-item.unread").forEach((el) => {
        el.classList.remove("unread");
      });
    } catch (e) { /* nothing marked, the badge stays honest */ }
  });

  refreshCount();
  setInterval(refreshCount, 60000);
})();
