# Changelog

## [Unreleased]

## [0.9.0] - 2026-07-16

### Added

- **Home Assistant integration.** A new `/api/ha/summary` endpoint feeds
  HA REST sensors: today's remaining count, the task list, overdue
  cards, per-project open counts, and your stalest neglected project.
  Ready-to-paste configuration (sensors, TV display pop-up commands,
  card-creating rest_commands, and a cheeky leaving-home reminder
  automation) ships in `homeassistant/sq.yaml`.
- **API keys.** Create keys under Settings for Home Assistant and
  scripts: each has a name and a role (member acts, viewer reads,
  neither administers), is sent as an `X-API-Key` header, and is shown
  exactly once. Revoke instantly from the same table.
- **Members can pop up displays.** Triggering a TV display (show, hide,
  sleep) now needs only member rights, so automations and family members
  can put the list on screen; display configuration stays admin-only.

## [0.8.0] - 2026-07-16

### Added

- **Real user accounts.** SQ now supports multiple people on one
  instance. Manage users under Settings: everyone gets a username,
  password, and a role. Admins run the show (settings, users, displays,
  backups), members have full board access, viewers can look but not
  touch. Everyone shares the same boards and Today list.
- **Your account page.** Click your name in the top bar to change your
  password. Changing it signs you out everywhere, on purpose.
- **Safe upgrade.** An instance with the old single password keeps
  working: that password becomes the "admin" account. An instance with
  no password stays open until you add your first user (who must be an
  admin). Wall displays and the Claude Code connector keep using their
  own tokens, so no screen goes dark over this.

### Changed

- **Login asks for a username now.** If you upgraded from the single
  password, your username is "admin".

## [0.7.0] - 2026-07-16

### Added

- **Recurring cards.** Set a card to repeat (daily, weekly, monthly, and
  friends) and finishing it sends it back to the start of the board with
  a fresh due date and an unticked checklist. Perfect for the chores that
  are never actually done.
- **Plan my day.** One button on the Today rail asks your AI to pick 3
  to 6 tasks from everything open, favoring overdue and due-soon work,
  and drops them on the Today list (and your wall displays).
- **Work-in-progress limits.** Give any column a cap from its menu
  ("limit 3") and the header shows 2/3; blow past it and the column turns
  red. The squirrel says nothing, but you know.
- **Install it like an app.** SQ now has a proper icon and web app
  manifest, so a phone or tablet can pin it to the home screen and run
  it full screen.

## [0.6.1] - 2026-07-16

### Fixed

- **The mystery orange bar.** An empty nudge banner (just a squirrel, no
  message) showed on every board even when there was nothing to nag
  about. It now only appears when it actually has something to say.

### Changed

- **Sharper, darker, punchier.** Corners are crisp instead of rounded
  (the menu pills keep their shape), the background is nearly black, and
  borders and text got a contrast bump. Chips are squared off to match.

## [0.6.0] - 2026-07-16

### Added

- **This tracker has a name now: SQ.** Short for Squirrel, because we both
  know why you have this many projects. New identity across the app, plus
  a fresh dark theme: deep space background, violet-to-cyan accents, and a
  little glow where it counts.
