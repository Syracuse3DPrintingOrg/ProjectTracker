# Project Tracker

A lightweight, self-hosted project tracker: drag-and-drop cards on a kanban
board, a Today's Tasks list, and status displays for a wall screen or an
ESP32. One Python service, one SQLite file, no accounts to create.

## Features

- **Boards**: multiple projects, each with its own status columns (Backlog,
  To Do, In Progress, Done by default; rename, add, and reorder freely).
- **Cards**: title, description, priority (P0 to P4), due date, labels,
  and checklists ("- [ ] step" lines become tickable items with progress
  shown on the board). Drag cards between columns or reorder within one,
  on desktop or touch.
- **Search and filter**: search every project from the top bar; filter
  the board as you type.
- **Today's Tasks**: drag any card onto the Today rail and it appears on
  your wall displays. Cards that reach a done column can be cleared from
  the list in one click.
- **Calendar**: a month view of everything with a due date, across all
  projects or a filtered set. Overdue cards stand out; finished ones are
  crossed off.
- **Status displays**: register each screen on the Displays page and
  manage its look (theme, text size, clock, overscan margins) from the
  tracker.
  - A **Raspberry Pi** (3B+ is plenty) boots straight into the display:
    run [`scripts/pi-display-setup.sh`](scripts/pi-display-setup.sh) on a
    stock Raspberry Pi OS install with the display URL.
  - An **Android TV** can be popped up remotely: enable Network debugging
    on the TV, add it with its IP, and press Show. The tracker wakes the
    TV and opens the display over ADB.
  - An **ESP32** polls `/api/display`, a compact JSON payload built for
    microcontrollers. ESPHome examples:
    [`examples/esphome-tdisplay.yaml`](examples/esphome-tdisplay.yaml)
    (LILYGO T-Display, with button paging) and
    [`examples/esphome-display.yaml`](examples/esphome-display.yaml)
    (generic).
- **AI assist** (optional): break a card into subtasks or draft its
  description. Google Gemini by default; Anthropic Claude, OpenAI, and
  local Ollama also work. Configure a key on the Settings page and the
  assist buttons appear; without one they stay hidden.
- **Single user**: no login by default (fine on a trusted LAN). Set a
  password in Settings if the box is reachable from outside; wall displays
  then authenticate with a token instead of a login.
- **Backup**: one JSON download from Settings holds everything and
  restores in place.
- **Claude Code dashboard**: see what Claude Code is doing across your
  machines: active repos, sessions working versus waiting for input, and
  each repo's beads issue counts. Run
  [`scripts/claude-code-connector.py`](scripts/claude-code-connector.py)
  on each dev machine (the dashboard hands you the exact command and
  token) and link repos to boards for a live status chip on the board.

## Run it

```bash
docker compose up -d --build
```

Open http://localhost:9280 and create your first project. All data lives in
`./data` (a SQLite database plus `settings.json`), so back that folder up
and you have everything.

Without Docker:

```bash
pip install -r service/requirements.txt
cd service && uvicorn app.main:app --host 0.0.0.0 --port 9280
```

### Unraid

Add a container from the `Dockerfile` (or `docker compose up` on the
command line), map port 9280 and a path to `/data`. Nothing else is
required.

## Configuration

Everything is set from the Settings page and stored in `data/settings.json`.
Environment variables override saved settings:

| Variable | Meaning |
|---|---|
| `TRACKER_DATA_DIR` | Data directory (default `data`, `/data` in Docker) |
| `GEMINI_API_KEY` | Gemini key for AI assist |
| `ANTHROPIC_API_KEY` | Anthropic key |
| `OPENAI_API_KEY` | OpenAI key |
| `OLLAMA_URL` | Ollama server URL |
| `TRACKER_LLM_PROVIDER` | `gemini` (default), `anthropic`, `openai`, `ollama` |
| `TRACKER_LLM_MODEL` | Model override (blank uses a sensible default) |
| `TRACKER_TITLE` | App title shown in the header |

## Display API

`GET /api/display` returns the Today's Tasks list:

```json
{
  "app": "projecttracker",
  "version": "0.1.0",
  "generated_at": "2026-07-16T12:00:00Z",
  "count": 3,
  "remaining": 2,
  "tasks": [
    {"id": 7, "title": "Water the plants", "project": "Home",
     "status": "To Do", "done": false, "priority": 2, "due": ""}
  ]
}
```

When a password is set, displays append `?token=...` (generate the token
under Settings, Wall displays).

## Tests

```bash
pip install -r service/requirements.txt pytest
python -m pytest tests/ -q
```
