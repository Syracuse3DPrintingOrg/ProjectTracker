/* Project overview page: file previews and description editing. */
(function () {
  "use strict";

  const cfg = window.OVERVIEW || {};

  // Files open in the attachment preview dialog (preview.js).
  document.querySelectorAll(".overview-file").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.attachmentId, 10);
      if (id && window.SQPreview) window.SQPreview.open(id);
    });
  });

  // Archiving: sweep finished cards into the Archived list, or bring
  // one back. Both buttons only render for people who can edit.
  const archiveNote = document.getElementById("archive-note");
  const archiveBtn = document.getElementById("archive-done");
  if (archiveBtn) {
    archiveBtn.addEventListener("click", async () => {
      archiveNote.textContent = "Archiving...";
      try {
        const resp = await fetch("/api/projects/" + cfg.projectId + "/archive-done", { method: "POST" });
        if (!resp.ok) throw new Error(resp.statusText);
        const result = await resp.json();
        if (!result.archived) {
          archiveNote.textContent = "No finished cards to archive.";
          return;
        }
        window.location.reload();
      } catch (err) {
        archiveNote.textContent = "Archive failed: " + err.message;
      }
    });
  }

  document.querySelectorAll(".unarchive-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const resp = await fetch("/api/cards/" + btn.dataset.cardId, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ archived: false }),
        });
        if (!resp.ok) throw new Error(resp.statusText);
        window.location.reload();
      } catch (err) {
        btn.textContent = "Failed: " + err.message;
      }
    });
  });

  // Description editing. Viewers get no form; nothing below applies.
  const form = document.getElementById("desc-form");
  const view = document.getElementById("desc-view");
  const editBtn = document.getElementById("desc-edit");
  if (!form || !view || !editBtn) return;
  const textarea = document.getElementById("desc-text");
  const note = document.getElementById("desc-note");

  function renderView(text) {
    view.textContent = "";
    const paras = text.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!paras.length) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "No description yet. What is this project about?";
      view.appendChild(p);
      return;
    }
    paras.forEach((para) => {
      const p = document.createElement("p");
      p.textContent = para;
      view.appendChild(p);
    });
  }

  function showForm(show) {
    form.hidden = !show;
    view.hidden = show;
    editBtn.hidden = show;
    if (show) textarea.focus();
  }

  editBtn.addEventListener("click", () => showForm(true));

  // The description saves as you type; Done just saves anything still
  // waiting and folds the editor away.
  let saveTimer = null;
  let saveChain = Promise.resolve();

  async function persist(text) {
    const resp = await fetch("/api/projects/" + cfg.projectId, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: text }),
    });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (err) { /* keep statusText */ }
      throw new Error(detail);
    }
    const project = await resp.json();
    cfg.description = project.description || "";
  }

  function save() {
    clearTimeout(saveTimer);
    saveTimer = null;
    const text = textarea.value;
    if (text === (cfg.description || "")) return saveChain;
    note.textContent = "Saving…";
    saveChain = saveChain.catch(() => {}).then(() => persist(text)).then(() => {
      if (textarea.value === text) note.textContent = "Saved";
    }, (err) => {
      note.textContent = "Save failed: " + err.message;
      throw err;
    });
    return saveChain;
  }

  textarea.addEventListener("input", () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => { save().catch(() => { /* shown in the note */ }); }, 800);
  });
  textarea.addEventListener("blur", () => { save().catch(() => { /* shown in the note */ }); });

  window.addEventListener("pagehide", () => {
    if (!saveTimer) return;
    clearTimeout(saveTimer);
    fetch("/api/projects/" + cfg.projectId, {
      method: "PATCH",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: textarea.value }),
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await save();
      textarea.value = cfg.description;
      renderView(cfg.description);
      note.textContent = "";
      showForm(false);
    } catch (err) { /* shown in the note */ }
  });
})();
