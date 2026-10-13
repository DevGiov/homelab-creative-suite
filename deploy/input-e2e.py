#!/usr/bin/env python3
"""
End-to-end check of the input path Sunshine -> libvirtualhid evdev devices -> relay -> Xorg :0.

    python3 deploy/input-e2e.py

Writes events into the virtual devices Sunshine created (exactly what Sunshine does when a client
moves the mouse or types) and checks with Xlib that the X server saw them. Needs python3-evdev and
python3-xlib (installed by install.sh). Exits non-zero if any check fails.
"""

import sys
import time

import evdev
from evdev import ecodes as e
from Xlib import X, display

SETTLE = 0.4  # the relay polls nothing; this only covers scheduling + X round trips
failures = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global failures
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures += 1
        print(f"      {detail}")


def find(name: str) -> evdev.InputDevice | None:
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        if device.name == name:
            return device
    return None


def send(device: evdev.InputDevice, *events: tuple[int, int, int]) -> None:
    for ev_type, code, value in events:
        device.write(ev_type, code, value)
    device.syn()
    time.sleep(SETTLE)


def main() -> int:
    d = display.Display(":0")
    root = d.screen().root
    geometry = root.get_geometry()
    width, height = geometry.width, geometry.height

    absolute = find("libvirtualhid Mouse (Absolute)")
    relative = find("libvirtualhid Mouse")
    keyboard = find("libvirtualhid Keyboard")
    check("Sunshine virtual devices visible and readable",
          all((absolute, relative, keyboard)), [p.name for p in map(evdev.InputDevice, evdev.list_devices())])
    if not all((absolute, relative, keyboard)):
        return 1

    info = dict(absolute.capabilities()[e.EV_ABS])
    ax, ay = info[e.ABS_X], info[e.ABS_Y]
    for fx, fy in ((0.5, 0.5), (0.25, 0.75)):
        send(absolute, (e.EV_ABS, e.ABS_X, round(ax.min + fx * (ax.max - ax.min))),
             (e.EV_ABS, e.ABS_Y, round(ay.min + fy * (ay.max - ay.min))))
        p = root.query_pointer()
        want = (round(fx * (width - 1)), round(fy * (height - 1)))
        check(f"absolute move to {fx:.0%},{fy:.0%} -> {want}",
              abs(p.root_x - want[0]) <= 2 and abs(p.root_y - want[1]) <= 2, (p.root_x, p.root_y))

    before = root.query_pointer().root_x
    send(relative, (e.EV_REL, e.REL_X, 40))
    after = root.query_pointer().root_x
    check("relative move right", after > before, (before, after))

    send(absolute, (e.EV_KEY, e.BTN_LEFT, 1))
    pressed = bool(root.query_pointer().mask & X.Button1Mask)
    send(absolute, (e.EV_KEY, e.BTN_LEFT, 0))
    released = not root.query_pointer().mask & X.Button1Mask
    check("left button press/release", pressed and released, (pressed, released))

    shift = e.KEY_LEFTSHIFT + 8
    send(keyboard, (e.EV_KEY, e.KEY_LEFTSHIFT, 1))
    down = bool(d.query_keymap()[shift // 8] & (1 << (shift % 8)))
    send(keyboard, (e.EV_KEY, e.KEY_LEFTSHIFT, 0))
    up = not d.query_keymap()[shift // 8] & (1 << (shift % 8))
    check("keyboard key press/release (Left Shift)", down and up, (down, up))

    print(f"\n{failures} check(s) failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
