# Boards and cards

A board is where a project lives: one column per status, one card per task, and a squirrel keeping score.

## Projects

The dropdown at the top left of every board switches between your projects. Next to it:

- **New project** creates a board with the default columns (Backlog, To Do, In Progress, Done). If other projects still have open cards, SQ first shows you a "SQUIRREL!" warning listing what you would be abandoning. You can chase the shiny thing anyway; it just wants you to know.
- **Rename** changes the project's name.
- **Archive** takes the project off your board list. Its cards leave the board but nothing is deleted.
- **Overview** opens the project's overview page (see below).

Every project also has a status, set right from the board header:

- **Chasing**: you are actively on it.
- **Buried for later**: parked on purpose. SQ stops judging.
- **Cracked it**: finished. Marking a project Cracked earns you a congratulation and a guilt-free license to start something new.

Buried and Cracked projects are left in peace: they never appear in the nudges below, and they get a little marker in the project dropdown so you can tell them apart at a glance.

### The squirrel nudge

When some other Chasing project has open cards and has not moved in three days or more, the board shows a gentle banner about your stalest one, with a link to go finish it. Dismissing it keeps it quiet for the rest of your browser session. It never blocks anything; it just remembers.

## Columns

Columns are your statuses. **+ Add status** at the right end of the board adds one, and dragging a column by its header reorders the board.

The three-dot menu on a column header does everything else. It asks for one of:

- a new name, to rename the column
- `done`, to toggle the column's finished flag
- `limit N`, to set a work-in-progress cap (`limit 0` removes it)
- `delete`, to remove the column (it must be empty first)

A **done column** is where finished work lands. Cards there count as finished everywhere: on the Today list, on the overview page, and for recurring cards (see below). The default board's Done column already has the flag.

### Work-in-progress limits

Give a column a cap and its header shows the count against it, like `2/3`. Go over and the column turns red. Nothing is blocked; the squirrel says nothing, but you know.

## Cards

**+ Add card** at the bottom of a column creates a card; clicking any card opens it. A card carries:

- **Title** and **description**.
- **Priority**, P0 critical through P4 someday. P2 is normal and shows no chip; anything else shows a `P0` to `P4` chip on the card.
- **Due date**. The date shows as a chip and turns red once it is past.
- **Repeats**: never, daily, every 2 days, weekly, every 2 weeks, or monthly-ish.
- **Labels**, comma separated, each shown as a chip.
- **Assignee**, when your instance has user accounts. The card shows an initials chip, and assignments land in the activity feed.

Drag cards between columns, or reorder them within one. It works with a mouse or a finger.

### Checklists

Lines like `- [ ] sand the door` in a card's description become a real checklist: tick items off in the card dialog, and the card shows progress like `2/5` on the board. When every item is ticked, the chip changes to show the list is complete.

### Subtasks

Cards can carry subtasks, and subtasks are real cards: each has its own description, attachments, comments, and due date. In the card dialog you can add a subtask, click its title to rename it, tick it done, open it as its own card, or delete it.

On the board, a card with subtasks shows a count badge like `1/3 subtasks`. Click the badge and the subtasks unfold right under the parent, collapsed again with another click; SQ remembers which ones you had open for the rest of your session.

Nesting is drag and drop too:

- Drag a card onto another card and it becomes that card's subtask.
- Drag a subtask out into a column and it becomes a full card again.
- Subtasks go one level deep: a card that has subtasks of its own cannot become a subtask.

Deleting a card with subtasks does not delete them; they are promoted to cards of their own.

### Recurring cards

A card set to repeat comes back. Finish it (drag it into a done column, or tap it done on a kiosk) and it respawns at the start of the board with a fresh due date, an unticked checklist, and a clean slate on the Today list. Perfect for the chores that are never actually done.

### Comments and activity

Every card keeps a trail: created, moved, assigned, files attached, and (for recurring cards) sent back around. The card dialog shows the feed with a comment box at the bottom; anyone with member access can post.

### Attachments

Drop files onto a card, on the board or in its dialog, and preview most of them right in the page. The full story is in [Attachments and previews](attachments-and-previews.md).

## Quick filter

The filter box at the top right of the board narrows cards as you type, matching titles, labels, and assignee names. The magnifier in the top bar searches across every project instead.

## The overview page

The **Overview** button on a board opens the project's overview: a description you can edit in place, headline counts (open tasks, finished, files, days quiet), the open tasks with their status, owner, due date, and subtask progress, the finished work tucked into a collapsible list, every file attached anywhere in the project (click one to preview it), and the recent activity across all its cards.

It is the page to send someone who asks "so how is that project going," assuming you are brave enough to look yourself.


## My work

The My work entry in the top menu gathers every open card assigned to
you across all active projects, grouped by project and sorted by due
date and priority. It is the "what should I be doing" page; the Today
list stays the "what am I doing today" page.

## Reports

Every project overview includes a Reports panel: bars for how many
cards you finished each of the last eight weeks, the average age of
what is still open, and a live count per column. No sprint ceremonies
required.


## Simple lists

Some things are a shopping list, not a project. When you create a
project you can pick a simple list instead of a board: one flat page
with an add box at the top, tickable rows, checked items sinking below,
and a Clear checked button. List items are real cards underneath, so
you can still drag one onto Today, see it on a wall display, and find
it in search. The project switcher marks lists with a checkbox icon.

## Right-click menus

The board speaks right-click. Cards offer open, Today, assign, move,
make subtask of, archive, send to AI, and delete; column headers offer
rename, WIP limit, the done-column toggle, archive finished, and
delete; empty board space offers new cards, columns, projects, and
lists. On a touch screen, long-press does the same thing.
