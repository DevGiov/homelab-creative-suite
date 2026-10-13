#!/usr/bin/env python3
"""
Make PhotoCraft render on the CPU by preference.

The virtual display has no GPU surface. Left on "auto", PhotoCraft tries the GPU, falls back, and
opens a modal "Switched to CPU rendering" on every launch. Choosing "Keep Using CPU" in that
dialog stores performance.renderingMode = "cpu"; this writes the same values (see
photocraft crates/ui-egui/src/gpu_status.rs: choose_recovery) so the dialog never appears.

    python3 deploy/provision-photocraft.py [PREFERENCES.json]

Idempotent; keeps every other preference. Run while PhotoCraft is stopped (it rewrites the file).
"""

import json
import sys
from pathlib import Path

DEFAULT_PATH = Path("/root/.config/photocraft/preferences.json")
CPU = {"renderingMode": "cpu", "useGpu": False, "gpuBackend": "auto"}


def with_cpu_rendering(prefs: dict) -> dict:
    """`prefs` with the CPU rendering preference set; everything else untouched."""
    out = dict(prefs)
    performance = dict(out.get("performance") or {})
    performance.update(CPU)
    out["performance"] = performance
    return out


def provision(path: Path) -> bool:
    """Write the preference to `path`; returns True if the file changed."""
    try:
        current = json.loads(path.read_text())
    except FileNotFoundError:
        current = {}
    if not isinstance(current, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    updated = with_cpu_rendering(current)
    if updated == current:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(updated, indent=2) + "\n")
    tmp.replace(path)
    return True


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    print(f"provision-photocraft: {target}: {'updated' if provision(target) else 'already set'}")
