#!/bin/bash
# Turn a Raspberry Pi into a Project Tracker wall display.
#
# Run on Raspberry Pi OS (Lite is enough, Bookworm or newer) as a user
# with sudo:
#
#   ./pi-display-setup.sh "http://192.168.1.170:9280/display?d=abc123"
#   ./pi-display-setup.sh "http://..." --rotate 90
#
# It installs cage (a minimal Wayland compositor) plus Chromium, and a
# systemd unit that boots straight into the display, waits for the
# tracker to answer before starting the browser, and restarts forever if
# anything crashes. Re-run with a new URL or rotation to update.
set -euo pipefail

URL="${1:-}"
ROTATE="normal"
if [[ "${2:-}" == "--rotate" && -n "${3:-}" ]]; then
  case "$3" in
    0) ROTATE="normal" ;;
    90|180|270) ROTATE="$3" ;;
    *) echo "rotation must be 0, 90, 180, or 270" >&2; exit 1 ;;
  esac
fi

if [[ -z "$URL" ]]; then
  echo "Usage: $0 <display-url> [--rotate 0|90|180|270]" >&2
  echo "Get the URL from the tracker's Displays page." >&2
  exit 1
fi

KUSER="${SUDO_USER:-$(id -un)}"
if [[ "$KUSER" == "root" ]]; then KUSER="pi"; fi
KUID="$(id -u "$KUSER")"

echo "Installing packages (cage, chromium, seatd, wlr-randr)..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends cage seatd wlr-randr curl \
  chromium-browser 2>/dev/null || sudo apt-get install -y --no-install-recommends chromium

CHROMIUM="$(command -v chromium-browser || command -v chromium)"
CAGE="$(command -v cage)"

sudo usermod -aG _seatd "$KUSER" 2>/dev/null || true
sudo systemctl enable --now seatd 2>/dev/null || true

sudo mkdir -p /etc/projecttracker
sudo tee /etc/projecttracker/display-env >/dev/null <<EOF
DISPLAY_URL=$URL
DISPLAY_ROTATE=$ROTATE
EOF

# Health gate: do not launch the browser into a connection-refused page.
sudo tee /usr/local/bin/projecttracker-wait-health >/dev/null <<'EOF'
#!/bin/sh
. /etc/projecttracker/display-env
base=$(printf '%s' "$DISPLAY_URL" | sed -E 's#^(https?://[^/]+).*#\1#')
for i in $(seq 1 180); do
  curl -sf --max-time 3 "$base/health" >/dev/null 2>&1 && exit 0
  sleep 5
done
exit 0
EOF
sudo chmod +x /usr/local/bin/projecttracker-wait-health

# cage's DRM backend ignores WLR_OUTPUT_TRANSFORM, so rotation is applied
# at runtime with wlr-randr after the compositor is up.
sudo tee /usr/local/bin/projecttracker-apply-rotation >/dev/null <<'EOF'
#!/bin/sh
. /etc/projecttracker/display-env
[ "$DISPLAY_ROTATE" = "normal" ] && exit 0
for i in $(seq 1 30); do
  for d in /run/user/*/wayland-*; do
    case "$d" in *.lock) continue ;; esac
    [ -e "$d" ] || continue
    export XDG_RUNTIME_DIR="$(dirname "$d")" WAYLAND_DISPLAY="$(basename "$d")"
    out=$(wlr-randr 2>/dev/null | awk '/^[A-Za-z]/{print $1; exit}')
    if [ -n "$out" ]; then
      wlr-randr --output "$out" --transform "$DISPLAY_ROTATE" && exit 0
    fi
  done
  sleep 1
done
exit 0
EOF
sudo chmod +x /usr/local/bin/projecttracker-apply-rotation

sudo tee /etc/systemd/system/projecttracker-display.service >/dev/null <<EOF
[Unit]
Description=Project Tracker wall display
After=systemd-user-sessions.service getty@tty1.service network-online.target seatd.service
Wants=network-online.target seatd.service
Conflicts=getty@tty1.service
StartLimitIntervalSec=0

[Service]
EnvironmentFile=/etc/projecttracker/display-env
Type=simple
TimeoutStartSec=900
User=$KUSER
PAMName=login
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
StandardInput=tty
StandardOutput=journal
StandardError=journal
UtmpIdentifier=tty1
UtmpMode=user
Environment=XDG_RUNTIME_DIR=/run/user/$KUID
Environment=LIBSEAT_BACKEND=seatd
ExecStartPre=-/usr/local/bin/projecttracker-wait-health
ExecStart=$CAGE -- $CHROMIUM --kiosk --noerrdialogs --disable-infobars \\
  --no-first-run --ozone-platform=wayland --default-background-color=0d0f12 \\
  --disable-restore-session-state \$DISPLAY_URL
ExecStartPost=-/usr/local/bin/projecttracker-apply-rotation
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable projecttracker-display.service
sudo systemctl restart projecttracker-display.service --no-block

echo
echo "Done. The display starts on tty1 now and on every boot."
echo "  URL:      $URL"
echo "  Rotation: $ROTATE"
echo "Change either by re-running this script, or edit /etc/projecttracker/display-env"
echo "and: sudo systemctl restart projecttracker-display"
