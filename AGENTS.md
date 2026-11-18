# SQ (Project Tracker): Agent Instructions

Canonical instructions for every AI agent working in this repo. `CLAUDE.md`
is just a pointer to this file; edit here, not there.

## What This Is

**SQ** (short for Squirrel, a joke about chasing shiny new projects) is a
lightweight, self-hosted project tracker: FastAPI plus SQLite, one
container, port 9280. The brand is SQ and the voice is cheeky (squirrel
jokes, gentle guilt); **internal identifiers stay `projecttracker`** (the
repo name, container name, image tag, and the `/health` `app` field), the
same lesson as PantryRaider's foodassistant plumbing: renaming them breaks
deployments for no user benefit. Kanban boards with drag-and-drop cards, a Today's
Tasks list that feeds wall displays (`/display` for a Raspberry Pi
browser, `/api/display` compact JSON for an ESP32), and optional LLM
assist (Gemini default; Anthropic, OpenAI, Ollama). Multi-user with three
roles (admin, member, viewer) behind optional logins; boards and the
Today list are shared by everyone on the instance.

## Repository Map

| Path | What lives there |
|---|---|
| `service/app/` | The FastAPI app: `main.py`, `config.py`, `database.py`, `routers/`, `services/`, `templates/`, `static/` |
| `tests/` | Pure-logic pytest suite (temp SQLite per test, no network or Docker needed) |
| `examples/` | ESPHome config for an ESP32 status display |
| `Dockerfile`, `docker-compose.yml` | Deployment (Unraid or any Docker host) |

## Architecture Notes

- `config.py`: settings merged from defaults, `data/settings.json` (written
  by the Settings page), and env overrides. `_SAVEABLE` lists persistable
  keys; `APP_VERSION` lives here and is the single source of truth.
- `database.py`: plain sqlite3, short-lived connections, schema created at
  startup. No ORM on purpose; keep it that way unless the schema outgrows it.
- `services/store.py`: all board logic. Ordering renumbers integer
  positions on every move; simple beats clever for a single-user board.
- `services/llm.py`: providers called over plain HTTP with httpx, no SDKs.
  LLM JSON replies may be fenced; always parse with `parse_json_response`.
- Auth is optional: no password means open on the LAN. Display endpoints
  accept `?token=...` so wall screens never need a login flow.
- `/api/settings` applies only the fields present in the request, so each
  Settings section saves without clobbering the others. Blank API key
  fields keep the stored secret.
- Frontend is server-rendered Jinja2 plus small vanilla JS files; the only
  vendored dependency is SortableJS. Do not add a build step, a framework,
  or a CDN dependency; the app must work on a LAN with no internet.
- Templates get an `ai_configured` flag; gate AI-only UI on it so the app
  never offers actions that cannot work without a provider.

## Writing Style

Applies to ALL project content: code comments, docs, README, CHANGELOG,
commit messages, and UI copy.

- No em-dashes. Use commas, parentheses, colons, or rewrite the sentence.
- No ASCII line or box diagrams.
- The goal is copy that reads as human-written; avoid LLM tells generally.
- Docs and UI copy are user-forward: written for the app's end user, not
  as notes to the developer, and never describing the software from the
  builder's side.

## Build and Test

```bash
docker compose up -d --build          # run

# tests (pure logic, no network or Docker needed):
pip install -r service/requirements.txt pytest
python -m pytest tests/ -q

# import smoke test:
python -c "import sys; sys.path.insert(0,'service'); from app.main import app"
```

**Definition of done:** before handing off a code change, run the test
suite and the import smoke test. A user-facing change also needs a
CHANGELOG entry (see Versioning).

## Deploying Without the Registry

While the image publish workflow is blocked, a release reaches a Docker
host with `scripts/deploy.sh <ssh-target> <host-data-dir> [port]`. Run it
on a machine with Docker (image builds belong on the task server, not the
dev VM). It ships the image over SSH, backs up the data folder next to it
under `backups/` (last five kept), keeps the old container's environment,
waits for `/health` to report the new version, and restores the old image
if it does not. Where production runs and its data path are recorded in
the owner's inventory, not here: this repo is public.

## Versioning

- `APP_VERSION` in `service/app/config.py` is the single source of truth
  (major.minor.patch). Pre-1.0 until the tracker is feature-stable.
- Every user-facing change gets a CHANGELOG entry under `[Unreleased]` in
  the appropriate Added/Changed/Fixed section, written in plain prose for
  users, not developers.

## Authorship and Git

- All commits are authored by Dan's GitHub identity
  (`Syracuse3DPrinting <dm.marafino@gmail.com>`); the repo git config is
  already set, do not change it. Never add Co-Authored-By trailers, AI
  attributions, or session links to commit messages.
- Development happens on `main` directly.
- Commit and push are part of done: an unpushed change has not shipped.
  Do not wait to be asked. The one exception is small conversational
  tweaks Dan asks for while just chatting, which may be left uncommitted
  for his review unless he says ship it.
- Track follow-up work in beads (`bd create`, prefix `SQ`); the beads
  section below has the workflow. GitHub issues are for outside
  reporters, not our own tracking.

## Non-Interactive Shell Commands

ALWAYS use non-interactive flags with file operations. `cp`, `mv`, and
`rm` may be aliased to `-i` on some systems, which hangs an agent waiting
for y/n input. Use `cp -f`, `mv -f`, `rm -f` (and `-rf` for recursive
operations). Similarly: `scp`/`ssh` with `-o BatchMode=yes`, `apt-get -y`,
and `HOMEBREW_NO_AUTO_UPDATE=1` for `brew`.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking; do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge; do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
