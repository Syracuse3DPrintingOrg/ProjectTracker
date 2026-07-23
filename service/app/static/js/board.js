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

  function localDateStr() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
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
    const att = parseInt(el.dataset.attachments || "0", 10);
    if (att) html += `<span class="chip" title="${att} file${att > 1 ? "s" : ""} attached">&#128206; ${att}</span>`;
    if (el.dataset.assignee) {
      const initials = el.dataset.assignee.slice(0, 2).toUpperCase();
      html += `<span class="chip assignee-chip" title="Assigned to ${esc(el.dataset.assignee)}">${esc(initials)}</span>`;
    }
    const recur = parseInt(el.dataset.recur || "0", 10);
    if (recur) html += `<span class="chip" title="Repeats every ${recur} day${recur > 1 ? "s" : ""}">&#8635; ${recur}d</span>`;
    if (p !== 2) html += `<span class="chip p${p}">P${p}</span>`;
    if (due) {
      const overdue = due < localDateStr();
      html += `<span class="chip due ${overdue ? "overdue" : ""}">${esc(due)}</span>`;
    }
    labels.forEach(l => { html += `<span class="chip">${esc(l)}</span>`; });
    meta.innerHTML = html;
    meta.style.display = html ? "" : "none";
  }

  function updateCounts() {
    document.querySelectorAll("#board .column").forEach(col => {
      const n = col.querySelectorAll(".card").length;
      const limit = parseInt(col.dataset.wip || "0", 10);
      const count = col.querySelector(".count");
      count.textContent = limit ? `${n}/${limit}` : (n ? String(n) : "");
      const over = limit && n > limit;
      col.classList.toggle("over-wip", !!over);
      count.title = over ? "Over the limit. The squirrel is judging you." : "";
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
    div.dataset.recur = card.recur_days || 0;
    div.dataset.attachments = card.attachments || 0;
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

  /* Whose Today list the rail shows: the shared one, or the signed-in
     user's personal one. The choice sticks per browser. */
  const listSelect = document.getElementById("today-list-select");
  let todayList = "shared";
  if (window.BOARD.userId && listSelect) {
    listSelect.hidden = false;
    const saved = localStorage.getItem("sq_today_list");
    if (saved === "mine" || saved === "shared") todayList = saved;
    listSelect.value = todayList;
    listSelect.addEventListener("change", async () => {
      todayList = listSelect.value;
      localStorage.setItem("sq_today_list", todayList);
      await refreshToday();
    });
  }

  function todayQuery() {
    return todayList === "mine" ? "?list=mine" : "";
  }

  async function refreshToday() {
    const tasks = await api("/api/today" + todayQuery());
    const list = document.getElementById("today-list");
    list.innerHTML = "";
    tasks.forEach(t => list.appendChild(todayEl(t)));
    markToday();
  }

  /* ---- nested subtasks on the board ---- */

  const SUB_OPEN_KEY = "sq-open-subtasks";

  function openSubtaskSet() {
    try { return new Set(JSON.parse(sessionStorage.getItem(SUB_OPEN_KEY) || "[]")); }
    catch (e) { return new Set(); }
  }

  function setExpanded(cardBox, open) {
    const list = cardBox.querySelector(".child-list");
    if (!list) return;
    list.hidden = !open;
    const arrow = cardBox.querySelector(".sub-arrow");
    if (arrow) arrow.innerHTML = open ? "&#9662;" : "&#9656;";
    const set = openSubtaskSet();
    if (open) set.add(cardBox.dataset.cardId); else set.delete(cardBox.dataset.cardId);
    sessionStorage.setItem(SUB_OPEN_KEY, JSON.stringify([...set]));
  }

  function hasKids(el) {
    return !!el.querySelector(".child-card") || parseInt(el.dataset.subTotal || "0", 10) > 0;
  }

  function childEl(sub) {
    const div = document.createElement("div");
    div.className = "child-card" + (sub.done ? " done" : "");
    div.dataset.cardId = sub.id;
    div.dataset.title = sub.title;
    const span = document.createElement("span");
    span.className = "child-title";
    span.textContent = sub.title;
    div.appendChild(span);
    return div;
  }

  function ensureChildUI(cardBox) {
    let list = cardBox.querySelector(".child-list");
    if (!list) {
      const badge = document.createElement("button");
      badge.type = "button";
      badge.className = "sub-badge";
      badge.title = "Show or hide the subtasks";
      badge.innerHTML = '<span class="sub-arrow">&#9656;</span> <span class="sub-count"></span>';
      cardBox.appendChild(badge);
      list = document.createElement("div");
      list.className = "child-list";
      list.dataset.parentId = cardBox.dataset.cardId;
      list.hidden = true;
      cardBox.appendChild(list);
      initChildSortable(list);
    }
    return list;
  }

  /* Where a drop landed when it wasn't a list: a card body under the
     pointer means "nest under that card". */
  function nestTargetAt(evt) {
    const oe = evt.originalEvent;
    if (!oe || typeof oe.clientX !== "number") return null;
    const under = document.elementFromPoint(oe.clientX, oe.clientY);
    if (!under) return null;
    const cardBox = under.closest(".card");
    if (!cardBox || cardBox === evt.item || cardBox.contains(evt.item)) return null;
    return parseInt(cardBox.dataset.cardId, 10);
  }

  async function nestCard(cardId, parentId) {
    try {
      await api(`/api/cards/${cardId}`, {
        method: "PATCH",
        body: JSON.stringify({ parent_id: parentId }),
      });
    } catch (err) {
      alert("Nest failed: " + err.message);
    }
    window.location.reload();
  }

  function initChildSortable(el) {
    new Sortable(el, {
      group: "cards",
      animation: 120,
      ghostClass: "sortable-ghost",
      fallbackOnBody: true,
      swapThreshold: 0.65,
      onEnd: async (evt) => {
        const cardId = evt.item.dataset.cardId;
        try {
          if (evt.to === evt.from) {
            if (evt.newIndex !== evt.oldIndex) {
              await api(`/api/subtasks/${cardId}`, {
                method: "PATCH",
                body: JSON.stringify({ position: evt.newIndex }),
              });
            }
            return;
          }
          if (evt.to.classList.contains("child-list")) {
            // Moved into another card's nested list.
            await api(`/api/cards/${cardId}`, {
              method: "PATCH",
              body: JSON.stringify({ parent_id: parseInt(evt.to.dataset.parentId, 10) }),
            });
          } else if (evt.to.dataset.today) {
            await api(`/api/cards/${cardId}/today`, {
              method: "POST",
              body: JSON.stringify({ today: true, list: todayList }),
            });
          } else {
            // Dragged out into a column: back to a top-level card.
            await api(`/api/cards/${cardId}`, {
              method: "PATCH",
              body: JSON.stringify({ clear_parent: true }),
            });
            await api(`/api/cards/${cardId}/move`, {
              method: "POST",
              body: JSON.stringify({ column_id: parseInt(evt.to.dataset.columnId, 10), position: evt.newIndex }),
            });
          }
        } catch (err) {
          alert("Move failed: " + err.message);
        }
        window.location.reload();
      },
    });
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
          if (to.classList.contains("child-list")) {
            // Dropped into an expanded nested list: nest under that card.
            if (hasKids(evt.item)) {
              alert("A card with subtasks of its own cannot become a subtask.");
              window.location.reload();
              return;
            }
            await nestCard(cardId, parseInt(to.dataset.parentId, 10));
            return;
          }
          if (to.dataset.today) {
            await api(`/api/cards/${cardId}/today`, {
              method: "POST",
              body: JSON.stringify({ today: true, position: evt.newIndex, list: todayList }),
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
            await api(`/api/cards/${cardId}/today`, { method: "POST", body: JSON.stringify({ today: false, list: todayList }) });
            evt.item.remove();
            await refreshToday();
          } else {
            // Dropped onto a collapsed card's body? That nests instead.
            const nestTarget = hasKids(evt.item) ? null : nestTargetAt(evt);
            if (nestTarget && nestTarget !== parseInt(cardId, 10)) {
              await nestCard(cardId, nestTarget);
              return;
            }
            const moved = await api(`/api/cards/${cardId}/move`, {
              method: "POST",
              body: JSON.stringify({ column_id: parseInt(to.dataset.columnId, 10), position: evt.newIndex }),
            });
            // A recurring card bounces out of Done server-side; redraw.
            if (moved.column_id !== parseInt(to.dataset.columnId, 10)) {
              window.location.reload();
              return;
            }
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
    const recur = card ? String(card.recur_days || 0) : "0";
    form.recur_days.value = [...form.recur_days.options].some(o => o.value === recur) ? recur : "0";
    document.getElementById("card-delete").hidden = !card;
    document.getElementById("assist-actions").hidden = !(card && window.BOARD.aiConfigured);
    document.getElementById("assist-note").textContent = "";
    document.getElementById("handoff-actions").hidden = !card;
    document.getElementById("attachments-box").hidden = !card;
    document.getElementById("attachment-list").textContent = "";
    document.getElementById("attachment-note").textContent = "";
    // A subtask card cannot take subtasks of its own (one level only).
    const isChild = !!(card && card.parent_id);
    document.getElementById("subtasks-box").hidden = !card || isChild;
    document.getElementById("subtask-list").textContent = "";
    document.getElementById("subtask-progress").textContent = "";
    document.getElementById("assist-subtasks").disabled = isChild;
    document.getElementById("activity-box").hidden = !card;
    document.getElementById("activity-feed").textContent = "";
    if (card) {
      refreshAttachments(card.id).catch(() => { /* list stays empty */ });
      if (!isChild) refreshSubtasks(card.id);
      refreshActivity(card.id);
      loadAssignees().then(users => {
        const row = document.getElementById("assignee-row");
        const select = form.assignee_id;
        row.hidden = users.length === 0;
        select.innerHTML = '<option value="">Nobody yet</option>';
        users.forEach(u => {
          const opt = document.createElement("option");
          opt.value = u.id;
          opt.textContent = u.username;
          select.appendChild(opt);
        });
        select.value = card.assignee_id ? String(card.assignee_id) : "";
        if (card.assignee_id && select.value !== String(card.assignee_id)) select.value = "";
      });
    } else {
      document.getElementById("assignee-row").hidden = true;
    }
    renderDialogChecklist();
    dialog.showModal();
  }

  document.querySelectorAll(".add-card-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      openCardDialog(null, parseInt(btn.closest(".column").dataset.columnId, 10));
    });
  });

  document.getElementById("board").addEventListener("click", async (e) => {
    const badge = e.target.closest(".sub-badge");
    if (badge) {
      const box = badge.closest(".card");
      const list = box.querySelector(".child-list");
      setExpanded(box, list ? list.hidden : false);
      return;
    }
    const mini = e.target.closest(".child-card");
    if (mini) {
      try {
        const child = await api(`/api/cards/${mini.dataset.cardId}`);
        openCardDialog(child, child.column_id);
      } catch (err) { alert(err.message); }
      return;
    }
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
      recur_days: parseInt(form.recur_days.value, 10),
    };
    if (!body.title) return;
    if (form.card_id.value && !document.getElementById("assignee-row").hidden) {
      if (form.assignee_id.value) body.assignee_id = parseInt(form.assignee_id.value, 10);
      else body.clear_assignee = true;
    }
    try {
      if (form.card_id.value) {
        const card = await api(`/api/cards/${form.card_id.value}`, { method: "PATCH", body: JSON.stringify(body) });
        const el = document.querySelector(`#board .card[data-card-id="${card.id}"]`);
        if (el) {
          el.dataset.title = card.title;
          el.dataset.priority = card.priority;
          el.dataset.due = card.due_date;
          el.dataset.labels = card.labels;
          el.dataset.recur = card.recur_days || 0;
          const chosen = form.assignee_id.selectedOptions[0];
          el.dataset.assignee = card.assignee_id && chosen ? chosen.textContent : "";
          el.querySelector(".card-title").textContent = card.title;
          syncCardChecklist(card);
          renderMeta(el);
        }
        const mini = document.querySelector(`#board .child-card[data-card-id="${card.id}"]`);
        if (mini) {
          mini.dataset.title = card.title;
          mini.querySelector(".child-title").textContent = card.title;
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
    if (!id || !confirm("Delete this card? Its subtasks become cards of their own.")) return;
    try {
      await api(`/api/cards/${id}`, { method: "DELETE" });
      const boardCard = document.querySelector(`#board .card[data-card-id="${id}"]`);
      if (boardCard && hasKids(boardCard)) {
        // The subtasks were promoted to top-level cards; redraw the board.
        window.location.reload();
        return;
      }
      document.querySelectorAll(`.card[data-card-id="${id}"], .child-card[data-card-id="${id}"]`).forEach(el => el.remove());
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
      if (kind === "subtasks") {
        await refreshSubtasks(id);
        note.textContent = data.subtasks.length
          ? `Added ${data.subtasks.length} subtask${data.subtasks.length > 1 ? "s" : ""}.`
          : "Nothing new to add.";
      } else {
        form.description.value = data.card.description;
        syncCardChecklist(data.card);
        renderDialogChecklist();
        note.textContent = "Done. Review and save.";
      }
    } catch (err) {
      note.textContent = err.message;
    }
  }
  document.getElementById("assist-subtasks").addEventListener("click", () => assist("subtasks"));
  document.getElementById("assist-describe").addEventListener("click", () => assist("describe"));

  /* ---- attachments ---- */

  function humanSize(n) {
    if (!isFinite(n) || n < 0) return "";
    if (n < 1024) return n + " B";
    const units = ["KB", "MB", "GB"];
    let u = -1;
    do { n /= 1024; u++; } while (n >= 1024 && u < units.length - 1);
    return (Math.round(n * 10) / 10) + " " + units[u];
  }

  function setCardAttachmentCount(cardId, n) {
    document.querySelectorAll(`.card[data-card-id="${cardId}"]`).forEach(el => {
      el.dataset.attachments = n;
      renderMeta(el);
    });
  }

  async function uploadAttachment(cardId, file) {
    const fd = new FormData();
    fd.append("file", file);
    const resp = await fetch(`/api/cards/${cardId}/attachments`, { method: "POST", body: fd });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (e) { /* ignore */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  function renderAttachmentList(items) {
    const list = document.getElementById("attachment-list");
    list.textContent = "";
    items.forEach(att => {
      const row = document.createElement("div");
      row.className = "attachment-row";
      const name = document.createElement("a");
      name.href = "#";
      name.className = "attachment-name";
      name.textContent = att.filename;
      name.title = att.filename;
      name.addEventListener("click", (e) => {
        e.preventDefault();
        window.SQPreview.open(att.id);
      });
      const size = document.createElement("span");
      size.className = "attachment-size muted";
      size.textContent = humanSize(att.size);
      const del = document.createElement("button");
      del.type = "button";
      del.className = "attachment-delete";
      del.title = "Delete this file";
      del.textContent = "×";
      del.addEventListener("click", async () => {
        if (!confirm(`Delete "${att.filename}"? The file is gone for good.`)) return;
        try {
          await api(`/api/attachments/${att.id}`, { method: "DELETE" });
          await refreshAttachments(att.card_id);
        } catch (err) { alert(err.message); }
      });
      row.append(name, size, del);
      list.appendChild(row);
    });
  }

  async function refreshAttachments(cardId) {
    const items = await api(`/api/cards/${cardId}/attachments`);
    renderAttachmentList(items);
    setCardAttachmentCount(cardId, items.length);
    return items;
  }

  const attachDrop = document.getElementById("attachment-drop");
  const attachInput = document.getElementById("attachment-input");
  const attachNote = document.getElementById("attachment-note");

  async function uploadToOpenCard(files) {
    const cardId = form.card_id.value;
    if (!cardId || !files.length) return;
    attachNote.textContent = "Uploading…";
    try {
      for (const f of files) await uploadAttachment(cardId, f);
      attachNote.textContent = "";
    } catch (err) {
      attachNote.textContent = "Upload failed: " + err.message;
    }
    try { await refreshAttachments(cardId); } catch (e) { /* keep the note */ }
  }

  attachDrop.addEventListener("click", () => attachInput.click());
  attachInput.addEventListener("change", async () => {
    const files = [...attachInput.files];
    attachInput.value = "";
    await uploadToOpenCard(files);
  });

  function dragHasFiles(e) {
    return !!(e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files"));
  }

  attachDrop.addEventListener("dragover", (e) => {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    attachDrop.classList.add("dragover");
  });
  attachDrop.addEventListener("dragleave", () => attachDrop.classList.remove("dragover"));
  attachDrop.addEventListener("drop", async (e) => {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    attachDrop.classList.remove("dragover");
    await uploadToOpenCard([...e.dataTransfer.files]);
  });

  /* Drop files straight onto a board card. Only file drags get handled, so
     SortableJS card dragging is left alone. */

  const boardEl = document.getElementById("board");
  let fileDropCard = null;

  function clearFileDropTarget() {
    if (fileDropCard) fileDropCard.classList.remove("file-drop");
    fileDropCard = null;
  }

  // Capture phase throughout: SortableJS listens for native drag events on
  // the .cards containers between the card and #board and can stop
  // propagation, which would starve bubble-phase handlers here and make the
  // browser refuse the drop entirely.
  boardEl.addEventListener("dragover", (e) => {
    if (!dragHasFiles(e)) return;
    const card = e.target.closest(".card");
    if (!card) { clearFileDropTarget(); return; }
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    if (fileDropCard !== card) {
      clearFileDropTarget();
      fileDropCard = card;
      card.classList.add("file-drop");
    }
  }, true);

  boardEl.addEventListener("dragleave", (e) => {
    if (fileDropCard && !fileDropCard.contains(e.relatedTarget)) clearFileDropTarget();
  }, true);

  boardEl.addEventListener("drop", async (e) => {
    if (!dragHasFiles(e)) return;
    const card = e.target.closest(".card");
    clearFileDropTarget();
    if (!card) return;
    e.preventDefault();
    const files = [...e.dataTransfer.files];
    if (!files.length) return;
    const cardId = card.dataset.cardId;
    try {
      for (const f of files) await uploadAttachment(cardId, f);
    } catch (err) {
      alert("Upload failed: " + err.message);
    }
    try {
      const items = await api(`/api/cards/${cardId}/attachments`);
      setCardAttachmentCount(cardId, items.length);
    } catch (err) { /* the chip catches up next reload */ }
  });

  // A file dropped anywhere else must not navigate the page away. Capture
  // phase, so no other handler's stopPropagation can starve the guard.
  document.addEventListener("dragover", (e) => { if (dragHasFiles(e)) e.preventDefault(); }, true);
  document.addEventListener("drop", (e) => {
    if (dragHasFiles(e) && !e.target.closest(".card, .dropzone")) e.preventDefault();
  }, true);

  /* ---- subtasks ---- */

  let assigneesCache = null;

  async function loadAssignees() {
    if (assigneesCache === null) {
      try { assigneesCache = await api("/api/assignees"); }
      catch (e) { assigneesCache = []; }
    }
    return assigneesCache;
  }

  function syncCardSubtasks(cardId, items) {
    const doneCount = items.filter(s => s.done).length;
    document.querySelectorAll(`.card[data-card-id="${cardId}"]`).forEach(el => {
      el.dataset.subTotal = items.length;
      el.dataset.subDone = doneCount;
      renderMeta(el);
    });
    const boardCard = document.querySelector(`#board .card[data-card-id="${cardId}"]`);
    if (boardCard) {
      if (items.length) {
        const list = ensureChildUI(boardCard);
        list.textContent = "";
        items.forEach(s => list.appendChild(childEl(s)));
        boardCard.querySelector(".sub-count").textContent = `${doneCount}/${items.length} subtasks`;
        boardCard.querySelector(".sub-badge").hidden = false;
      } else {
        const badge = boardCard.querySelector(".sub-badge");
        if (badge) {
          badge.hidden = true;
          const list = boardCard.querySelector(".child-list");
          if (list) list.hidden = true;
        }
      }
    }
    document.getElementById("subtask-progress").textContent =
      items.length ? `${doneCount}/${items.length}` : "";
  }

  async function refreshSubtasks(cardId) {
    let items = [];
    try { items = await api(`/api/cards/${cardId}/subtasks`); } catch (e) { return; }
    const list = document.getElementById("subtask-list");
    list.textContent = "";
    items.forEach(s => {
      const row = document.createElement("div");
      row.className = "subtask-row";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = !!s.done;
      box.addEventListener("change", async () => {
        try {
          await api(`/api/subtasks/${s.id}`, { method: "PATCH", body: JSON.stringify({ done: box.checked }) });
          await refreshSubtasks(cardId);
        } catch (err) { box.checked = !box.checked; alert(err.message); }
      });
      const title = document.createElement("span");
      title.className = "subtask-title" + (s.done ? " done" : "");
      title.textContent = s.title;
      title.title = "Click to rename";
      title.addEventListener("click", async () => {
        const next = prompt("Rename subtask:", s.title);
        if (!next || !next.trim() || next.trim() === s.title) return;
        try {
          await api(`/api/subtasks/${s.id}`, { method: "PATCH", body: JSON.stringify({ title: next.trim() }) });
          await refreshSubtasks(cardId);
        } catch (err) { alert(err.message); }
      });
      const open = document.createElement("button");
      open.type = "button";
      open.className = "subtask-open";
      open.textContent = "↗";
      open.title = "Open this subtask's own card";
      open.addEventListener("click", async () => {
        try {
          const child = await api(`/api/cards/${s.id}`);
          dialog.close();
          openCardDialog(child, child.column_id);
        } catch (err) { alert(err.message); }
      });
      const del = document.createElement("button");
      del.type = "button";
      del.className = "attachment-delete";
      del.textContent = "×";
      del.title = "Delete subtask";
      del.addEventListener("click", async () => {
        try {
          await api(`/api/subtasks/${s.id}`, { method: "DELETE" });
          await refreshSubtasks(cardId);
        } catch (err) { alert(err.message); }
      });
      row.append(box, title, open, del);
      list.appendChild(row);
    });
    syncCardSubtasks(cardId, items);
  }

  async function addSubtask() {
    const cardId = form.card_id.value;
    const input = document.getElementById("subtask-new");
    const title = input.value.trim();
    if (!cardId || !title) return;
    try {
      await api(`/api/cards/${cardId}/subtasks`, { method: "POST", body: JSON.stringify({ title }) });
      input.value = "";
      input.focus();
      await refreshSubtasks(cardId);
    } catch (err) { alert(err.message); }
  }

  document.getElementById("subtask-add-btn").addEventListener("click", addSubtask);
  document.getElementById("subtask-new").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addSubtask(); }
  });

  /* ---- activity and comments ---- */

  function eventLine(ev) {
    const row = document.createElement("div");
    row.className = "activity-row" + (ev.kind === "comment" ? " is-comment" : "");
    const head = document.createElement("span");
    head.className = "muted";
    const when = (ev.created_at || "").slice(0, 16);
    const label = {
      created: "created this card", moved: "moved it", assigned: "assigned it",
      attached: "attached", respawned: "sent it back around",
    }[ev.kind] || "";
    head.textContent = ev.kind === "comment"
      ? `${ev.actor} · ${when}`
      : `${ev.actor} ${label}${ev.text ? " " + ev.text : ""} · ${when}`;
    row.appendChild(head);
    if (ev.kind === "comment") {
      const body = document.createElement("div");
      body.textContent = ev.text;
      row.appendChild(body);
    }
    return row;
  }

  async function refreshActivity(cardId) {
    let events = [];
    try { events = await api(`/api/cards/${cardId}/events`); } catch (e) { return; }
    const feed = document.getElementById("activity-feed");
    feed.textContent = "";
    events.forEach(ev => feed.appendChild(eventLine(ev)));
    feed.scrollTop = feed.scrollHeight;
  }

  document.getElementById("comment-post").addEventListener("click", async () => {
    const cardId = form.card_id.value;
    const input = document.getElementById("comment-new");
    const text = input.value.trim();
    if (!cardId || !text) return;
    try {
      await api(`/api/cards/${cardId}/comments`, { method: "POST", body: JSON.stringify({ text }) });
      input.value = "";
      await refreshActivity(cardId);
    } catch (err) { alert(err.message); }
  });

  /* ---- AI research and handoff ---- */

  async function copyText(text, host) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (e) { /* fall through to the manual path */ }
    }
    // Plain-http tablets have no clipboard API; a temporary textarea does it.
    // It must live inside the open modal dialog or focus is blocked.
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    (host || document.body).appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  const researchDialog = document.getElementById("research-dialog");
  let researchText = "";

  function renderResearch(text) {
    const box = document.getElementById("research-body");
    box.textContent = "";
    text.split("\n").forEach(line => {
      const m = line.match(/^#{1,6}\s+(.*)$/);
      if (m) {
        const strong = document.createElement("strong");
        strong.textContent = m[1];
        box.appendChild(strong);
      } else {
        box.appendChild(document.createTextNode(line));
      }
      box.appendChild(document.createTextNode("\n"));
    });
  }

  document.getElementById("assist-research").addEventListener("click", async () => {
    const id = form.card_id.value;
    if (!id) return;
    const btn = document.getElementById("assist-research");
    const note = document.getElementById("assist-note");
    btn.disabled = true;
    note.textContent = "Researching… this can take a minute.";
    try {
      const data = await api("/api/assist/research", {
        method: "POST",
        body: JSON.stringify({ card_id: parseInt(id, 10) }),
      });
      researchText = data.research || "";
      renderResearch(researchText);
      document.getElementById("research-note").textContent = "";
      note.textContent = "";
      researchDialog.showModal();
    } catch (err) {
      note.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("research-append").addEventListener("click", () => {
    form.description.value =
      form.description.value.replace(/\s+$/, "") + "\n\n---\nResearch notes:\n" + researchText;
    renderDialogChecklist();
    researchDialog.close();
    document.getElementById("assist-note").textContent = "Added to the description. Save to keep it.";
  });

  document.getElementById("research-copy").addEventListener("click", async () => {
    const ok = await copyText(researchText, researchDialog);
    document.getElementById("research-note").textContent =
      ok ? "Copied." : "Copy failed. Select the text and copy it by hand.";
  });

  document.getElementById("research-close").addEventListener("click", () => researchDialog.close());

  const handoffDialog = document.getElementById("handoff-dialog");
  let handoffPrompt = "";

  document.getElementById("send-to-ai").addEventListener("click", async () => {
    const id = form.card_id.value;
    if (!id) return;
    try {
      const data = await api(`/api/cards/${id}/handoff`);
      handoffPrompt = data.prompt || "";
      document.getElementById("handoff-text").value = handoffPrompt;
      document.getElementById("handoff-note").textContent = "";
      handoffDialog.showModal();
    } catch (err) { alert(err.message); }
  });

  async function handoffCopy(text, doneNote) {
    const ok = await copyText(text, handoffDialog);
    document.getElementById("handoff-note").textContent =
      ok ? doneNote : "Copy failed. Select the prompt above and copy it by hand.";
    return ok;
  }

  document.getElementById("handoff-copy").addEventListener("click", () => {
    handoffCopy(handoffPrompt, "Copied.");
  });

  document.getElementById("handoff-claude").addEventListener("click", () => {
    window.open("https://claude.ai/new?q=" + encodeURIComponent(handoffPrompt));
  });

  document.getElementById("handoff-chatgpt").addEventListener("click", () => {
    window.open("https://chatgpt.com/?q=" + encodeURIComponent(handoffPrompt));
  });

  document.getElementById("handoff-gemini").addEventListener("click", async () => {
    await handoffCopy(handoffPrompt, "Copied. Paste it into Gemini.");
    window.open("https://gemini.google.com/app");
  });

  document.getElementById("handoff-claude-code").addEventListener("click", () => {
    const shellSafe = handoffPrompt.replace(/[\\"`$]/g, (c) => "\\" + c);
    handoffCopy('claude "' + shellSafe + '"', "Copied. Paste it into a terminal.");
  });

  document.getElementById("handoff-close").addEventListener("click", () => handoffDialog.close());

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
      const isDone = col.classList.contains("is-done");
      const archiveHint = isDone ? ' "archive" to sweep finished cards into the project archive,' : "";
      const choice = prompt(
        `Column "${name}"\nType a new name to rename, "done" to toggle the finished flag, "limit N" for a work-in-progress cap (0 removes it),${archiveHint} or "delete" to remove (must be empty):`
      );
      if (!choice) return;
      const limitMatch = choice.trim().toLowerCase().match(/^limit\s+(\d{1,2})$/);
      try {
        if (isDone && choice.trim().toLowerCase() === "archive") {
          const result = await api(`/api/projects/${projectId}/archive-done`, { method: "POST" });
          alert(`Archived ${result.archived} card${result.archived === 1 ? "" : "s"}. They live on in the project overview.`);
        } else if (choice.trim().toLowerCase() === "delete") {
          await api(`/api/columns/${columnId}`, { method: "DELETE" });
        } else if (choice.trim().toLowerCase() === "done") {
          await api(`/api/columns/${columnId}`, { method: "PATCH", body: JSON.stringify({ is_done: !col.classList.contains("is-done") }) });
        } else if (limitMatch) {
          await api(`/api/columns/${columnId}`, { method: "PATCH", body: JSON.stringify({ wip_limit: parseInt(limitMatch[1], 10) }) });
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
      // textContent + createElement: a project name must never be markup.
      const target = document.getElementById("nudge-text");
      target.textContent = line + " ";
      const go = document.createElement("a");
      go.href = `/project/${p.id}`;
      go.textContent = "Go finish it";
      target.appendChild(go);
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

  const planBtn = document.getElementById("plan-day");
  if (planBtn) {
    planBtn.addEventListener("click", async () => {
      planBtn.disabled = true;
      planBtn.textContent = "Planning...";
      try {
        const data = await api("/api/assist/plan-day", {
          method: "POST",
          body: JSON.stringify({ list: todayList }),
        });
        await refreshToday();
        planBtn.textContent = data.added.length
          ? `Added ${data.added.length} task${data.added.length > 1 ? "s" : ""}`
          : "Nothing to plan";
      } catch (err) {
        planBtn.textContent = "\u{1F43F}️ Plan my day";
        alert("Planning failed: " + err.message);
      } finally {
        planBtn.disabled = false;
        setTimeout(() => { planBtn.textContent = "\u{1F43F}️ Plan my day"; }, 4000);
      }
    });
  }

  document.getElementById("clear-done-today").addEventListener("click", async () => {
    try {
      await api("/api/today/clear-done" + todayQuery(), { method: "POST" });
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
      const hay = (el.dataset.title + " " + el.dataset.labels + " " + (el.dataset.assignee || "")).toLowerCase();
      el.style.display = !q || hay.includes(q) ? "" : "none";
    });
  });

  /* ---- init ---- */

  document.querySelectorAll("#board .card").forEach(renderMeta);
  document.querySelectorAll("#board .child-list").forEach(initChildSortable);
  const openSubs = openSubtaskSet();
  document.querySelectorAll("#board .card").forEach(el => {
    if (openSubs.has(el.dataset.cardId)) setExpanded(el, true);
  });
  updateCounts();
  refreshToday();
  squirrelNudge();
})();
