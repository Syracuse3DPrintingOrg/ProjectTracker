/* Displays page: registry CRUD and Android TV actions. */
(function () {
  "use strict";

  const dialog = document.getElementById("display-dialog");
  const form = document.getElementById("display-form");
  const note = document.getElementById("displays-note");

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

  function syncKindRows() {
    document.getElementById("adb-row").style.display =
      form.kind.value === "androidtv" ? "" : "none";
    document.getElementById("look-rows").style.display =
      form.kind.value === "esp32" ? "none" : "";
  }
  form.kind.addEventListener("change", syncKindRows);

  function openDialog(row) {
    form.display_id.value = row ? row.dataset.id : "";
    form.name.value = row ? row.dataset.name : "";
    form.kind.value = row ? row.dataset.kind : "browser";
    form.adb_host.value = row ? row.dataset.adb : "";
    const params = row ? JSON.parse(row.dataset.params || "{}") : {};
    form.theme.value = params.theme || "dark";
    form.scale.value = params.scale || "1";
    form.clock.value = params.clock === "0" ? "0" : "1";
    form.hide_done.value = params.hide_done || "";
    form.tv.checked = params.tv === "1";
    syncKindRows();
    dialog.showModal();
  }

  document.getElementById("add-display").addEventListener("click", () => openDialog(null));
  document.getElementById("display-cancel").addEventListener("click", () => dialog.close());

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const params = {};
    if (form.theme.value !== "dark") params.theme = form.theme.value;
    if (form.scale.value !== "1") params.scale = form.scale.value;
    if (form.clock.value === "0") params.clock = "0";
    if (form.hide_done.value) params.hide_done = form.hide_done.value;
    if (form.tv.checked) params.tv = "1";
    const body = {
      name: form.name.value.trim(),
      kind: form.kind.value,
      adb_host: form.adb_host.value.trim(),
      params: params,
    };
    try {
      if (form.display_id.value) {
        await api(`/api/displays/${form.display_id.value}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await api("/api/displays", { method: "POST", body: JSON.stringify(body) });
      }
      window.location.reload();
    } catch (err) { alert("Save failed: " + err.message); }
  });

  document.getElementById("display-table").addEventListener("click", async (e) => {
    const row = e.target.closest("tr");
    if (!row) return;
    if (e.target.classList.contains("edit-btn")) {
      openDialog(row);
    } else if (e.target.classList.contains("delete-btn")) {
      if (!confirm(`Remove "${row.dataset.name}"? The device itself is not touched.`)) return;
      try {
        await api(`/api/displays/${row.dataset.id}`, { method: "DELETE" });
        window.location.reload();
      } catch (err) { alert(err.message); }
    } else if (e.target.classList.contains("tv-btn")) {
      const action = e.target.dataset.action;
      note.textContent = action === "show" ? "Waking the TV..." : "Sending...";
      try {
        await api(`/api/displays/${row.dataset.id}/tv/${action}`, { method: "POST" });
        note.textContent = action === "show"
          ? "Sent. First time? Accept the debugging prompt on the TV."
          : "Sent.";
      } catch (err) {
        note.textContent = "TV command failed: " + err.message;
      }
    }
  });

  document.getElementById("base-url-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const el = document.getElementById("base-url-note");
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: e.target.base_url.value.trim() }),
      });
      el.textContent = "Saved.";
      window.location.reload();
    } catch (err) { el.textContent = "Save failed: " + err.message; }
  });
})();
