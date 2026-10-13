#!/usr/bin/env python3
"""
Relay Sunshine's virtual input devices into the X server on :0.

Sunshine injects the client's mouse, keyboard, touch and pen input through uinput devices
("libvirtualhid Keyboard", "libvirtualhid Mouse (Absolute)", ...). Inside the unprivileged
LXC there is no udev, so Xorg never hot-plugs them and the stream ignores all input. This
daemon reads those evdev devices and replays their events into Xorg through XTest.

Runtime deps (apt): python3-evdev, python3-xlib. The translation logic below has no
dependencies so it can be unit-tested anywhere.
"""

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field

# linux/input-event-codes.h
EV_SYN, EV_KEY, EV_REL, EV_ABS = 0x00, 0x01, 0x02, 0x03
SYN_REPORT = 0
REL_X, REL_Y, REL_HWHEEL, REL_WHEEL = 0x00, 0x01, 0x06, 0x08
ABS_X, ABS_Y = 0x00, 0x01
ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x35, 0x36
BTN_MISC, BTN_TOOL_PEN, BTN_DIGI_END = 0x100, 0x140, 0x160
KEY_PRESS, KEY_RELEASE, KEY_REPEAT = 1, 0, 2

# evdev button -> X pointer button
BUTTONS = {
    0x110: 1,  # BTN_LEFT
    0x111: 3,  # BTN_RIGHT
    0x112: 2,  # BTN_MIDDLE
    0x113: 8,  # BTN_SIDE
    0x114: 9,  # BTN_EXTRA
    0x115: 9,  # BTN_FORWARD
    0x116: 8,  # BTN_BACK
    0x14A: 1,  # BTN_TOUCH (touchscreen contact, pen tip)
    0x14B: 3,  # BTN_STYLUS (pen barrel button)
    0x14C: 2,  # BTN_STYLUS2
}
# X keycodes are evdev codes + 8 with the xkb "evdev" rules every Linux X server uses.
X_KEYCODE_OFFSET = 8
WHEEL_UP, WHEEL_DOWN, WHEEL_LEFT, WHEEL_RIGHT = 4, 5, 6, 7

log = logging.getLogger("virtualhid-relay")


# --- Translation: evdev events -> X actions ------------------------------------------------


@dataclass(frozen=True)
class Key:
    keycode: int
    pressed: bool


@dataclass(frozen=True)
class Button:
    button: int
    pressed: bool


@dataclass(frozen=True)
class MoveTo:
    x: int
    y: int


@dataclass(frozen=True)
class MoveBy:
    dx: int
    dy: int


@dataclass(frozen=True)
class AbsRange:
    minimum: int
    maximum: int

    def scale(self, value: int, size: int) -> int:
        span = self.maximum - self.minimum
        if span <= 0 or size <= 0:
            return 0
        clamped = min(max(value, self.minimum), self.maximum)
        return round((clamped - self.minimum) * (size - 1) / span)


@dataclass
class Translator:
    """Turns one device's evdev events into X actions, emitted per SYN_REPORT frame."""

    abs_x: AbsRange | None = None
    abs_y: AbsRange | None = None
    _dx: int = 0
    _dy: int = 0
    _ax: int | None = None  # last absolute position seen on each axis
    _ay: int | None = None
    _abs_moved: bool = False
    _clicks: list = field(default_factory=list)

    def feed(self, ev_type: int, code: int, value: int, screen: tuple[int, int]) -> list:
        if ev_type == EV_KEY:
            self._key(code, value)
        elif ev_type == EV_REL:
            self._rel(code, value)
        elif ev_type == EV_ABS:
            if code in (ABS_X, ABS_MT_POSITION_X):
                self._ax, self._abs_moved = value, True
            elif code in (ABS_Y, ABS_MT_POSITION_Y):
                self._ay, self._abs_moved = value, True
        elif ev_type == EV_SYN and code == SYN_REPORT:
            return self._flush(screen)
        return []

    def _key(self, code: int, value: int) -> None:
        if value == KEY_REPEAT:
            return  # the X server autorepeats held keys itself
        pressed = value == KEY_PRESS
        if code in BUTTONS:
            self._clicks.append(Button(BUTTONS[code], pressed))
        elif code < BTN_MISC or code >= BTN_DIGI_END:
            self._clicks.append(Key(code + X_KEYCODE_OFFSET, pressed))
        # other BTN_* (BTN_TOOL_PEN, gamepad, ...) carry no pointer meaning here

    def _rel(self, code: int, value: int) -> None:
        if code == REL_X:
            self._dx += value
        elif code == REL_Y:
            self._dy += value
        elif code in (REL_WHEEL, REL_HWHEEL) and value:
            if code == REL_WHEEL:
                button = WHEEL_UP if value > 0 else WHEEL_DOWN
            else:
                button = WHEEL_RIGHT if value > 0 else WHEEL_LEFT
            for _ in range(min(abs(value), 10)):
                self._clicks += [Button(button, True), Button(button, False)]
        # REL_WHEEL_HI_RES / REL_HWHEEL_HI_RES duplicate the low-res notches: ignored

    def _flush(self, screen: tuple[int, int]) -> list:
        actions: list = []
        # Position first, so a click in the same frame lands where the pointer now is.
        known = self._ax is not None and self._ay is not None and self.abs_x and self.abs_y
        if self._abs_moved and known:
            width, height = screen
            actions.append(MoveTo(self.abs_x.scale(self._ax, width), self.abs_y.scale(self._ay, height)))
        if self._dx or self._dy:
            actions.append(MoveBy(self._dx, self._dy))
        actions += self._clicks
        self._dx = self._dy = 0
        self._abs_moved = False
        self._clicks = []
        return actions


