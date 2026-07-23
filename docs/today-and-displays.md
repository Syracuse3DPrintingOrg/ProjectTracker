# Today's Tasks and wall displays

Today's Tasks is the short list of what you mean to do today, and it follows you onto tablets, TVs, Raspberry Pis, and even tiny ESP32 screens.

## The Today rail

Every board has a Today's Tasks rail on the right. Drag any card onto it and the card joins the list (the card stays on its board, marked with a little sun). Each entry on the rail shows which project and status the card came from; drag it off the rail to remove it from the list.

- **Clear finished** removes every card on the list that has reached a done column.
- **Plan my day** appears once an AI provider is configured: it picks a handful of tasks from everything open, favoring overdue and due-soon work, and drops them on the list.

When your instance has user accounts, the rail gains a chooser: **Everyone** shows the shared household list, **Mine** shows your personal one. The choice sticks to your browser, and Plan my day fills whichever list you are looking at.

The **Today** pill in the top bar shows the same list as a simple page.

## Kiosk mode

The kiosk at `/kiosk` is the Today list grown up into a wall dashboard: huge type, a clock, a progress bar, and rows big enough to tap. Tap a task to check it off; tap again to bring it back. Recurring chores respawn as usual, and high-priority tasks (P0 and P1) are flagged in red. Viewers can look but not touch, and the kiosk says so if they try.

The footer holds quick views: **Today**, **Due soon**, and **Overdue**, each tappable to swap the list on screen, with counts so you know what you are in for. It also quietly mentions your most neglected project when one has gone three days or more without movement.

Press **Kiosk** in the top bar and this browser becomes a wall screen: the preference sticks to the device, so the tablet on the fridge reopens as the dashboard, and the small x on the kiosk page turns it back into the full app. The list refreshes every 10 seconds and the screen only repaints when something actually changed, so a scrolled list stays put.

## The classic display page

`/display` is the original passive page: the Today list, a progress bar, an optional clock, and overdue highlighting, with no tap targets at all. It refreshes every 15 seconds and repaints only on change, which is kind to always-on screens. Use it for anything that should show the list without ever being touched.

## Registering displays

Register each screen under **Settings, Hardware**. Every display gets a name, a kind, and a URL of its own, and its look is managed from the tracker, so you never have to touch the device again to restyle it:

- **Theme**: dark, light, or high contrast.
- **Text size**: small to extra large.
- **Clock**: show or hide.
- **Finished tasks**: crossed out, or hidden entirely.
- **TV mode**: adds margins so overscan does not eat the edges.
- **Shows**: the shared Today list, or one user's personal list (the row appears once the instance has users).

Three kinds are supported: **Browser** (a Pi kiosk, tablet, or TV browser; it gets the kiosk URL), **Android TV** (popped up remotely, below), and **ESP32** (it gets the JSON API URL). Deleting a display only forgets its registration; the device itself is not touched.

If devices should reach the tracker at a different address than the one your browser uses, set it under **Tracker address for devices** on the same pane.

### The display token

Once logins exist, displays authenticate with a token instead of a session: the URLs from the table carry `?token=...` automatically. Generate, rotate, or remove the token from the Hardware pane. The token is read-only with one exception: it may tap tasks done on the kiosk, so a wall touchscreen still works.

## Raspberry Pi

One script turns a stock Raspberry Pi OS install (Lite is enough) into a display that boots straight into your list. Copy the display's URL from the Hardware pane and run, on the Pi:

```bash
./scripts/pi-display-setup.sh "http://192.168.1.50:9280/kiosk?d=abc123"
./scripts/pi-display-setup.sh "http://192.168.1.50:9280/kiosk?d=abc123" --rotate 90
```

It installs a minimal kiosk (the cage compositor plus Chromium), waits for the tracker to answer before starting the browser, restarts everything if it crashes, and supports 0, 90, 180, and 270 degree rotation. Re-run it with a new URL or rotation to change either.

## Android TV

Add the TV as a display with its IP address (port 5555 is assumed), after enabling Developer options and Network debugging on the TV. Then press **Show**: the tracker wakes the TV and opens the display on it. The first Show pops an "allow USB debugging" prompt on the TV; tick Always allow. **Hide** sends the TV back to its home screen.

This needs the `adb` tool installed on the server running the tracker (the buttons say so when it is missing), and the TV needs a browser that can open links. Members can press Show and Hide, so automations and family can put the list on screen; configuring displays stays with admins.

## ESP32 screens

Small screens poll `/api/display`, a compact JSON payload built to parse on a microcontroller:

```json
{
  "count": 3,
  "remaining": 2,
  "tasks": [
    {"id": 41, "title": "Sand the door", "project": "Hall closet",
     "status": "In Progress", "done": false, "priority": 2,
     "due": "2026-07-24", "checklist": "1/3"}
  ]
}
```

Two ready-to-flash ESPHome examples ship in the repo:

- `examples/esphome-tdisplay.yaml`: the LILYGO TTGO T-Display, with the on-board button paging through a long list, backlight control, and an offline notice.
- `examples/esphome-display.yaml`: a generic ESP32 with an ST7789 panel.

Point `base_url` at your tracker, and if a password is set, put the display token in `display_token`. The examples poll every 30 seconds.
