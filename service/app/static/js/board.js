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

  function renderMeta(el) {
    const meta = el.querySelector(".meta");
    const p = parseInt(el.dataset.priority || "2", 10);
    const due = el.dataset.due;
    const labels = (el.dataset.labels || "").split(",").map(s => s.trim()).filter(Boolean);
    let html = "";
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

  document.getElementById("new-project").addEventListener("click", async () => {
    const name = prompt("Project name:");
    if (!name || !name.trim()) return;
    try {
      const p = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: name.trim() }) });
      window.location.href = `/project/${p.id}`;
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

  /* ---- init ---- */

  document.querySelectorAll("#board .card").forEach(renderMeta);
  updateCounts();
  refreshToday();
})();
