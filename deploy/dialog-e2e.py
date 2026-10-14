#!/usr/bin/env python3
"""
End-to-end check of the native file dialogs: Ctrl+O in an app opens the XDG portal's GTK file
chooser, a path typed into it is opened by the app.

    DISPLAY=:0 python3 deploy/dialog-e2e.py [app] [workspace-file]

Default: DeckCraft opens /workspace/tests/demo.pptx (any deck works; the script makes one headless
if it is missing). While a dialog is open the app's UI thread is blocked, so the control channel
answers only after the dialog closed; the script therefore always leaves no dialog behind.
Needs xdotool and xwininfo. Exits non-zero on failure.
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp-server"))
import server

APP = sys.argv[1] if len(sys.argv) > 1 else "deckcraft"
TARGET = sys.argv[2] if len(sys.argv) > 2 else "/workspace/tests/demo.pptx"
failures = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global failures
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures += 1
        print(f"      {detail}")


def sh(*args: str, timeout: int = 8) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False).stdout.strip()


def dialogs() -> list[str]:
    """Top-level windows of the portal backend that are not its 10x10 helper window."""
    tree = sh("xwininfo", "-root", "-tree")
    return [line.split()[0] for line in tree.splitlines() if "xdg-desktop-portal-gtk" in line and "10x10" not in line]


def wait_for(predicate, seconds: float = 10.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.4)
    return False


def main() -> int:
    spec = server.APPS[APP]
    check("bridge launches the app", server.session_launch(APP).get("ok") is True)
    window = sh("xdotool", "search", "--class", f"ai.storyteller.{APP}").split()[0]
    for stale in dialogs():  # a previous run may have left one open
        sh("xdotool", "windowfocus", stale)
        sh("xdotool", "key", "Escape")
        time.sleep(0.5)
    check("no dialog open before the test", not dialogs(), dialogs())

    sh("xdotool", "windowactivate", "--sync", window)
    time.sleep(0.4)
    sh("xdotool", "key", "--window", window, "ctrl+o")
    check("Ctrl+O opens the file chooser", wait_for(lambda: bool(dialogs())))
    opened = dialogs()
    if not opened:
        return 1

    sh("xdotool", "windowfocus", opened[0])
    time.sleep(0.4)
    sh("xdotool", "key", "ctrl+l")
    time.sleep(0.4)
    sh("xdotool", "type", "--delay", "30", TARGET, timeout=20)
    time.sleep(0.4)
    sh("xdotool", "key", "Return")
    check("the dialog closes after Enter", wait_for(lambda: not dialogs()), dialogs())

    result = {}
    wait_for(lambda: bool(result.update(server.control_call(spec, "document.inspect", {}, timeout=10)) or result.get("ok")), 10)
    path = (result.get("result") or {}).get("path")
    check(f"{APP} opened {TARGET}", path == TARGET, path)

    print(f"\n{failures} check(s) failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