- **Project status.** Every project is Chasing (&#128063;), Buried for
  later (&#127793;), or Cracked it (&#9989;), set right from the board
  header. Buried and Cracked projects are left in peace.
- **Squirrel discipline.** Start a new project while others still have
  open cards and SQ asks, politely, if you really want to chase the shiny
  thing (with a list of what you'd be abandoning). Boards also show a
  gentle nudge about your stalest open project: dismiss it, or click
  through and go finish something.

## [0.5.0] - 2026-07-16

### Added

- **Every chat on the Claude Code dashboard.** Repo cards now list each
  chat by name (the title you gave it, or its generated name) with its
  branch, state, and how long ago it was active. Chats waiting on you
  show Claude's last message, so you can tell what the question is
  without switching windows.
- **Needs input floats to the top.** A highlighted section above the
  machine cards collects every chat that is waiting for input, across
  all machines, most recent first.

## [0.4.0] - 2026-07-16

### Added

- **Claude Code dashboard.** A new Claude Code pill in the top menu shows
  what Claude is doing on your development machines: which repos have
  active sessions, which are working versus waiting for your input, and
  each repo's beads issue tracker at a glance (in progress, open,
  blocked, with the in-progress titles). Repos waiting for input sort
  first and are highlighted.
- **The connector.** One small script
  (`scripts/claude-code-connector.py`, standard library only) runs on
  each dev machine and posts a status snapshot to the tracker every
  minute. It reads Claude Code's local session files and each repo's
  beads export; get the ready-made command, token included, from the
  dashboard when no machine reports yet. `--install` sets it up as a
  systemd user service.
- **Connect boards to repos.** Link a tracker project to a Claude Code
  repo from its board (the Connect Claude button) or from the dashboard.
  A linked board shows a live status chip (working, waiting, idle) and
  the dashboard links straight back to the board.

### Changed

- **The top menu is now pills.** Boards, Today, Calendar, Claude Code,
  and Displays sit in the top bar as pill buttons with the current page
  highlighted; search and Settings stay on the right.

## [0.3.0] - 2026-07-16

### Added

- **Checklists on cards.** Lines like "- [ ] sand the door" in a card's
  description become a real checklist: tick items off in the card dialog,
  see progress ("2/5") on the board, in search results, and on wall
  displays. The AI subtask button already writes this shape, so its
  output is now clickable.
- **Search.** The magnifier in the top bar searches titles, descriptions,
  and labels across every project. The board also gets a filter box that
  narrows cards as you type.
- **Backup and restore.** Download everything as one JSON file from
  Settings and restore it there too. Restoring replaces all boards, so it
  asks first.

## [0.2.0] - 2026-07-16

### Added

- **Calendar view.** A month grid of everything with a due date, across
  all projects or just the ones you tick in the filter. Overdue cards
  stand out, finished ones are crossed off, and clicking a card jumps to
  its board.
- **A real Displays page.** Register each wall screen (Pi kiosk, Android
  TV, ESP32) under Displays in the top nav: every display gets its own
  URL and its look (theme, text size, clock, TV overscan margins, hide
  finished tasks) is managed from the tracker, not on the device.
- **Pop up on Android TV.** Add a TV with its IP address, press Show, and
  the tracker wakes the TV and opens the display on it over network
  debugging. Hide sends it back home. Enable Developer options and
  Network debugging on the TV once; the first Show asks you to allow the
  connection on screen.
- **One-command Raspberry Pi kiosk.** `scripts/pi-display-setup.sh` turns
  a stock Raspberry Pi OS install into a display that boots straight into
  the list, waits for the tracker before starting, restarts if anything
  crashes, and supports rotated screens.
- **Nicer display page.** Light, dark, and high-contrast themes, a clock,
  a progress bar, overdue highlighting, and it only repaints when the
  list actually changes.
- **T-Display example.** A ready-to-flash ESPHome config for the LILYGO
  TTGO T-Display with paging by button, alongside the generic ESP32
  example.

## [0.1.0] - 2026-07-16

### Added

- **The tracker itself.** Kanban boards with drag-and-drop cards and
  statuses, multiple projects, priorities, due dates, and labels. Runs as
  one small container with a single data folder to back up.
- **Today's Tasks.** Drag a card onto the Today rail and it shows up on
  your wall displays: a full-screen page at `/display` for a Raspberry Pi,
  and compact JSON at `/api/display` for an ESP32 (ESPHome example
  included).
- **AI assist.** Break a card into subtasks or draft its description.
  Works with Google Gemini out of the box, or Anthropic Claude, OpenAI,
  and local Ollama; the buttons only appear once a provider is configured.
- **Optional password.** The app is open on a trusted network by default;
  set a password in Settings and displays switch to token access.
