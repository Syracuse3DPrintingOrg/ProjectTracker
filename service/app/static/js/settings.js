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

  document.getElementById("access-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const pw = e.target.password.value;
    if (!pw) {
      document.getElementById("access-note").textContent = "Type a password first.";
      return;
    }
    const data = await save({ password: pw }, "access-note", "Password set.");
    if (data) e.target.password.value = "";
  });

  const clearPw = document.getElementById("clear-password");
  if (clearPw) {
    clearPw.addEventListener("click", async () => {
      if (!confirm("Remove the password? The app will be open on your network.")) return;
      const data = await save({ clear_password: true }, "access-note", "Password removed.");
      if (data) window.location.reload();
    });
  }

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