# --- Runtime: evdev devices -> XTest ---------------------------------------------------------


class XInjector:
    def __init__(self, display_name: str):
        from Xlib import X, display
        from Xlib.ext import xtest

        self._X, self._xtest = X, xtest
        self.display = display.Display(display_name)
        if not self.display.has_extension("XTEST"):
            raise RuntimeError(f"{display_name} has no XTEST extension")
        self.root = self.display.screen().root
        self._size = (0, 0)
        self._size_at = 0.0

    def screen_size(self) -> tuple[int, int]:
        now = time.monotonic()
        if now - self._size_at > 1.0:  # re-read so RandR resolution changes are followed
            geometry = self.root.get_geometry()
            self._size, self._size_at = (geometry.width, geometry.height), now
        return self._size

    def apply(self, actions: list) -> None:
        X, fake = self._X, self._xtest.fake_input
        for action in actions:
            if isinstance(action, MoveTo):
                fake(self.display, X.MotionNotify, x=action.x, y=action.y)
            elif isinstance(action, MoveBy):
                fake(self.display, X.MotionNotify, detail=True, x=action.dx, y=action.dy)
            elif isinstance(action, Button):
                fake(self.display, X.ButtonPress if action.pressed else X.ButtonRelease, action.button)
            elif isinstance(action, Key):
                fake(self.display, X.KeyPress if action.pressed else X.KeyRelease, action.keycode)
        self.display.flush()


def abs_range(device, code: int) -> AbsRange | None:
    caps = dict(device.capabilities().get(EV_ABS, []))
    info = caps.get(code)
    return AbsRange(info.min, info.max) if info else None


async def relay_device(path: str, injector: XInjector) -> None:
    import evdev

    device = evdev.InputDevice(path)
    translator = Translator(
        abs_x=abs_range(device, ABS_X) or abs_range(device, ABS_MT_POSITION_X),
        abs_y=abs_range(device, ABS_Y) or abs_range(device, ABS_MT_POSITION_Y),
    )
    log.info("relaying %s (%s)", device.name, path)
    try:
        async for event in device.async_read_loop():
            screen = injector.screen_size() if event.type == EV_SYN else (0, 0)
            actions = translator.feed(event.type, event.code, event.value, screen)
            if actions:
                injector.apply(actions)
    except OSError as e:
        log.info("device %s gone: %s", path, e)
    finally:
        device.close()


async def main() -> int:
    import evdev

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    prefix = os.environ.get("RELAY_NAME_PREFIX", "libvirtualhid")
    injector = XInjector(os.environ.get("DISPLAY", ":0"))
    tasks: dict[str, asyncio.Task] = {}
    log.info("watching /dev/input for devices named %r*", prefix)
    while True:
        for path in evdev.list_devices():
            if path in tasks and not tasks[path].done():
                continue
            try:
                name = evdev.InputDevice(path).name
            except OSError:
                continue  # unreadable (not ours) or vanished
            if name.startswith(prefix):
                tasks[path] = asyncio.create_task(relay_device(path, injector))
        await asyncio.sleep(2)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
