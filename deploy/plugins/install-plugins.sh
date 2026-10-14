#!/usr/bin/env bash
# Install free, open-source CLAP and VST3 plugins for SoundCraft on CT 144.
#
#   deploy/plugins/install-plugins.sh            # idempotent: skips what is already installed
#
# SoundCraft scans /usr/local/lib/{clap,vst3} (and ~/.clap, ~/.vst3). Only the plugin bundles are
# kept (no standalone apps, no LV2/LADSPA/DSSI copies) to save disk. Downloads go to a staging dir
# that is removed afterwards. All of these are free software: Surge XT (GPL-3), DISTRHO plugins
# (GPL/ISC), Odin 2 (GPL-3), Dexed (GPL-3), LSP (LGPL-3).
set -euo pipefail

CLAP_DIR=/usr/local/lib/clap
VST3_DIR=/usr/local/lib/vst3
STAGE="$(mktemp -d /opt/creative-suite/plugins-src.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$CLAP_DIR" "$VST3_DIR"

log() { printf '[plugins] %s\n' "$*"; }

command -v 7z >/dev/null 2>&1 || { log "apt install p7zip-full"; DEBIAN_FRONTEND=noninteractive apt-get install -y -q p7zip-full unzip >/dev/null; }

# release_asset REPO TAG|latest REGEX -> browser_download_url of the first asset whose name matches
release_asset() {
    python3 - "$@" <<'PY'
import json, re, sys, urllib.request
repo, tag, rx = sys.argv[1:4]
url = f"https://api.github.com/repos/{repo}/releases/" + ("latest" if tag == "latest" else f"tags/{tag}")
data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "creative-suite"}), timeout=30))
for asset in data["assets"]:
    if re.search(rx, asset["name"]):
        print(asset["browser_download_url"]); break
else:
    sys.exit(f"no asset matching {rx!r} in {repo} {tag}")
PY
}

# install_from NAME ARCHIVE_URL: download, unpack, copy every *.clap file and *.vst3 bundle
install_from() {
    local name="$1" url="$2" dir="$STAGE/$1" archive
    archive="$STAGE/$name.${url##*.}"
    case "$url" in *.tar.xz) archive="$STAGE/$name.tar.xz" ;; *.tar.gz) archive="$STAGE/$name.tar.gz" ;; esac
    log "$name: downloading $(basename "$url")"
    curl -fsSL -o "$archive" "$url"
    mkdir -p "$dir"
    case "$archive" in
        *.tar.xz | *.tar.gz) tar -xf "$archive" -C "$dir" ;;
        *.zip) unzip -q "$archive" -d "$dir" ;;
        *.7z) 7z x -y -o"$dir" "$archive" >/dev/null ;;
    esac
    rm -f "$archive"
    local n_clap=0 n_vst3=0 f
    while IFS= read -r -d '' f; do
        rm -rf "${CLAP_DIR:?}/$(basename "$f")"; cp -a "$f" "$CLAP_DIR/"; n_clap=$((n_clap + 1))
    done < <(find "$dir" -name '*.clap' \( -type f -o -type d \) -print0)
    while IFS= read -r -d '' f; do
        rm -rf "${VST3_DIR:?}/$(basename "$f")"; cp -a "$f" "$VST3_DIR/"; n_vst3=$((n_vst3 + 1))
    done < <(find "$dir" -name '*.vst3' -type d -print0)
    log "$name: $n_clap CLAP, $n_vst3 VST3"
    rm -rf "$dir"
}

install_from dpf-plugins "https://github.com/DISTRHO/DPF-Plugins/releases/download/v1.7/DPF-Plugins-v1.7-linux-x86_64.tar.xz"
install_from surge-xt "$(release_asset surge-synthesizer/surge latest '^surge-xt-linux-NIGHTLY-.*-pluginsonly\.tar\.gz$')"
install_from odin2 "$(release_asset TheWaveWarden/odin2 NightlyDevel 'Linux\.zip$')"
install_from dexed "$(release_asset asb2m10/dexed v1.0.1 '-lnx\.zip$')"
install_from lsp-plugins "$(release_asset lsp-plugins/lsp-plugins 1.2.35 'Linux-x86_64\.7z$')"

log "installed: $(find "$CLAP_DIR" -maxdepth 1 -name '*.clap' | wc -l) CLAP files, $(find "$VST3_DIR" -maxdepth 1 -name '*.vst3' | wc -l) VST3 bundles"
du -sh "$CLAP_DIR" "$VST3_DIR" | sed 's/^/[plugins] /'
