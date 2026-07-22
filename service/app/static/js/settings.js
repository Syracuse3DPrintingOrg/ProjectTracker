/* Settings page: a sidebar of panes (hash-routed, one visible at a time);
   each section still posts only its own fields. */
(function () {
  "use strict";

  // --- Pane routing: /settings#ai deep-links and survives refresh. ---
  const panes = Array.from(document.querySelectorAll(".settings-pane"));
  const paneNames = panes.map((p) => p.dataset.pane);
  const navLinks = Array.from(document.querySelectorAll(".settings-nav a"));
  const paneLoaded = {};

  function showPane(name) {
    if (paneNames.indexOf(name) === -1) name = "overview";
    panes.forEach((p) => { p.hidden = p.dataset.pane !== name; });
    navLinks.forEach((a) => {
      a.classList.toggle("active", a.getAttribute("href") === "#" + name);
    });
    // Panes that fetch their numbers do it on first show, not page load.
    if (name === "overview" && !paneLoaded.overview) {
      paneLoaded.overview = true;
      loadOverview();
    }
    if (name === "updates" && !paneLoaded.updates) {
      paneLoaded.updates = true;
      checkUpdates();
    }
  }

  window.addEventListener("hashchange", () => {
    showPane(window.location.hash.slice(1));
  });
  showPane(window.location.hash.slice(1) || "overview");

  // --- Overview pane ---
  function setStat(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value);
  }

  function setHealth(id, ok, okText, otherText, warnWhenOff) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = ok ? okText : otherText;
    el.classList.remove("ok", "warn");
    if (ok) el.classList.add("ok");
    else if (warnWhenOff) el.classList.add("warn");
  }

  async function loadOverview() {
    const note = document.getElementById("ov-note");
    try {
      const resp = await fetch("/api/settings/overview");
      if (!resp.ok) throw new Error(resp.statusText);
      const data = await resp.json();
      setStat("ov-projects", data.projects);
      setStat("ov-cards", data.open_cards);
      setStat("ov-users", data.users);
      setStat("ov-displays", data.displays);
      const h = data.health || {};
      setHealth("ov-health-data", h.data_dir_writable, "writable", "not writable: nothing can be saved", true);
      setHealth("ov-health-ai", h.ai_configured, "configured", "not set up (optional)", false);
      setHealth("ov-health-users", h.users_configured, "on", "off: open on your network", false);
    } catch (err) {
      if (note) note.textContent = "Could not load the overview: " + err.message;
    }
  }

  // --- Updates pane ---
  async function checkUpdates() {
    const el = document.getElementById("updates-status");
    el.textContent = "Checking for a newer release...";
    try {
      const resp = await fetch("/api/settings/updates");
      if (!resp.ok) throw new Error(resp.statusText);
      const data = await resp.json();
      if (data.error) {
        el.textContent = data.error;
        return;
      }
      el.textContent = "";
      if (data.update_available) {
        const strong = document.createElement("strong");
        strong.textContent = data.latest + " available.";
        el.appendChild(strong);
        el.appendChild(document.createTextNode(
          " You are on " + data.current + "; pull the new image below to update. "));
        const link = document.createElement("a");
        link.href = data.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "What changed";
        el.appendChild(link);
      } else if (data.latest) {
        el.textContent = "You are current: " + data.current + " is the newest release.";
      } else {
        el.textContent = "You are on " + data.current + "; no releases have been published yet.";
      }
    } catch (err) {
      el.textContent = "Could not check for updates: " + err.message;
    }
  }

  document.getElementById("check-updates").addEventListener("click", checkUpdates);

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

  // --- API keys ---
  const keysBody = document.getElementById("keys-body");
  const keysNote = document.getElementById("keys-note");

  function keyRow(k) {
    const tr = document.createElement("tr");
    tr.style.borderBottom = "1px solid var(--border)";
    const name = document.createElement("td");
    name.style.padding = "0.6rem 0.4rem";
    const strong = document.createElement("strong");
    strong.textContent = k.name;
    name.appendChild(strong);
    tr.appendChild(name);
    const role = document.createElement("td");
    role.style.padding = "0.6rem 0.4rem";
    role.innerHTML = `<span class="chip">${k.role}</span>`;
    tr.appendChild(role);
    const used = document.createElement("td");
    used.style.padding = "0.6rem 0.4rem";
    used.className = "muted";
    used.textContent = k.last_used ? "last used " + k.last_used + " UTC" : "never used";
    tr.appendChild(used);
    const actions = document.createElement("td");
    actions.style.padding = "0.6rem 0.4rem";
    actions.style.textAlign = "right";
    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "Revoke";
    del.addEventListener("click", async () => {
      if (!confirm(`Revoke "${k.name}"? Anything using it stops working immediately.`)) return;
      try {
        await apiUsers("/api/keys/" + k.id, "DELETE");
        await loadKeys();
      } catch (err) { keysNote.textContent = err.message; }
    });
    actions.appendChild(del);
    tr.appendChild(actions);
    return tr;
  }

  async function loadKeys() {
    try {
      const keys = await apiUsers("/api/keys", "GET");
      keysBody.innerHTML = "";
      keys.forEach((k) => keysBody.appendChild(keyRow(k)));
    } catch (err) {
      document.getElementById("keys-table").hidden = true;
      document.getElementById("add-key").hidden = true;
      keysNote.textContent = "You need to be an admin to manage keys.";
    }
  }

  document.getElementById("add-key").addEventListener("click", async () => {
    const name = prompt("Name this key (e.g. Home Assistant):");
    if (!name || !name.trim()) return;
    const asViewer = confirm("OK = member key (can act: create cards, pop up displays).\nCancel = viewer key (read-only).");
    try {
      const key = await apiUsers("/api/keys", "POST", {
        name: name.trim(),
        role: asViewer ? "member" : "viewer",
      });
      prompt("Copy the key now; it is not shown again:", key.token);
      keysNote.textContent = "";
      await loadKeys();
    } catch (err) { keysNote.textContent = err.message; }
  });

  loadKeys();

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
