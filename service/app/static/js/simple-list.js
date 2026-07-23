/* Simple list projects: add, tick, untick, reorder, clear. Items are
   ordinary cards underneath, so Today, displays, and search all work. */
(function () {
  "use strict";

  const unchecked = document.getElementById("list-unchecked");
  const checked = document.getElementById("list-checked");

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

  function itemEl(card, done) {
    const li = document.createElement("li");
    li.className = "list-item" + (done ? " done" : "");
    li.dataset.cardId = card.id;
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = done;
    if (!window.LIST.canEdit) box.disabled = true;
    const title = document.createElement("span");
    title.className = "item-title";
    title.textContent = card.title;
    li.append(box, title);
    if (window.LIST.canEdit) {
      const del = document.createElement("button");
      del.className = "item-delete";
      del.title = "Remove";
      del.textContent = "×";
      li.appendChild(del);
    }
    return li;
  }

  const addForm = document.getElementById("list-add");
  if (addForm) {
    addForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = document.getElementById("list-new");
      const title = input.value.trim();
      if (!title) return;
      input.value = "";
      try {
        const card = await api("/api/cards", {
          method: "POST",
          body: JSON.stringify({
            project_id: window.LIST.projectId,
            column_id: window.LIST.itemsColumnId,
            title: title,
          }),
        });
        unchecked.appendChild(itemEl(card, false));
        const empty = document.getElementById("list-empty");
        if (empty) empty.remove();
      } catch (err) { alert(err.message); }
      input.focus();
    });
  }

  async function toggle(li, box) {
    try {
      await api(`/api/kiosk/toggle/${li.dataset.cardId}`, { method: "POST" });
      const target = box.checked ? checked : unchecked;
      li.classList.toggle("done", box.checked);
      target.appendChild(li);
    } catch (err) {
      box.checked = !box.checked;
      alert(err.message);
    }
  }

  document.querySelector(".simple-list").addEventListener("change", (e) => {
    if (e.target.type !== "checkbox") return;
    toggle(e.target.closest(".list-item"), e.target);
  });

  document.querySelector(".simple-list").addEventListener("click", async (e) => {
    if (!e.target.classList.contains("item-delete")) return;
    const li = e.target.closest(".list-item");
    try {
      await api(`/api/cards/${li.dataset.cardId}`, { method: "DELETE" });
      li.remove();
    } catch (err) { alert(err.message); }
  });

  const clearBtn = document.getElementById("clear-checked");
  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      try {
        await api(`/api/projects/${window.LIST.projectId}/archive-done`, { method: "POST" });
        checked.textContent = "";
        const divider = document.querySelector(".checked-divider");
        if (divider) divider.remove();
      } catch (err) { alert(err.message); }
    });
  }

  const deleteBtn = document.getElementById("delete-list");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Delete this whole list? Its items go with it.")) return;
      try {
        await api(`/api/projects/${window.LIST.projectId}`, { method: "DELETE" });
        window.location.href = "/";
      } catch (err) { alert(err.message); }
    });
  }

  document.getElementById("project-select").addEventListener("change", (e) => {
    window.location.href = `/project/${e.target.value}`;
  });

  if (window.LIST.canEdit && window.Sortable) {
    new Sortable(unchecked, {
      animation: 120,
      onEnd: async (evt) => {
        try {
          await api(`/api/cards/${evt.item.dataset.cardId}/move`, {
            method: "POST",
            body: JSON.stringify({
              column_id: window.LIST.itemsColumnId,
              position: evt.newIndex,
            }),
          });
        } catch (err) { window.location.reload(); }
      },
    });
  }
})();
