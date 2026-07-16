/* Claude Code dashboard: renders machine snapshots, polls, links projects. */
(function () {
  "use strict";

  const grid = document.getElementById("dash-grid");
  const dialog = document.getElementById("link-dialog");
  const form = document.getElementById("link-form");

  function esc(t) { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; }

  function ago(seconds) {
    if (seconds < 90) return seconds + "s ago";
    if (seconds < 5400) return Math.round(seconds / 60) + "m ago";
    if (seconds < 129600) return Math.round(seconds / 3600) + "h ago";
    return Math.round(seconds / 86400) + "d ago";
  }

  function stateBadge(state) {
    if (state === "waiting") return '<span class="chip state-waiting">needs input</span>';
    if (state === "working") return '<span class="chip state-working">working</span>';
    return '<span class="chip">idle</span>';
  }

  function chatLine(s, withProject) {
    const name = s.title || "untitled chat";
    let html = `<div class="dash-chat ${s.state}">`;
    html += stateBadge(s.state);
    html += `<span class="dash-chat-title">${esc(name)}</span>`;
    if (s.branch) html += `<span class="chip">${esc(s.branch)}</span>`;
    if (withProject) html += `<span class="muted">${esc(withProject)}</span>`;
    html += `<span class="muted" style="margin-left: auto; white-space: nowrap;">${ago(s.age_seconds)}</span>`;
    html += `</div>`;
    if (s.snippet) html += `<div class="dash-snippet">${esc(s.snippet)}</div>`;
    return html;
  }

  function projectCard(p) {
    const sessions = p.sessions || [];
    let html = `<div class="dash-card ${p.state}">`;
    html += `<div class="dash-card-head"><strong>${esc(p.name)}</strong>${stateBadge(p.state)}</div>`;
    html += `<div class="muted dash-path">${esc(p.path)}</div>`;
    sessions.forEach(s => { html += chatLine(s, ""); });
    if (p.beads) {
      const b = p.beads;
      html += `<div class="dash-line">beads: ${b.in_progress} in progress, ${b.open} open${b.blocked ? ", " + b.blocked + " blocked" : ""}</div>`;
      (b.in_progress_titles || []).forEach(t => {
        html += `<div class="dash-bead">&#9656; ${esc(t)}</div>`;
      });
    }
    if (p.tracker_project) {
      html += `<div class="dash-line"><a href="/project/${p.tracker_project.id}">Board: ${esc(p.tracker_project.name)}</a> · <a href="#" class="link-btn" data-path="${esc(p.path)}" data-name="${esc(p.name)}" data-linked="${p.tracker_project.id}">change</a></div>`;
    } else {
      html += `<div class="dash-line"><a href="#" class="link-btn" data-path="${esc(p.path)}" data-name="${esc(p.name)}">Connect to a board</a></div>`;
    }
    html += "</div>";
    return html;
  }

  async function refresh() {
    let data;
    try {
      const resp = await fetch("/api/connectors/claude-code");
      if (!resp.ok) throw new Error(resp.status);
      data = await resp.json();
    } catch (e) {
      document.getElementById("dash-updated").textContent = "connection lost, retrying...";
      return;
    }
    const machines = data.machines || [];
    document.getElementById("dash-empty").hidden = machines.length > 0;

    // Chats waiting for input float to the top, across every machine.
    const waiting = [];
    machines.forEach(m => (m.projects || []).forEach(p =>
      (p.sessions || []).forEach(s => {
        if (s.state === "waiting") waiting.push({ s, where: p.name + (machines.length > 1 ? " on " + m.machine : "") });
      })
    ));
    waiting.sort((a, b) => a.s.age_seconds - b.s.age_seconds);
    const needs = document.getElementById("dash-needs-input");
    needs.hidden = waiting.length === 0;
    needs.innerHTML = `<h2>Needs input (${waiting.length})</h2>` +
      waiting.map(w => chatLine(w.s, w.where)).join("");

    grid.innerHTML = machines.map(m => {
      const order = { waiting: 0, working: 1, idle: 2 };
      const projects = (m.projects || []).slice().sort((a, b) => order[a.state] - order[b.state]);
      return `<section class="dash-machine">` +
        `<h2>${esc(m.machine)} <span class="muted" style="font-weight: 400; font-size: 0.8rem;">` +
        `${m.stale ? '<span class="chip state-waiting">stale</span> ' : ""}reported ${ago(m.age_seconds)}</span></h2>` +
        `<div class="dash-cards">${projects.map(projectCard).join("") || '<p class="muted">No recent Claude Code activity.</p>'}</div>` +
        `</section>`;
    }).join("");
    document.getElementById("dash-updated").textContent =
      "updated " + new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
  }

  grid.addEventListener("click", (e) => {
    const btn = e.target.closest(".link-btn");
    if (!btn) return;
    e.preventDefault();
    form.path.value = btn.dataset.path;
    form.dataset.linked = btn.dataset.linked || "";
    form.project_id.value = btn.dataset.linked || "";
    document.getElementById("link-repo-name").textContent = btn.dataset.name;
    dialog.showModal();
  });

  document.getElementById("link-cancel").addEventListener("click", () => dialog.close());

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const projectId = form.project_id.value;
    const previous = form.dataset.linked;
    try {
      if (previous && previous !== projectId) {
        await fetch(`/api/projects/${previous}/claude-link`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ claude_path: "" }),
        });
      }
      if (projectId) {
        await fetch(`/api/projects/${projectId}/claude-link`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ claude_path: form.path.value }),
        });
      }
      dialog.close();
      refresh();
    } catch (err) { alert("Connect failed: " + err.message); }
  });

  refresh();
  setInterval(refresh, 15000);
})();
