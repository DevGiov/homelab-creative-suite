#!/usr/bin/env bash
# Build the sample "packs" tree in /workspace/Samples from free, packaged sources (Debian/Ubuntu).
# SoundCraft has no pack concept: a pack is a folder, browsed through the Workspace window / file dialogs.
# Idempotent: run as root on the container.
set -euo pipefail

ROOT=/workspace/Samples
KITS=/usr/share/hydrogen/data/drumkits

DEBIAN_FRONTEND=noninteractive apt-get install -y -q hydrogen-drumkits hydrogen-data fluid-soundfont-gm >/dev/null

mkdir -p "$ROOT/Drums" "$ROOT/Soundfonts" "$ROOT/Loops" "$ROOT/Mine"

# Hydrogen drum kits: one folder per kit, audio plus licence/readme only (drumkit.xml and artwork are not needed).
for kit in "$KITS"/*/; do
    name="$(basename "$kit")"
    dest="$ROOT/Drums/${name// /_}"
    mkdir -p "$dest"
    (cd "$kit" && find . -type f \( -iname '*.wav' -o -iname '*.flac' -o -iname '*.aif*' -o -iname 'README*' -o -iname 'LICENSE*' \) \
        -exec cp --parents -n {} "$dest" \;)
done

# General MIDI soundfonts (for sf2-capable players)
cp -n /usr/share/sounds/sf2/FluidR3_GM.sf2 "$ROOT/Soundfonts/"

# demo songs ship loops only as .h2song; the click track is a handy metronome source
install -m 0644 -D /usr/share/hydrogen/data/click.wav "$ROOT/Loops/click.wav"
printf '%s\n' 'Samples: one folder per pack. Drums/ from Hydrogen drumkits (see each kit README for licence).' > "$ROOT/README.txt"
echo "samples ready: $(find "$ROOT" -type f | wc -l) files, $(du -sh "$ROOT" | cut -f1)"
