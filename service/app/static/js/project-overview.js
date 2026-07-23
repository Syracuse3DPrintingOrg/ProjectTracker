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

  document.getElementById("desc-cancel").addEventListener("click", () => {
    textarea.value = cfg.description || "";
    note.textContent = "";
    showForm(false);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    note.textContent = "Saving…";
    try {
      const resp = await fetch("/api/projects/" + cfg.projectId, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: textarea.value }),
      });
      if (!resp.ok) {
        let detail = resp.statusText;
        try { detail = (await resp.json()).detail || detail; } catch (err) { /* keep statusText */ }
        throw new Error(detail);
      }
      const project = await resp.json();
      cfg.description = project.description || "";
      textarea.value = cfg.description;
      renderView(cfg.description);
      note.textContent = "";
      showForm(false);
    } catch (err) {
      note.textContent = "Save failed: " + err.message;
    }
  });
})();
