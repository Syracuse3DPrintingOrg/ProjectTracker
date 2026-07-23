# Integrations

SQ plays well with others: Home Assistant, your own scripts, and a live view of Claude Code across your machines.

## API keys

Headless callers (Home Assistant, scripts, cron jobs) authenticate with an API key instead of a login. Create one under Settings, Users and Access, API keys: give it a name and a role, **member** to act or **viewer** to only read. Keys are never admins; a headless caller does not manage the instance.

The key itself is shown exactly once, at creation, and only a hash is stored, so copy it then. Send it as an `X-API-Key` header and it flows through the same role checks as a logged-in user; the key list shows when each was last used, and deleting a key revokes it immediately.

```bash
curl -H "X-API-Key: sq_..." http://192.168.1.50:9280/api/today
```

## Home Assistant

Ready-made configuration ships in `homeassistant/sq.yaml`. To wire it up:

1. In SQ: Settings, Users and Access, Create key. Member role covers the rest_commands below; viewer is enough for just the sensors.
2. Put the key in Home Assistant's `secrets.yaml` as `sq_api_key: "sq_..."`.
3. Replace the `192.168.1.50:9280` address in the file with your SQ address (use the LAN address, not a reverse-proxied public one), include the file or paste the pieces into your configuration, and restart Home Assistant.

### The summary sensor

The sensors poll `/api/ha/summary`, one payload with everything worth automating on:

```json
{
  "app": "projecttracker",
  "version": "0.14.1",
  "generated_at": "2026-07-23T12:00:00Z",
  "today_count": 3,
  "today_remaining": 2,
  "today_tasks": [
    {"title": "Water the plants", "project": "Home", "done": false}
  ],
  "overdue": 1,
  "projects": [{"id": 1, "name": "Home", "open_cards": 4}],
  "stalest": {"name": "Bandsaw restore", "open_cards": 6, "days_quiet": 12}
}
```

The bundled config turns that into two entities: **SQ today remaining** (with `today_tasks`, `today_count`, `projects`, and `stalest` as attributes) and **SQ overdue**.

### Service calls

The file also defines three `rest_command` services:

- `sq_show_tv` and `sq_hide_tv` pop the Today list onto a registered Android TV display, or dismiss it, via `/api/displays/{display_id}/tv/show` and `/tv/hide`. Display ids are on the SQ Displays page (the `d=` value in each display's URL).
- `sq_add_card` drops a card straight onto a board from an automation: it posts `project_id`, `column_id`, `title`, and an optional `priority` to `/api/cards`.

The file ends with an example automation: when the last person leaves home and Today's tasks remain open, your phone hears about it. The squirrel does not clock out.

## The Claude Code dashboard

If Claude Code works on your machines, SQ can show what it is up to: which repos are active, which sessions are working versus waiting for your input, and each repo's beads issue counts. The dashboard lives at `/dashboard/claude-code`.

Feed it by running `scripts/claude-code-connector.py` on each dev machine; the dashboard and the Settings Hardware pane hand you the exact command with your connector token filled in:

```bash
python3 claude-code-connector.py --url http://192.168.1.50:9280 --token XXXX
```

Every 60 seconds (tune with `--interval`) it scans Claude Code's local session transcripts under `~/.claude/projects` and each repo's `.beads/issues.jsonl`, then posts one small JSON snapshot to the tracker. Nothing else leaves the machine. The script is standard library only; `--once` posts a single snapshot (handy for cron), and `--install` writes a systemd user service so it runs at boot and keeps itself running (run `loginctl enable-linger` so it also reports while you are logged out).

Link a repo to a board from the dashboard and the board gets a live status chip showing what Claude Code is doing in that repo.

## REST API for scripters

Everything the UI does goes through a JSON API under `/api`, and your scripts are welcome to it. When logins are on, send an API key as `X-API-Key`. The main endpoints:

| Endpoint | What it does |
|---|---|
| `GET /api/projects` | List projects (`?include_archived=true` for all) |
| `POST /api/projects` | Create a project: `{"name": "..."}` |
| `GET /api/projects/{id}/board` | Project, columns, and cards in one call |
| `POST /api/cards` | Create a card: `project_id`, `column_id`, `title`, plus optional `description`, `labels`, `priority` (0 to 4), `due_date`, `recur_days` |
| `PATCH /api/cards/{id}` | Edit any card field |
| `POST /api/cards/{id}/move` | Move a card: `{"column_id": 5, "position": 0}` |
| `GET /api/cards/{id}/subtasks`, `POST ...` | List or add subtasks |
| `POST /api/cards/{id}/today` | Put a card on the Today list or take it off: `{"today": true}` |
| `GET /api/today?list=shared` | The Today list; `list=mine` for the signed-in user's personal list |
| `POST /api/today/clear-done` | Clear finished tasks off the Today list |
| `GET /api/kiosk/data` | Everything the kiosk shows: tasks, overdue, due soon, stalest project |
| `POST /api/kiosk/toggle/{card_id}` | Toggle a task done, or back again |
| `GET /api/display` | The compact Today payload built for microcontrollers |
| `GET /api/search?q=...` | Search titles, descriptions, and labels across projects |
| `GET /api/export` | The full JSON backup (admin only) |
| `POST /api/import` | Restore from a backup, replaces everything (admin only, requires `"confirm": true`) |
| `GET /api/cards/{id}/handoff` | The card packed as a self-contained AI prompt, as JSON |

Note that export, import, and the other administrative endpoints need an admin login; API keys top out at member, so backups stay a person's job.
