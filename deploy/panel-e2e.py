#!/usr/bin/env python3
"""
End-to-end check of the launchers, driven like a Moonlight client would: through the virtual
mouse Sunshine creates (uinput -> relay -> Xorg), not by calling creative-open directly.

    python3 deploy/panel-e2e.py

1. Stops DeckCraft, clicks the first launcher of the tint2 panel and expects the app to start and
   its window to appear.
2. Stops the apps, right-clicks the empty desktop and expects the Openbox menu to open at the
   pointer, then dismisses it and restarts the apps that were running.
Needs python3-evdev, xdotool, xwininfo (x11-utils). Exits non-zero if a check fails.
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


def children() -> set[str]:
    """Top-level windows of the X root: popup menus show up here without a name or class."""
    out = sh("xwininfo", "-root", "-children")
    return {tok for line in out.splitlines() if (tok := line.strip().split(" ")[0]).startswith("0x")}


def near(window: str, x: int, y: int, slack: int = 8) -> bool:
    info = sh("xwininfo", "-id", window)
    fields = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in info.splitlines() if ":" in line)}
    try:
        wx, wy = int(fields["Absolute upper-left X"]), int(fields["Absolute upper-left Y"])
    except (KeyError, ValueError):
        return False
    return abs(wx - x) <= slack and abs(wy - y) <= slack


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

    # 2. right click on an empty desktop opens the Openbox menu (maximised apps would take the click)
    running = sh("systemctl", "list-units", "creative-app@*", "--state=active", "--no-legend").split()
    running = [u for u in running if u.startswith("creative-app@")]
    subprocess.run(["systemctl", "stop", "creative-app@*"], check=False)
    wait_for(lambda: not windows("ai.storyteller"), 10)
    mouse.click(mouse.width - 10, 10)  # make sure no menu is open
    time.sleep(0.5)
    before = children()
    x, y = mouse.width // 2, mouse.height // 3
    mouse.click(x, y, e.BTN_RIGHT)
    time.sleep(1)
    opened = [w for w in children() - before if near(w, x, y)]
    check("right click opens the Openbox menu where it was clicked", bool(opened), children() - before)
    mouse.click(mouse.width - 10, 10)  # dismiss
    time.sleep(0.5)
    check("a click elsewhere closes it", not [w for w in children() - before if near(w, x, y)])
    for unit in running:  # leave the workstation as found
        subprocess.run(["systemctl", "start", unit], check=False)

    print(f"\n{failures} check(s) failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
