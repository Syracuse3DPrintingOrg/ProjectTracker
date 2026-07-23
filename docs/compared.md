# How SQ compares

SQ covers the features people actually use in Trello, Jira, and Asana,
skips the enterprise weight, and adds a few things none of them have.
This page maps it out honestly.

## Feature map

| You know it as | In SQ |
|---|---|
| Trello boards, lists, cards | Boards, columns (statuses), cards, drag and drop |
| Jira subtasks | Subtasks that nest under the parent card, drag to nest or promote |
| Checklists | Checklist lines in the description plus real subtasks |
| Jira assignee, Trello members | One assignee per card, initials chip, My work page |
| Labels | Comma-separated labels, filterable |
| Priorities | P0 to P4 |
| Due dates and calendar | Due dates, overdue highlighting, a month calendar across projects |
| Comments and history | Comments plus an automatic activity trail on every card |
| Notifications | Mentions, assignments, and comment alerts in the bell; optional push to your own ntfy topic or webhook |
| Trello Butler recurring cards | Recurrence built into any card; finished recurring cards respawn |
| Jira WIP limits | Per-column limits with a red flag when you blow past them |
| Attachments | Any file on any card, with previews most tools cannot match: office files, PDF, video, audio, and 3D models incl. STEP rendered in the page |
| Reports | Finished-per-week bars, open-card aging, and column counts on every project overview |
| Trello import | Paste a Trello board export into Backup and Restore; lists, cards, checklists, and labels come across |
| Roles and permissions | Three roles: admin, member, viewer |
| API | REST endpoints with role-scoped API keys |

## What SQ has that they do not

- Wall displays: a tap-to-done kiosk for tablets and Raspberry Pis,
  compact JSON for ESP32 screens, and pop-up over ADB on Android TVs.
- A Today's Tasks layer, shared or personal, that those displays follow.
- Home Assistant integration out of the box.
- A dashboard showing what Claude Code is doing across your dev machines.
- AI that works for you on your hardware terms: Gemini, Claude, OpenAI,
  or a local Ollama, plus one-click handoff of any card to an outside AI.
- Squirrel discipline: the tracker itself nags you about the projects
  you abandoned before letting you chase a new one.
- Your data in one folder on your own hardware, exportable as one JSON
  file, with no subscription and no telemetry.

## What SQ skips on purpose

- **Custom fields**: labels, priorities, and due dates cover a household
  or small team; a field designer would not.
- **Automation engines**: recurrence handles the common case, and Home
  Assistant is a far better automation brain than a rules screen inside
  a tracker.
- **Time tracking and sprint ceremonies**: story points, velocity, and
  burndown charts serve managers of managers. The finished-per-week bars
  tell you what you actually want to know.
- **Deep hierarchies**: one level of subtasks, on purpose. If a subtask
  needs subtasks, it wants to be a project.
- **Per-project permissions**: everyone on the instance shares the
  boards. SQ is for people who share a roof or a workshop, not a
  department.

If one of the skipped items is the thing you need, Jira will happily
sell it to you. The squirrel understands.
