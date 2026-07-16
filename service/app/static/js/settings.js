/* Settings page: each section posts only its own fields. */
(function () {
  "use strict";

  async function save(body, noteId, okText) {
    const note = document.getElementById(noteId);
    note.textContent = "Saving...";
    try {
      const resp = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(resp.statusText);
      note.textContent = okText || "Saved.";
      return await resp.json();
    } catch (err) {
      note.textContent = "Save failed: " + err.message;
      return null;
    }
  }

  document.getElementById("llm-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const body = {
      llm_provider: f.llm_provider.value,
      ollama_url: f.ollama_url.value.trim(),
      llm_model: f.llm_model.value.trim(),
    };
    // Only send keys the user actually typed, so saved ones survive.
    ["gemini_api_key", "anthropic_api_key", "openai_api_key"].forEach((k) => {
      if (f[k].value.trim()) body[k] = f[k].value.trim();
    });
    const data = await save(body, "llm-note");
    if (data) {
      ["gemini_api_key", "anthropic_api_key", "openai_api_key"].forEach((k) => { f[k].value = ""; });
    }
  });

  document.getElementById("test-llm").addEventListener("click", async () => {
    const note = document.getElementById("llm-note");
    note.textContent = "Testing (save first if you changed anything)...";
    try {
      const resp = await fetch("/api/settings/test-llm", { method: "POST" });
      const data = await resp.json();
      note.textContent = data.ok ? `Working (${data.provider}).` : `Failed: ${data.error}`;
    } catch (err) {
      note.textContent = "Test failed: " + err.message;
    }
  });

  document.getElementById("general-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await save({ app_title: e.target.app_title.value.trim() }, "general-note");
  });

  // --- Users ---
  const usersBody = document.getElementById("users-body");
  const usersNote = document.getElementById("users-note");
  const userDialog = document.getElementById("user-dialog");
  const userForm = document.getElementById("user-form");

  async function apiUsers(path, method, body) {
    const resp = await fetch(path, {
      method: method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (e) { /* not JSON */ }
      throw new Error(detail);
    }
    return resp.status === 204 ? null : resp.json();
  }

  function userRow(u) {
    const tr = document.createElement("tr");
    tr.style.borderBottom = "1px solid var(--border)";

    const nameTd = document.createElement("td");
    nameTd.style.padding = "0.6rem 0.4rem";
    const strong = document.createElement("strong");
    strong.textContent = u.username;
    nameTd.appendChild(strong);
    tr.appendChild(nameTd);

    const roleTd = document.createElement("td");
    roleTd.style.padding = "0.6rem 0.4rem";
    const roleSel = document.createElement("select");
    roleSel.style.margin = "0";
    ["admin", "member", "viewer"].forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = r;
      if (r === u.role) opt.selected = true;
      roleSel.appendChild(opt);
    });
    roleSel.addEventListener("change", () => {
      changeUser(u.id, { role: roleSel.value });
    });
    roleTd.appendChild(roleSel);
    tr.appendChild(roleTd);

    const statusTd = document.createElement("td");
    statusTd.style.padding = "0.6rem 0.4rem";
    statusTd.className = u.disabled ? "muted" : "";
    statusTd.textContent = u.disabled ? "disabled" : "active";
    tr.appendChild(statusTd);

    const actionsTd = document.createElement("td");
    actionsTd.style.padding = "0.6rem 0.4rem";
    actionsTd.style.whiteSpace = "nowrap";
    actionsTd.style.textAlign = "right";

    const resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.textContent = "Reset password";
    resetBtn.addEventListener("click", () => {
      const pw = prompt("New password for " + u.username + " (at least 4 characters):");
      if (!pw) return;
      changeUser(u.id, { password: pw }, "Password reset for " + u.username + ".");
    });
    actionsTd.appendChild(resetBtn);

    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.textContent = u.disabled ? "Enable" : "Disable";
    toggleBtn.addEventListener("click", () => {
      changeUser(u.id, { disabled: u.disabled ? 0 : 1 });
    });
    actionsTd.appendChild(toggleBtn);

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "danger";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Delete " + u.username + "? Their login goes away; the boards stay.")) return;
      usersNote.textContent = "";
      try {
        await apiUsers("/api/users/" + u.id, "DELETE");
        await loadUsers();
      } catch (err) {
        usersNote.textContent = err.message;
      }
    });
    actionsTd.appendChild(deleteBtn);

    tr.appendChild(actionsTd);
    return tr;
  }

  async function changeUser(id, body, okText) {
    usersNote.textContent = "";
    try {
      await apiUsers("/api/users/" + id, "PATCH", body);
      if (okText) usersNote.textContent = okText;
      await loadUsers();
    } catch (err) {
      usersNote.textContent = err.message;
      await loadUsers();
    }
  }

  async function loadUsers() {
    try {
      const users = await apiUsers("/api/users", "GET");
      usersBody.innerHTML = "";
      users.forEach((u) => usersBody.appendChild(userRow(u)));
      if (!users.length) usersNote.textContent = "No users yet. The whole network can rummage freely.";
      else if (usersNote.textContent.startsWith("No users yet")) usersNote.textContent = "";
    } catch (err) {
      document.getElementById("users-table").hidden = true;
      document.getElementById("add-user").hidden = true;
      usersNote.textContent = "You need to be an admin to manage users.";
    }
  }

  document.getElementById("add-user").addEventListener("click", () => {
    userForm.reset();
    document.getElementById("user-dialog-note").textContent = "";
    userDialog.showModal();
  });

  document.getElementById("user-cancel").addEventListener("click", () => userDialog.close());

  userForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const note = document.getElementById("user-dialog-note");
    note.textContent = "Adding...";
    try {
      await apiUsers("/api/users", "POST", {
        username: userForm.username.value.trim(),
        password: userForm.password.value,
        role: userForm.role.value,
      });
      userDialog.close();
      usersNote.textContent = "";
      await loadUsers();
    } catch (err) {
      note.textContent = err.message;
    }
  });

  loadUsers();

  document.getElementById("import-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    const note = document.getElementById("backup-note");
    if (!file) return;
    if (!confirm("Replace ALL projects, columns, and cards with this backup?")) {
      e.target.value = "";
      return;
    }
    try {
      const data = JSON.parse(await file.text());
      data.confirm = true;
      const resp = await fetch("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText);
      const counts = await resp.json();
      note.textContent = `Restored ${counts.projects} projects, ${counts.cards} cards.`;
    } catch (err) {
      note.textContent = "Restore failed: " + err.message;
    }
    e.target.value = "";
  });

  document.getElementById("rotate-token").addEventListener("click", async () => {
    const data = await save({ rotate_display_token: true }, "token-note", "New token generated.");
    if (data) document.getElementById("display-token").textContent = data.display_token || "none";
  });

  document.getElementById("clear-token").addEventListener("click", async () => {
    const data = await save({ clear_display_token: true }, "token-note", "Token removed.");
    if (data) document.getElementById("display-token").textContent = "none";
  });
})();
