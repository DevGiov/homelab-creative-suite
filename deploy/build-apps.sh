#!/usr/bin/env bash
# Build the Creative Suite Rust apps on CT 144 and install them into /opt/creative-suite/bin.
#
#   deploy/build-apps.sh [app ...]      # default: every app below, lightest first
#
# Sources are cloned to /workspace/src/<app> at the commit pinned by the meta-repo submodule
# (read from the git tree of /opt/creative-suite/repo, which is cloned without submodules).
# Run it detached; it takes 1.5-2.5 h for all apps on 6 cores / 8 GB:
#   systemd-run --unit=craft-build --collect deploy/build-apps.sh
set -euo pipefail

REPO=/opt/creative-suite/repo
SRC=/workspace/src
BIN_DIR=/opt/creative-suite/bin
export CARGO_TARGET_DIR=/opt/creative-suite/build/target
export HOME=/root
export PATH="/root/.cargo/bin:$PATH"
JOBS="${CRAFT_JOBS:-3}"       # 8 GB container: more parallel rustc jobs thrash memory
MIN_FREE_GB=8                 # clean the shared target when the disk gets this tight
ALL_APPS=(cadcraft deckcraft designcraft effectcraft filmcraft gridcraft lightcraft pdfcraft photocraft soundcraft vectorcraft wordcraft)
# apt packages some apps need beyond the base image (FilmCraft: muda's GTK menu bar + libxdo).
APT_PACKAGES=(libgtk-3-dev libxdo-dev)

log() { printf '%s [build-apps] %s\n' "$(date '+%F %T')" "$*"; }

free_gb() { df -BG --output=avail / | tail -1 | tr -dc '0-9'; }

ensure_packages() {
    local missing=()
    for pkg in "${APT_PACKAGES[@]}"; do dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg"); done
    if ((${#missing[@]})); then
        log "apt install ${missing[*]}"
        DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
    fi
}

checkout() {  # checkout APP: clone if needed and move to the commit pinned by the meta-repo
    local app="$1" pin
    pin="$(git -C "$REPO" ls-tree HEAD "$app" | awk '$2 == "commit" {print $3}')"
    [[ -n "$pin" ]] || { log "no submodule pin for $app in $REPO"; return 1; }
    [[ -d "$SRC/$app/.git" ]] || git clone -q "https://github.com/storytold/$app.git" "$SRC/$app"
    git -C "$SRC/$app" remote set-url origin "https://github.com/storytold/$app.git" 2>/dev/null || true
    git -C "$SRC/$app" fetch -q --tags origin 2>/dev/null || true
    git -C "$SRC/$app" reset --hard -q HEAD 2>/dev/null || true
    if ! git -C "$SRC/$app" checkout -q "$pin"; then
        log "cannot checkout pin $pin for $app"
        return 1
    fi
    log "$app at $(git -C "$SRC/$app" log --oneline -1)"
}

build() {  # build APP: cargo build with memory-friendly profile overrides, then install the binaries
    local app="$1" jobs="$2"
    # Upstream release profiles use fat/thin LTO with codegen-units = 1 for several apps; the final
    # link then exceeds 8 GB. The UI is software-rendered here, so the lost optimisation is moot.
    CARGO_PROFILE_RELEASE_LTO=off CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 \
        cargo build --release --manifest-path "$SRC/$app/Cargo.toml" -j"$jobs" -p "$app" -p "$app-cli"
    install -m 0755 "$CARGO_TARGET_DIR/release/$app" "$CARGO_TARGET_DIR/release/$app-cli" "$BIN_DIR/"
}

FORCE=0
apps=()
for arg in "$@"; do
    if [[ "$arg" == "--force" || "$arg" == "-f" ]]; then
        FORCE=1
    else
        apps+=("$arg")
    fi
done
((${#apps[@]})) || apps=("${ALL_APPS[@]}")
mkdir -p "$SRC" "$BIN_DIR" "$CARGO_TARGET_DIR"
ensure_packages

failed=()
for app in "${apps[@]}"; do
    if [[ $FORCE -eq 0 && -x "$BIN_DIR/$app" && -x "$BIN_DIR/$app-cli" ]]; then
        log "$app already installed, skipping (use --force or remove $BIN_DIR/$app to rebuild)"
        continue
    fi
    if (($(free_gb) < MIN_FREE_GB)); then
        log "only $(free_gb) GB free: cleaning the shared target dir"
        rm -rf "$CARGO_TARGET_DIR"
        mkdir -p "$CARGO_TARGET_DIR"
    fi
    log "=== $app ($(free_gb) GB free)"
    start=$SECONDS
    if ! checkout "$app"; then
        log "$app FAILED (checkout)"
        failed+=("$app")
        continue
    fi
    if build "$app" "$JOBS"; then
        log "$app built in $(((SECONDS - start) / 60)) min"
    elif build "$app" 2; then   # most failures here are the link running out of memory
        log "$app built on retry with -j2 in $(((SECONDS - start) / 60)) min"
    else
        log "$app FAILED (build)"
        failed+=("$app")
    fi
done

log "finished; failed: ${failed[*]:-none}"
((${#failed[@]} == 0))
