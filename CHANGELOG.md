# Changelog

## [Unreleased]

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
