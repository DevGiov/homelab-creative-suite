#!/usr/bin/env bash
# Live health check of the creative-workstation (CT 144). Run as root on the container.
# Prints PASS/FAIL per check and exits non-zero if anything failed.
set -uo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR=/opt/creative-suite/bin
export DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/0 PULSE_SERVER=unix:/run/user/0/pulse/native
failures=0

check() {
    local name="$1"; shift
    if out="$("$@" 2>&1)"; then
        printf 'PASS  %s\n' "$name"
    else
        printf 'FAIL  %s\n      %s\n' "$name" "$(printf '%s' "$out" | tail -3 | tr '\n' ' ')"
        failures=$((failures + 1))
    fi
}

port_open() { ss -tln | awk '{print $4}' | grep -qE "[:.]$1\$"; }

control_ok() {  # control_ok PORT: read-only ui.inspect request over the JSON-lines channel
    python3 - "$1" <<'EOF'
import json, socket, sys
with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=30) as s:
    s.sendall(b'{"id":1,"method":"ui.inspect","params":{}}\n')
    reply = json.loads(s.makefile().readline())
sys.exit(0 if reply.get("ok") else f"reply: {reply}")
EOF
}

# Only the current Sunshine run counts: older runs in the same boot may predate a fix.
sunshine_log() { journalctl _SYSTEMD_INVOCATION_ID="$(systemctl show -p InvocationID --value sunshine)" --no-pager -o cat; }
sunshine_audio_ok() { ! sunshine_log | grep -q 'Unable to initialize audio capture'; }
sunshine_nvenc_ok() { sunshine_log | grep -q 'Found H.264 encoder: h264_nvenc'; }

units=(xorg-dummy openbox-session pipewire-headless pipewire-media-session-headless pipewire-pulse-headless
       sunshine creative-suite-mcp docker virtualhid-relay)
apps=()  # installed apps started at boot; on-demand apps (AUTOSTART=no) are not expected to run
for env_file in "$DEPLOY_DIR"/apps/*.env; do
    app="$(basename "$env_file" .env)"
    [[ -x "$BIN_DIR/$app" ]] || continue
    if grep -qx 'AUTOSTART=no' "$env_file"; then
        printf 'SKIP  %s is on demand\n' "$app"
    else
        apps+=("$app")
    fi
done

for unit in "${units[@]}"; do check "unit $unit active" systemctl is-active --quiet "$unit"; done
for app in "${apps[@]}"; do check "unit creative-app@$app active" systemctl is-active --quiet "creative-app@$app"; done
check "no failed units" test -z "$(systemctl --failed --no-legend --plain)"

for port in 47984 47989 47990 48010 8080 7900; do check "port $port listening" port_open "$port"; done

check "X display :0" xdpyinfo -display :0
check "pulse server reachable" pactl info
check "audio sink present" sh -c 'pactl list short sinks | grep -q .'
check "pipewire default metadata (default sink settable)" sh -c 'pw-cli ls Metadata | grep -q "metadata.name = \"default\""'
check "GPU visible" nvidia-smi -L
check "sunshine is the sm_70 build (on hold)" sh -c "apt-mark showhold | grep -qx sunshine && dpkg-query -W -f='\${Version}' sunshine | grep -q 'sm70'"
# Sunshine opens audio capture when a stream starts; this only catches a failure logged so far.
check "sunshine audio initialised" sunshine_audio_ok
check "sunshine selected NVENC" sunshine_nvenc_ok

check "MCP bridge /health" sh -c 'curl -sf http://127.0.0.1:7900/health | grep -q "\"status\":\"ok\""'
check "Moonlight web HTTP 200" sh -c '[ "$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/)" = 200 ]'

for app in "${apps[@]}"; do
    port="$(sed -n 's/^CONTROL_PORT=//p' "$DEPLOY_DIR/apps/$app.env")"
    check "$app control port $port" port_open "$port"
    check "$app answers ui.inspect" control_ok "$port"
done

echo
if ((failures)); then echo "$failures check(s) failed"; exit 1; fi
echo "all checks passed"
