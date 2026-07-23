# Getting started

Everything you need to get SQ running and tracking your first project.

SQ (short for Squirrel) is a lightweight, self-hosted project tracker: a kanban board per project, a Today's Tasks list, wall displays, and a built-in conscience that remembers every project you started. It is one Python service and one SQLite file, running on your own hardware, with no cloud account anywhere.

## Quick start with Docker Compose

Clone the repository and bring the stack up:

```bash
git clone https://github.com/Syracuse3DPrintingOrg/ProjectTracker.git
cd ProjectTracker
docker compose up -d --build
```

Then open http://localhost:9280. The bundled `docker-compose.yml` publishes port 9280 and keeps all data in `./data` next to the compose file.

## Using the published image

If you would rather pull a ready-made image than build one, SQ is published as `ghcr.io/syracuse3dprintingorg/projecttracker`. This `docker run` matches what the compose file sets up:

```bash
docker run -d \
  --name projecttracker \
  -p 9280:9280 \
  -v /path/to/data:/data \
  --restart unless-stopped \
  ghcr.io/syracuse3dprintingorg/projecttracker:latest
```

Point the volume at any folder you like; that folder becomes the tracker's whole world (see below).

## Unraid

Add a container with the image above, map port 9280, and map a path to `/data`. Nothing else is required. Later updates arrive through the container's own Check for Updates button.

## Running without Docker

A plain Python install works too:

```bash
pip install -r service/requirements.txt
cd service && uvicorn app.main:app --host 0.0.0.0 --port 9280
```

Data lands in a `data` folder under the working directory; set `TRACKER_DATA_DIR` to move it.

## Your first project

The first visit greets you with a welcome page. Give your project a name and SQ builds a board with Backlog, To Do, In Progress, and Done columns; rename, add, or reorder statuses whenever you like. Add cards, drag them between columns, and drag anything onto the Today rail to put it on your wall displays. That is the whole loop. The squirrel handles remembering.

## Your first user

Out of the box SQ has no logins at all: anyone on your network can use it, which is fine on a trusted home LAN. To turn logins on, go to Settings, then Users and Access, and add the first user.

The first user must be an admin, and SQ will refuse anything less. Creating that user locks the instance for everyone, so the account that turns the key has to be able to manage settings, users, and backups afterward. From then on SQ also insists on keeping at least one active admin, so you can never lock yourself out by demoting the last one.

Wall displays and other devices are not affected by turning logins on; they authenticate with their own tokens (see the Administration page).

## Where your data lives and what to back up

Everything is in the data folder (`./data` with the bundled compose file, `/data` inside the container):

| Item | What it holds |
|---|---|
| `tracker.db` | The SQLite database: projects, columns, cards, users, API keys, activity |
| `settings.json` | Everything saved from the Settings page, including AI keys and device tokens |
| `secret_key` | The key that signs login sessions |
| `attachments/` | Every file attached to a card |

Back up that one folder and you have everything. Settings also offers a one-click JSON download of your projects, columns, and cards; it is handy for moving boards around, but it is not the full picture (see Backup and restore on the Administration page).
