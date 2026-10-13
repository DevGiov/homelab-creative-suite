#!/usr/bin/env python3
"""
End-to-end check of the launchers, driven like a Moonlight client would: through the virtual
mouse Sunshine creates (uinput -> relay -> Xorg), not by calling creative-open directly.

    python3 deploy/panel-e2e.py

1. Stops DeckCraft, clicks the first launcher of the tint2 panel and expects the app to start and
   its window to appear.
2. Right-clicks the empty desktop and expects the Openbox menu to open.
Needs python3-evdev, python3-xlib, xdotool. Exits non-zero if a check fails.
"""

import subprocess
import sys
import time

import evdev
from evdev import ecodes as e

APP = "deckcraft"
UNIT = f"creative-app@{APP}.service"
WAIT = 25
failures = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global failures
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures += 1
        print(f"      {detail}")


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()


def device(name: str) -> evdev.InputDevice:
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except OSError:
            continue
        if d.name == name:
            return d
    raise SystemExit(f"virtual device {name!r} not found: is Sunshine running?")


class Mouse:
    def __init__(self):
        self.dev = device("libvirtualhid Mouse (Absolute)")
        info = dict(self.dev.capabilities()[e.EV_ABS])
        self.x, self.y = info[e.ABS_X], info[e.ABS_Y]
        geometry = sh("xdotool", "getdisplaygeometry").split()
        self.width, self.height = int(geometry[0]), int(geometry[1])

    def _write(self, *events):
        for ev in events:
            self.dev.write(*ev)
        self.dev.write(e.EV_SYN, e.SYN_REPORT, 0)
        time.sleep(0.15)

    def move(self, px: int, py: int):
        ax = round(self.x.min + px / (self.width - 1) * (self.x.max - self.x.min))
        ay = round(self.y.min + py / (self.height - 1) * (self.y.max - self.y.min))
        self._write((e.EV_ABS, e.ABS_X, ax), (e.EV_ABS, e.ABS_Y, ay))

    def click(self, px: int, py: int, button: int = e.BTN_LEFT):
        self.move(px, py)
        self._write((e.EV_KEY, button, 1))
        self._write((e.EV_KEY, button, 0))


def wait_for(predicate, seconds: float = WAIT) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.5)
    return False


def windows(cls: str) -> list[str]:
    return sh("xdotool", "search", "--class", cls).split()


def main() -> int:
    mouse = Mouse()

    # 1. launcher click starts the app
    subprocess.run(["systemctl", "stop", UNIT], check=False)
    check("DeckCraft is stopped", wait_for(lambda: not windows(f"ai.storyteller.{APP}"), 10))
    panel = sh("xdotool", "search", "--class", "tint2").split()
    check("tint2 panel is on screen", bool(panel))
    if not panel:
        return 1
    geo = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in
           sh("xdotool", "getwindowgeometry", panel[0]).splitlines() if ":" in line)}
    px, py = (int(v) for v in geo["Position"].split()[0].split(","))
    _, height = (int(v) for v in geo["Geometry"].split("x"))
    # First launcher: panel padding 6 + launcher padding 4 + half of the 36 px icon.
    mouse.click(px + 28, py + height // 2)
    check("launcher click starts the app", wait_for(lambda: sh("systemctl", "is-active", UNIT) == "active"),
          sh("systemctl", "is-active", UNIT))
    check("its window appears", wait_for(lambda: bool(windows(f"ai.storyteller.{APP}"))))

    # 2. right click on an empty desktop opens the Openbox menu
    subprocess.run(["systemctl", "stop", UNIT], check=False)
    wait_for(lambda: not windows(f"ai.storyteller.{APP}"), 10)
    before = set(sh("xdotool", "search", "--onlyvisible", "--class", "openbox").split())
    mouse.click(mouse.width // 2, mouse.height // 3, e.BTN_RIGHT)
    time.sleep(0.8)
    after = set(sh("xdotool", "search", "--onlyvisible", "--class", "openbox").split())
    check("right click opens the Openbox menu", len(after - before) > 0, (before, after))
    mouse.click(mouse.width // 2, mouse.height // 3)  # click elsewhere to dismiss it
    subprocess.run(["systemctl", "start", UNIT], check=False)  # leave the workstation as found

    print(f"\n{failures} check(s) failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
