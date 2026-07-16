# Changelog

## [Unreleased]

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
