/* Board page: drag and drop via SortableJS, card dialog, Today rail. */
(function () {
  "use strict";

  const projectId = window.BOARD.projectId;
  const dialog = document.getElementById("card-dialog");
  const form = document.getElementById("card-form");
  let dialogColumnId = null;

  async function api(path, options) {
    const opts = Object.assign({ headers: { "Content-Type": "application/json" } }, options);
    const resp = await fetch(path, opts);
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (e) { /* ignore */ }
      throw new Error(detail);
    }
    if (resp.status === 204) return null;
    return resp.json();
  }

  function esc(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function checklistItems(text) {
    const items = [];
    (text || "").split("\n").forEach(line => {
      const m = line.match(/^\s*[-*]\s*\[( |x|X)\]\s*(.*)$/);
      if (m) items.push({ checked: m[1] !== " ", text: m[2] });
    });
    return items;
  }

  function renderMeta(el) {
    const meta = el.querySelector(".meta");
    const p = parseInt(el.dataset.priority || "2", 10);
    const due = el.dataset.due;
    const labels = (el.dataset.labels || "").split(",").map(s => s.trim()).filter(Boolean);
    let html = "";
    const total = parseInt(el.dataset.checkTotal || "0", 10);
    if (total) {
      const done = parseInt(el.dataset.checkDone || "0", 10);
      html += `<span class="chip ${done === total ? "check-full" : ""}">&#9745; ${done}/${total}</span>`;
    }
    if (p !== 2) html += `<span class="chip p${p}">P${p}</span>`;
    if (due) {
      const overdue = due < new Date().toISOString().slice(0, 10);
      html += `<span class="chip due ${overdue ? "overdue" : ""}">${esc(due)}</span>`;
    }
    labels.forEach(l => { html += `<span class="chip">${esc(l)}</span>`; });
    meta.innerHTML = html;
    meta.style.display = html ? "" : "none";
  }

  function updateCounts() {
    document.querySelectorAll("#board .column").forEach(col => {
      const n = col.querySelectorAll(".card").length;
      col.querySelector(".count").textContent = n ? String(n) : "";
    });
  }

  function cardEl(card) {
    const div = document.createElement("div");
    div.className = "card";
    div.dataset.cardId = card.id;
    div.dataset.title = card.title;
    div.dataset.priority = card.priority;
    div.dataset.due = card.due_date;
    div.dataset.labels = card.labels;
    const items = checklistItems(card.description);
    div.dataset.checkTotal = items.length;
    div.dataset.checkDone = items.filter(i => i.checked).length;
    div.innerHTML = '<div class="card-title"></div><div class="meta"></div>';
    div.querySelector(".card-title").textContent = card.title;
    renderMeta(div);
    return div;
  }

  function todayEl(card) {
    const div = cardEl(card);
    const from = document.createElement("div");
    from.className = "from";
    from.textContent = card.project_name + " · " + card.status;
    if (card.done) div.classList.add("done-card");
    div.appendChild(from);
    return div;
  }

  function markToday() {
    const ids = new Set([...document.querySelectorAll("#today-list .card")].map(el => el.dataset.cardId));
    document.querySelectorAll("#board .card").forEach(el => {
      el.classList.toggle("today", ids.has(el.dataset.cardId));
    });
  }

  async function refreshToday() {
    const tasks = await api("/api/today");
    const list = document.getElementById("today-list");
    list.innerHTML = "";
    tasks.forEach(t => list.appendChild(todayEl(t)));
    markToday();
  }

  /* ---- drag and drop ---- */

  function initColumnSortable(el) {
    new Sortable(el, {
      group: "cards",
      animation: 120,
      ghostClass: "sortable-ghost",
      onEnd: async (evt) => {
        const cardId = evt.item.dataset.cardId;
        const to = evt.to;
        try {
          if (to.dataset.today) {
            await api(`/api/cards/${cardId}/today`, {
              method: "POST",
              body: JSON.stringify({ today: true, position: evt.newIndex }),
            });
            await refreshToday();
            // The board keeps its own copy of the card; remove the dragged clone.
            if (evt.from !== to) {
              const clone = to.querySelector(`.card[data-card-id="${cardId}"]`);
              if (clone && !clone.querySelector(".from")) clone.remove();
              evt.from.insertBefore(evt.item, evt.from.children[evt.oldIndex] || null);
            }
          } else if (evt.from.dataset.today) {
            // Dragging out of Today removes it from the list.
            await api(`/api/cards/${cardId}/today`, { method: "POST", body: JSON.stringify({ today: false }) });
            evt.item.remove();
            await refreshToday();
          } else {
            await api(`/api/cards/${cardId}/move`, {
              method: "POST",
              body: JSON.stringify({ column_id: parseInt(to.dataset.columnId, 10), position: evt.newIndex }),
            });
          }
        } catch (err) {
          alert("Move failed: " + err.message);
          window.location.reload();
          return;
        }
        updateCounts();
        markToday();
      },
    });
  }

  document.querySelectorAll("#board .cards").forEach(initColumnSortable);
  initColumnSortable(document.getElementById("today-list"));

  new Sortable(document.getElementById("board"), {
    animation: 120,
    handle: ".column-header",
    draggable: ".column",
    onEnd: async (evt) => {
      const columnId = evt.item.dataset.columnId;
      try {
        await api(`/api/columns/${columnId}`, {
          method: "PATCH",
          body: JSON.stringify({ position: evt.newIndex }),
        });
      } catch (err) {
        alert("Reorder failed: " + err.message);
        window.location.reload();
      }
    },
  });

  /* ---- card dialog ---- */

  function renderDialogChecklist() {
    const box = document.getElementById("checklist-box");
    const wrap = document.getElementById("checklist-items");
    const cardId = form.card_id.value;
    const items = checklistItems(form.description.value);
    box.hidden = !cardId || items.length === 0;
    wrap.innerHTML = "";
    items.forEach((item, i) => {
      const label = document.createElement("label");
      label.className = "checklist-item";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = item.checked;
      input.addEventListener("change", async () => {
        try {
          const card = await api(`/api/cards/${cardId}/checklist`, {
            method: "POST",
            body: JSON.stringify({ index: i, checked: input.checked }),
          });
          form.description.value = card.description;
          syncCardChecklist(card);
          renderDialogChecklist();
        } catch (err) {
          input.checked = !input.checked;
          alert(err.message);
        }
      });
      const span = document.createElement("span");
      span.textContent = item.text;
      if (item.checked) span.style.textDecoration = "line-through";
      label.append(input, span);
      wrap.appendChild(label);
    });
  }

  function syncCardChecklist(card) {
    const el = document.querySelector(`#board .card[data-card-id="${card.id}"]`);
    if (!el) return;
    const items = checklistItems(card.description);
    el.dataset.checkTotal = items.length;
    el.dataset.checkDone = items.filter(i => i.checked).length;
    renderMeta(el);
  }

  function openCardDialog(card, columnId) {
    dialogColumnId = columnId;
    form.card_id.value = card ? card.id : "";
    form.title.value = card ? card.title : "";
    form.description.value = card ? card.description : "";
    form.priority.value = card ? String(card.priority) : "2";
    form.due_date.value = card ? card.due_date : "";
    form.labels.value = card ? card.labels : "";
    document.getElementById("card-delete").hidden = !card;
    document.getElementById("assist-actions").hidden = !(card && window.BOARD.aiConfigured);
    document.getElementById("assist-note").textContent = "";
    renderDialogChecklist();
    dialog.showModal();
  }

  document.querySelectorAll(".add-card-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      openCardDialog(null, parseInt(btn.closest(".column").dataset.columnId, 10));
    });
  });

  document.getElementById("board").addEventListener("click", async (e) => {
    const el = e.target.closest(".card");
    if (!el || e.target.closest(".col-menu")) return;
    try {
      const card = await api(`/api/cards/${el.dataset.cardId}`);
      openCardDialog(card, card.column_id);
    } catch (err) { alert(err.message); }
  });

  document.getElementById("today-list").addEventListener("click", async (e) => {
    const el = e.target.closest(".card");
    if (!el) return;
    try {
      const card = await api(`/api/cards/${el.dataset.cardId}`);
      openCardDialog(card, card.column_id);
    } catch (err) { alert(err.message); }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      title: form.title.value.trim(),
      description: form.description.value,
      priority: parseInt(form.priority.value, 10),
      due_date: form.due_date.value,
      labels: form.labels.value,
    };
    if (!body.title) return;
    try {
      if (form.card_id.value) {
        const card = await api(`/api/cards/${form.card_id.value}`, { method: "PATCH", body: JSON.stringify(body) });
        const el = document.querySelector(`#board .card[data-card-id="${card.id}"]`);
        if (el) {
          el.dataset.title = card.title;
          el.dataset.priority = card.priority;
          el.dataset.due = card.due_date;
          el.dataset.labels = card.labels;
          el.querySelector(".card-title").textContent = card.title;
          syncCardChecklist(card);
          renderMeta(el);
        }
        await refreshToday();
      } else {
        const card = await api("/api/cards", {
          method: "POST",
          body: JSON.stringify(Object.assign({ project_id: projectId, column_id: dialogColumnId }, body)),
        });
        document.querySelector(`#board .cards[data-column-id="${dialogColumnId}"]`).appendChild(cardEl(card));
      }
      dialog.close();
      updateCounts();
    } catch (err) { alert("Save failed: " + err.message); }
  });

  document.getElementById("card-cancel").addEventListener("click", () => dialog.close());

  document.getElementById("card-delete").addEventListener("click", async () => {
    const id = form.card_id.value;
    if (!id || !confirm("Delete this card?")) return;
    try {
      await api(`/api/cards/${id}`, { method: "DELETE" });
      document.querySelectorAll(`.card[data-card-id="${id}"]`).forEach(el => el.remove());
      dialog.close();
      updateCounts();
    } catch (err) { alert(err.message); }
  });

  /* ---- AI assist ---- */

  async function assist(kind) {
    const id = form.card_id.value;
    if (!id) return;
    const note = document.getElementById("assist-note");
    note.textContent = "Thinking...";
    try {
      const data = await api(`/api/assist/${kind}`, { method: "POST", body: JSON.stringify({ card_id: parseInt(id, 10) }) });
      form.description.value = data.card.description;
      syncCardChecklist(data.card);
      renderDialogChecklist();
      note.textContent = "Done. Review and save.";
    } catch (err) {
      note.textContent = err.message;
    }
  }
  document.getElementById("assist-subtasks").addEventListener("click", () => assist("subtasks"));
  document.getElementById("assist-describe").addEventListener("click", () => assist("describe"));

  /* ---- columns ---- */

  document.getElementById("add-column").addEventListener("click", async () => {
    const name = prompt("Status name:");
    if (!name || !name.trim()) return;
    try {
      await api(`/api/projects/${projectId}/columns`, { method: "POST", body: JSON.stringify({ name: name.trim() }) });
      window.location.reload();
    } catch (err) { alert(err.message); }
  });

  document.querySelectorAll(".col-menu").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const col = btn.closest(".column");
      const columnId = col.dataset.columnId;
      const name = col.querySelector(".col-name").textContent;
      const choice = prompt(
        `Column "${name}"\nType a new name to rename, "done" to toggle the finished flag, or "delete" to remove (must be empty):`
      );
      if (!choice) return;
      try {
        if (choice.trim().toLowerCase() === "delete") {
          await api(`/api/columns/${columnId}`, { method: "DELETE" });
        } else if (choice.trim().toLowerCase() === "done") {
          await api(`/api/columns/${columnId}`, { method: "PATCH", body: JSON.stringify({ is_done: !col.classList.contains("is-done") }) });
        } else {
          await api(`/api/columns/${columnId}`, { method: "PATCH", body: JSON.stringify({ name: choice.trim() }) });
        }
        window.location.reload();
      } catch (err) { alert(err.message); }
    });
  });

  /* ---- projects ---- */

  document.getElementById("project-select").addEventListener("change", (e) => {
    window.location.href = `/project/${e.target.value}`;
  });

  /* ---- squirrel discipline ---- */

  const NUDGE_LINES = [
    (p) => `Psst. "${p.name}" has ${p.open_cards} open card${p.open_cards > 1 ? "s" : ""} and hasn't moved in ${p.days_quiet} days. It misses you.`,
    (p) => `Remember "${p.name}"? ${p.open_cards} card${p.open_cards > 1 ? "s" : ""} still open, ${p.days_quiet} days of silence. Just saying.`,
    (p) => `That nut you buried, "${p.name}"? Still in the ground. ${p.open_cards} open card${p.open_cards > 1 ? "s" : ""}, quiet for ${p.days_quiet} days.`,
    (p) => `"${p.name}" called. It wants its ${p.open_cards} open card${p.open_cards > 1 ? "s" : ""} finished. (${p.days_quiet} days and counting.)`,
  ];

  async function squirrelNudge() {
    try {
      const stale = (await api(`/api/nudge?exclude=${projectId}`))
        .filter(p => p.days_quiet >= 3);
      if (!stale.length) return;
      const p = stale[0];
      if (sessionStorage.getItem("nudge-dismissed") === String(p.id)) return;
      const line = NUDGE_LINES[p.id % NUDGE_LINES.length](p);
      document.getElementById("nudge-text").innerHTML =
        `${line} <a href="/project/${p.id}">Go finish it</a>`;
      document.getElementById("squirrel-nudge").hidden = false;
      document.getElementById("nudge-dismiss").onclick = () => {
        sessionStorage.setItem("nudge-dismissed", String(p.id));
        document.getElementById("squirrel-nudge").hidden = true;
      };
    } catch (e) { /* no guilt today */ }
  }

  document.getElementById("new-project").addEventListener("click", async () => {
    try {
      const unfinished = await api("/api/nudge");
      if (unfinished.length) {
        const top = unfinished.slice(0, 3)
          .map(p => `  - ${p.name}: ${p.open_cards} open, quiet ${p.days_quiet}d`)
          .join("\n");
        const total = unfinished.reduce((n, p) => n + p.open_cards, 0);
        if (!confirm(
          `SQUIRREL! \u{1F43F}️\n\nEasy there. ${unfinished.length} project${unfinished.length > 1 ? "s" : ""} still ` +
          `${unfinished.length > 1 ? "have" : "has"} nuts in the ground (${total} open cards):\n\n${top}\n\n` +
          `Chase the new shiny thing anyway?`
        )) return;
      }
    } catch (e) { /* the nudge never blocks the work */ }
    const name = prompt("Project name:");
    if (!name || !name.trim()) return;
    try {
      const p = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: name.trim() }) });
      window.location.href = `/project/${p.id}`;
    } catch (err) { alert(err.message); }
  });

  document.getElementById("project-status").addEventListener("change", async (e) => {
    try {
      await api(`/api/projects/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: e.target.value }),
      });
      if (e.target.value === "cracked") {
        alert("\u{1F43F}️ Cracked it. Go start something new, guilt-free.");
      }
      window.location.reload();
    } catch (err) { alert(err.message); }
  });

  document.getElementById("rename-project").addEventListener("click", async () => {
    const name = prompt("New project name:");
    if (!name || !name.trim()) return;
    try {
      await api(`/api/projects/${projectId}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) });
      window.location.reload();
    } catch (err) { alert(err.message); }
  });

  document.getElementById("archive-project").addEventListener("click", async () => {
    if (!confirm("Archive this project? Its cards leave the board but nothing is deleted.")) return;
    try {
      await api(`/api/projects/${projectId}/archive`, { method: "POST" });
      window.location.href = "/";
    } catch (err) { alert(err.message); }
  });

  document.getElementById("clear-done-today").addEventListener("click", async () => {
    try {
      await api("/api/today/clear-done", { method: "POST" });
      await refreshToday();
    } catch (err) { alert(err.message); }
  });

  /* ---- Claude Code connect ---- */

  const claudeDialog = document.getElementById("claude-dialog");
  const claudeForm = document.getElementById("claude-form");

  document.getElementById("claude-connect").addEventListener("click", async () => {
    try {
      const data = await api("/api/connectors/claude-code");
      const select = claudeForm.claude_path;
      select.innerHTML = '<option value="">(disconnect)</option>';
      (data.known_paths || []).forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.path;
        opt.textContent = `${p.name} (${p.machine})`;
        select.appendChild(opt);
      });
      if (window.BOARD.claudePath) {
        if (![...select.options].some(o => o.value === window.BOARD.claudePath)) {
          const opt = document.createElement("option");
          opt.value = window.BOARD.claudePath;
          opt.textContent = window.BOARD.claudePath + " (not reporting)";
          select.appendChild(opt);
        }
        select.value = window.BOARD.claudePath;
      }
      claudeDialog.showModal();
    } catch (err) { alert(err.message); }
  });

  document.getElementById("claude-cancel").addEventListener("click", () => claudeDialog.close());

  claudeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api(`/api/projects/${projectId}/claude-link`, {
        method: "POST",
        body: JSON.stringify({ claude_path: claudeForm.claude_path.value }),
      });
      window.location.reload();
    } catch (err) { alert("Connect failed: " + err.message); }
  });

  /* ---- quick filter ---- */

  document.getElementById("quick-filter").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    document.querySelectorAll("#board .card").forEach(el => {
      const hay = (el.dataset.title + " " + el.dataset.labels).toLowerCase();
      el.style.display = !q || hay.includes(q) ? "" : "none";
    });
  });

  /* ---- init ---- */

  document.querySelectorAll("#board .card").forEach(renderMeta);
  updateCounts();
  refreshToday();
  squirrelNudge();
})();
