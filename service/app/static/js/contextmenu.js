/* SQMenu: one small right-click menu for the whole app. No dependencies.
   window.SQMenu.open(x, y, items) where items is a list of
   { label, danger, disabled, children, onclick } rows and { sep: true }
   separators. Children render as a fly-out submenu on hover or tap.
   The menu clamps to the viewport and closes on Escape, click-away,
   scroll, resize, or picking an item. Arrow keys plus Enter also work. */
(function () {
  "use strict";

  /* Open menus, root first, deepest submenu last. */
  let stack = [];
  let bound = false;

  function insideMenu(node) {
    return !!(node instanceof Element && node.closest(".sq-menu"));
  }

  function closeAll() {
    stack.forEach(el => el.remove());
    stack = [];
    if (bound) {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", closeAll);
      window.removeEventListener("blur", closeAll);
      bound = false;
    }
  }

  /* Remove every submenu deeper than the given menu. */
  function closeBelow(menu) {
    const i = stack.indexOf(menu);
    if (i < 0) return;
    stack.slice(i + 1).forEach(el => el.remove());
    stack = stack.slice(0, i + 1);
  }

  function onPointerDown(e) {
    if (!insideMenu(e.target)) closeAll();
  }

  function onScroll(e) {
    /* A long menu may scroll itself; only outside scrolling closes it. */
    if (!insideMenu(e.target)) closeAll();
  }

  function rows(menu) {
    return [...menu.querySelectorAll(".sq-menu-item:not(:disabled)")];
  }

  function onKeyDown(e) {
    if (!stack.length) return;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeAll();
      return;
    }
    const menu = stack[stack.length - 1];
    const items = rows(menu);
    if (!items.length) return;
    const active = document.activeElement;
    const idx = items.indexOf(active);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      const next = idx < 0
        ? (step === 1 ? 0 : items.length - 1)
        : (idx + step + items.length) % items.length;
      items[next].focus();
    } else if (e.key === "ArrowRight") {
      if (active && active._sqChildren && menu.contains(active)) {
        e.preventDefault();
        openSub(menu, active, active._sqChildren);
        const sub = stack[stack.length - 1];
        const first = rows(sub)[0];
        if (first) first.focus();
      }
    } else if (e.key === "ArrowLeft") {
      if (stack.length > 1) {
        e.preventDefault();
        const parentRow = menu._sqParentRow;
        closeBelow(stack[stack.length - 2]);
        if (parentRow) parentRow.focus();
      }
    }
    /* Enter is the button's own click; nothing extra needed. */
  }

  /* Place a fixed-position element at (x, y), clamped to the viewport.
     flipX, when given, is the alternate right edge for a submenu that
     would overflow: it flips to the left side of its parent row. */
  function place(el, x, y, flipX) {
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (x + w > vw - 4) {
      x = flipX !== undefined ? Math.max(4, flipX - w + 2) : Math.max(4, vw - w - 4);
    }
    if (y + h > vh - 4) y = Math.max(4, vh - h - 4);
    el.style.left = Math.max(4, x) + "px";
    el.style.top = Math.max(4, y) + "px";
  }

  function openSub(parentMenu, row, children) {
    /* Already open for this row? Leave it be. */
    const i = stack.indexOf(parentMenu);
    if (i >= 0 && stack[i + 1] && stack[i + 1]._sqParentRow === row) return;
    closeBelow(parentMenu);
    const sub = build(children);
    sub.classList.add("sq-submenu");
    sub._sqParentRow = row;
    document.body.appendChild(sub);
    stack.push(sub);
    const r = row.getBoundingClientRect();
    place(sub, r.right - 2, r.top - 5, r.left);
  }

  function build(items) {
    const menu = document.createElement("div");
    menu.className = "sq-menu";
    menu.addEventListener("contextmenu", (e) => e.preventDefault());
    items.forEach(item => {
      if (item.sep) {
        const sep = document.createElement("div");
        sep.className = "sq-menu-sep";
        menu.appendChild(sep);
        return;
      }
      const row = document.createElement("button");
      row.type = "button";
      row.className = "sq-menu-item" + (item.danger ? " danger" : "");
      if (item.disabled) row.disabled = true;
      const label = document.createElement("span");
      label.className = "sq-menu-label";
      label.textContent = item.label;
      row.appendChild(label);
      if (item.children && item.children.length) {
        const more = document.createElement("span");
        more.className = "sq-menu-more";
        more.textContent = "▸";
        row.appendChild(more);
        row._sqChildren = item.children;
        row.addEventListener("mouseenter", () => openSub(menu, row, item.children));
        /* A tap has no hover; clicking the row opens the fly-out too. */
        row.addEventListener("click", () => openSub(menu, row, item.children));
      } else {
        /* Hovering a plain row folds a sibling's open fly-out away. */
        row.addEventListener("mouseenter", () => closeBelow(menu));
        if (!item.disabled) {
          row.addEventListener("click", () => {
            closeAll();
            if (item.onclick) item.onclick();
          });
        }
      }
      menu.appendChild(row);
    });
    return menu;
  }

  function open(x, y, items) {
    closeAll();
    const menu = build(items);
    document.body.appendChild(menu);
    stack.push(menu);
    place(menu, x, y);
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", closeAll);
    window.addEventListener("blur", closeAll);
    bound = true;
    return menu;
  }

  window.SQMenu = { open: open, close: closeAll };
})();
