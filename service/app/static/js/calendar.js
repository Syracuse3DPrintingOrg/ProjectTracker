/* Calendar page: month grid of due dates, filterable by project. */
(function () {
  "use strict";

  const grid = document.getElementById("calendar");
  const title = document.getElementById("cal-title");
  let current = new Date();
  current.setDate(1);

  const MONTHS = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function iso(d) {
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  function esc(t) { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; }

  function selectedProjects() {
    const boxes = [...document.querySelectorAll(".cal-project")];
    const picked = boxes.filter(b => b.checked).map(b => b.value);
    return picked.length === boxes.length ? "" : picked.join(",");
  }

  async function render() {
    const year = current.getFullYear(), month = current.getMonth();
    title.textContent = MONTHS[month] + " " + year;

    // Grid runs Monday to Sunday, padded to full weeks.
    const first = new Date(year, month, 1);
    const start = new Date(first);
    start.setDate(1 - ((first.getDay() + 6) % 7));
    const last = new Date(year, month + 1, 0);
    const end = new Date(last);
    end.setDate(last.getDate() + (7 - ((last.getDay() + 6) % 7 + 1)) % 7);

    let cards = [];
    try {
      const params = new URLSearchParams({ start: iso(start), end: iso(end) });
      const projects = selectedProjects();
      if (projects) params.set("projects", projects);
      const resp = await fetch("/api/calendar?" + params);
      if (resp.ok) cards = await resp.json();
    } catch (e) { /* render an empty grid */ }

    const byDate = {};
    cards.forEach(c => { (byDate[c.due_date] = byDate[c.due_date] || []).push(c); });

    const today = iso(new Date());
    let html = DAYS.map(d => `<div class="cal-dow">${d}</div>`).join("");
    const cursor = new Date(start);
    while (cursor <= end) {
      const day = iso(cursor);
      const faded = cursor.getMonth() !== month ? "faded" : "";
      const now = day === today ? "today" : "";
      const items = (byDate[day] || []).map(c =>
        `<a class="cal-card ${c.done ? "done" : ""} p${c.priority} ${day < today && !c.done ? "overdue" : ""}"` +
        ` href="/project/${c.project_id}" title="${esc(c.title)} (${esc(c.project_name)} · ${esc(c.status)})">` +
        `${esc(c.title)}</a>`
      ).join("");
      html += `<div class="cal-day ${faded} ${now}"><div class="cal-date">${cursor.getDate()}</div>${items}</div>`;
      cursor.setDate(cursor.getDate() + 1);
    }
    grid.innerHTML = html;
  }

  document.getElementById("cal-prev").addEventListener("click", () => { current.setMonth(current.getMonth() - 1); render(); });
  document.getElementById("cal-next").addEventListener("click", () => { current.setMonth(current.getMonth() + 1); render(); });
  document.getElementById("cal-today").addEventListener("click", () => { current = new Date(); current.setDate(1); render(); });

  const all = document.getElementById("cal-all");
  all.addEventListener("change", () => {
    document.querySelectorAll(".cal-project").forEach(b => { b.checked = all.checked; });
    render();
  });
  document.querySelectorAll(".cal-project").forEach(b => b.addEventListener("change", () => {
    const boxes = [...document.querySelectorAll(".cal-project")];
    all.checked = boxes.every(x => x.checked);
    render();
  }));

  render();
})();
