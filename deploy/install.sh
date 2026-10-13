#!/usr/bin/env bash
# Install the creative-workstation (CT 144) configuration from this repo.
# Idempotent: run as root on the container after every `git pull`.
#   /opt/creative-suite/repo/deploy/install.sh
# Running services are not restarted; restart the ones whose config changed.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$DEPLOY_DIR")"
BIN_DIR=/opt/creative-suite/bin
VENV=/opt/creative-suite/mcp-server/.venv
PACKAGES=(pulseaudio-utils locales python3-evdev python3-xlib)

log() { printf '[install] %s\n' "$*"; }

missing=()
for pkg in "${PACKAGES[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
    log "apt install ${missing[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
fi

if ! locale -a 2>/dev/null | grep -qi '^en_US\.utf8$'; then
    log "generating en_US.UTF-8 locale"
    locale-gen en_US.UTF-8 >/dev/null
fi

log "config files"
install -m 0644 "$DEPLOY_DIR"/systemd/*.service /etc/systemd/system/
install -D -m 0644 "$DEPLOY_DIR/sunshine/sunshine.conf" /root/.config/sunshine/sunshine.conf
install -D -m 0644 "$DEPLOY_DIR/sunshine/apps.json" /root/.config/sunshine/apps.json
install -D -m 0644 "$DEPLOY_DIR/moonlight/docker-compose.yaml" /opt/moonlight-web/docker-compose.yaml
install -D -m 0644 "$DEPLOY_DIR/x11/xorg.conf" /etc/X11/xorg.conf
# pipewire-media-session only exports the "default" metadata (default sink, needed by Sunshine to
# route app audio into its capture sink) when these modules are on; Ubuntu ships them commented out.
mkdir -p /etc/pipewire/media-session.d
sed -E 's/^(\s*)#(metadata|default-nodes|restore-stream|streams-follow-default)(\s)/\1\2\3/' \
    /usr/share/pipewire/media-session.d/media-session.conf > /etc/pipewire/media-session.d/media-session.conf

log "MCP bridge venv"
[[ -x "$VENV/bin/python3" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q -r "$REPO_DIR/mcp-server/requirements.txt"

log "systemd units"
systemctl daemon-reload
systemctl enable -q --now \
    xorg-dummy.service openbox-session.service \
    pipewire-headless.service pipewire-media-session-headless.service pipewire-pulse-headless.service \
    sunshine.service creative-suite-mcp.service virtualhid-relay.service

for env_file in "$DEPLOY_DIR"/apps/*.env; do
    app="$(basename "$env_file" .env)"
    if [[ ! -x "$BIN_DIR/$app" ]]; then
        log "app $app skipped: $BIN_DIR/$app not installed"
    elif grep -qx 'AUTOSTART=no' "$env_file"; then
        systemctl disable -q "creative-app@$app.service"
        log "app $app on demand (AUTOSTART=no)"
    else
        systemctl enable -q --now "creative-app@$app.service"
        log "app $app enabled"
    fi
done

log "done"
