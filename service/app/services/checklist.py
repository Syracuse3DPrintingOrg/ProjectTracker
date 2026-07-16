"""Markdown checklists inside card descriptions.

A checklist item is a line like "- [ ] buy paint" or "- [x] sand the
door". The description stays plain text (the AI subtask button already
writes this shape); these helpers parse and toggle items without
disturbing anything else in the text.
"""

import re

_ITEM = re.compile(r"^(\s*[-*]\s*\[)([ xX])(\]\s*)(.*)$")


def parse_checklist(description: str) -> list[dict]:
    """All checklist items in order: {line, text, checked}."""
    items = []
    for i, line in enumerate(description.splitlines()):
        m = _ITEM.match(line)
        if m:
            items.append(
                {"line": i, "text": m.group(4).strip(), "checked": m.group(2) in "xX"}
            )
    return items


def progress(description: str) -> tuple[int, int]:
    """(done, total) across the description's checklist items."""
    items = parse_checklist(description)
    return sum(1 for i in items if i["checked"]), len(items)


def toggle_item(description: str, index: int, checked: bool) -> str | None:
    """Set the index-th checklist item; returns the new description, or
    None when the index does not point at an item."""
    items = parse_checklist(description)
    if index < 0 or index >= len(items):
        return None
    target_line = items[index]["line"]
    lines = description.splitlines()
    m = _ITEM.match(lines[target_line])
    lines[target_line] = f"{m.group(1)}{'x' if checked else ' '}{m.group(3)}{m.group(4)}"
    trailing = "\n" if description.endswith("\n") else ""
    return "\n".join(lines) + trailing
