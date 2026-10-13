import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from relay import (
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    ABS_X,
    ABS_Y,
    EV_ABS,
    EV_KEY,
    EV_REL,
    EV_SYN,
    REL_HWHEEL,
    REL_WHEEL,
    REL_X,
    REL_Y,
    SYN_REPORT,
    AbsRange,
    Button,
    Key,
    MoveBy,
    MoveTo,
    Translator,
)

SCREEN = (1920, 1080)
KEY_A, KEY_LEFTSHIFT, KEY_F1 = 30, 42, 59
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_TOUCH, BTN_STYLUS, BTN_TOOL_PEN = 0x110, 0x111, 0x112, 0x14A, 0x14B, 0x140
REL_WHEEL_HI_RES = 0x0B


def frame(t: Translator, *events) -> list:
    out = []
    for ev in events:
        out += t.feed(*ev, SCREEN)
    return out + t.feed(EV_SYN, SYN_REPORT, 0, SCREEN)


def test_nothing_is_emitted_before_syn_report():
    t = Translator()
    assert t.feed(EV_KEY, KEY_A, 1, SCREEN) == []
    assert t.feed(EV_REL, REL_X, 5, SCREEN) == []
    assert t.feed(EV_SYN, SYN_REPORT, 0, SCREEN) == [MoveBy(5, 0), Key(KEY_A + 8, True)]


def test_keys_map_to_evdev_x_keycodes_and_ignore_autorepeat():
    t = Translator()
    assert frame(t, (EV_KEY, KEY_LEFTSHIFT, 1), (EV_KEY, KEY_A, 1)) == [Key(50, True), Key(38, True)]
    assert frame(t, (EV_KEY, KEY_A, 2)) == []
    assert frame(t, (EV_KEY, KEY_A, 0), (EV_KEY, KEY_LEFTSHIFT, 0)) == [Key(38, False), Key(50, False)]
    assert frame(t, (EV_KEY, KEY_F1, 1)) == [Key(67, True)]


def test_mouse_buttons_map_to_x_buttons():
    t = Translator()
    assert frame(t, (EV_KEY, BTN_LEFT, 1)) == [Button(1, True)]
    assert frame(t, (EV_KEY, BTN_RIGHT, 1), (EV_KEY, BTN_MIDDLE, 1)) == [Button(3, True), Button(2, True)]
    assert frame(t, (EV_KEY, BTN_LEFT, 0)) == [Button(1, False)]


def test_relative_motion_accumulates_within_a_frame():
    t = Translator()
    assert frame(t, (EV_REL, REL_X, 3), (EV_REL, REL_Y, -2), (EV_REL, REL_X, 4)) == [MoveBy(7, -2)]
    assert frame(t) == []


def test_wheel_notches_become_button_clicks_and_hi_res_is_ignored():
    t = Translator()
    up = [Button(4, True), Button(4, False)]
    assert frame(t, (EV_REL, REL_WHEEL, 1), (EV_REL, REL_WHEEL_HI_RES, 120)) == up
    assert frame(t, (EV_REL, REL_WHEEL, -2)) == [Button(5, True), Button(5, False)] * 2
    assert frame(t, (EV_REL, REL_HWHEEL, 1)) == [Button(7, True), Button(7, False)]
    assert frame(t, (EV_REL, REL_HWHEEL, -1)) == [Button(6, True), Button(6, False)]


def test_huge_wheel_values_are_capped():
    t = Translator()
    assert len(frame(t, (EV_REL, REL_WHEEL, 10_000))) == 20


def test_absolute_motion_scales_to_the_screen():
    t = Translator(abs_x=AbsRange(0, 65535), abs_y=AbsRange(0, 65535))
    assert frame(t, (EV_ABS, ABS_X, 0), (EV_ABS, ABS_Y, 0)) == [MoveTo(0, 0)]
    assert frame(t, (EV_ABS, ABS_X, 65535), (EV_ABS, ABS_Y, 65535)) == [MoveTo(1919, 1079)]
    assert frame(t, (EV_ABS, ABS_X, 32768), (EV_ABS, ABS_Y, 32768)) == [MoveTo(960, 540)]


def test_absolute_motion_on_one_axis_keeps_the_other():
    t = Translator(abs_x=AbsRange(0, 1000), abs_y=AbsRange(0, 1000))
    frame(t, (EV_ABS, ABS_X, 500), (EV_ABS, ABS_Y, 1000))
    assert frame(t, (EV_ABS, ABS_X, 0)) == [MoveTo(0, 1079)]


def test_absolute_values_out_of_range_are_clamped():
    t = Translator(abs_x=AbsRange(0, 100), abs_y=AbsRange(0, 100))
    assert frame(t, (EV_ABS, ABS_X, -50), (EV_ABS, ABS_Y, 500)) == [MoveTo(0, 1079)]


def test_absolute_motion_waits_for_both_axes():
    t = Translator(abs_x=AbsRange(0, 100), abs_y=AbsRange(0, 100))
    assert frame(t, (EV_ABS, ABS_X, 50)) == []
    assert frame(t, (EV_ABS, ABS_Y, 50)) == [MoveTo(960, 540)]


def test_click_lands_after_the_move_in_the_same_frame():
    t = Translator(abs_x=AbsRange(0, 100), abs_y=AbsRange(0, 100))
    assert frame(t, (EV_KEY, BTN_LEFT, 1), (EV_ABS, ABS_X, 100), (EV_ABS, ABS_Y, 0)) == [MoveTo(1919, 0), Button(1, True)]


def test_touch_and_pen_act_as_pointer_with_clicks():
    touch = Translator(abs_x=AbsRange(0, 1919), abs_y=AbsRange(0, 1079))
    assert frame(touch, (EV_ABS, ABS_MT_POSITION_X, 100), (EV_ABS, ABS_MT_POSITION_Y, 200), (EV_KEY, BTN_TOUCH, 1)) == [
        MoveTo(100, 200),
        Button(1, True),
    ]
    pen = Translator(abs_x=AbsRange(0, 1000), abs_y=AbsRange(0, 1000))
    out = frame(pen, (EV_KEY, BTN_TOOL_PEN, 1), (EV_KEY, BTN_STYLUS, 1), (EV_ABS, ABS_X, 0), (EV_ABS, ABS_Y, 0))
    assert out == [MoveTo(0, 0), Button(3, True)]


def test_degenerate_ranges_do_not_divide_by_zero():
    assert AbsRange(5, 5).scale(5, 1920) == 0
    assert AbsRange(0, 100).scale(50, 0) == 0
