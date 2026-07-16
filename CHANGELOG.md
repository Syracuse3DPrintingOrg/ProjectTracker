# Changelog

## [Unreleased]

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
