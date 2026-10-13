import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gen", DEPLOY / "gen-session-config.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

RC = """<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc" xmlns:xi="http://www.w3.org/2001/XInclude">
  <!-- stock comment -->
  <keyboard>
    <keybind key="W-e"><action name="Execute"><command>x-terminal-emulator</command></action></keybind>
  </keyboard>
  <applications>
    <application class="Other"><maximized>no</maximized></application>
  </applications>
</openbox_config>
"""


def write_apps(tmp_path, specs):
    """specs: {name: (label, category, installed)}; returns (apps_dir, bin_dir)."""
    apps, bins = tmp_path / "apps", tmp_path / "bin"
    apps.mkdir()
    bins.mkdir()
    for name, (label, category, installed) in specs.items():
        (apps / f"{name}.env").write_text(f'LABEL={label}\nCATEGORY="{category}"\nCONTROL_PORT=7000\n')
        if installed:
            (bins / name).write_text("")
    return apps, bins


@pytest.fixture
def three(tmp_path):
    return write_apps(tmp_path, {
        "wordcraft": ("WordCraft", "Documenti", True),
        "photocraft": ("PhotoCraft", "Grafica", True),
        "soundcraft": ("SoundCraft", "Audio e video", True),
        "filmcraft": ("FilmCraft", "Audio e video", False),  # source only, not built
        "gridcraft": ("GridCraft", "Documenti", True),
    })


def test_only_installed_apps_in_category_then_label_order(three):
    apps = gen.installed_apps(*three)
    assert [a["name"] for a in apps] == ["gridcraft", "wordcraft", "photocraft", "soundcraft"]


def test_icon_is_taken_from_the_app_sources_when_present(three, tmp_path):
    icon = tmp_path / "src" / "wordcraft" / "assets" / "app-icon" / "hicolor" / "256x256" / "apps"
    icon.mkdir(parents=True)
    (icon / "ai.storyteller.wordcraft.png").write_bytes(b"png")
    apps = {a["name"]: a for a in gen.installed_apps(*three, tmp_path / "src")}
    assert apps["wordcraft"]["icon"].endswith("ai.storyteller.wordcraft.png")
    assert apps["photocraft"]["icon"] is None


def test_openbox_menu_is_valid_and_lists_installed_apps(three):
    xml = gen.openbox_menu(gen.installed_apps(*three))
    root = ET.fromstring(xml)
    ns = {"m": gen.MENU_NS}
    assert root.find("m:menu", ns).get("id") == "root-menu"
    commands = [c.text for c in root.iter(f"{{{gen.MENU_NS}}}command")]
    assert f"{gen.OPEN} wordcraft" in commands
    assert f"{gen.OPEN} filmcraft" not in commands
    assert "x-terminal-emulator" in commands
    labels = [m.get("label") for m in root.find("m:menu", ns).findall("m:menu", ns)]
    assert labels == ["Documenti", "Grafica", "Audio e video"]


def test_menu_escapes_markup_in_labels(tmp_path):
    apps, bins = write_apps(tmp_path, {"a": ("R&D <Lab>", "Documenti", True)})
    ET.fromstring(gen.openbox_menu(gen.installed_apps(apps, bins)))  # must still parse


def test_rc_adds_window_rule_and_shortcut_and_keeps_the_rest():
    out = gen.openbox_rc(RC)
    root = ET.fromstring(out)
    q = lambda t: f"{{{gen.RC_NS}}}{t}"
    classes = [a.get("class") for a in root.find(q("applications"))]
    assert classes == ["Other", gen.CLASS_GLOB]
    rule = root.find(q("applications"))[1]
    assert rule.find(q("maximized")).text == "yes"
    keys = [k.get("key") for k in root.find(q("keyboard"))]
    assert keys == ["W-e", gen.MENU_SHORTCUT]
    assert "stock comment" in out


def test_rc_generation_is_idempotent():
    once = gen.openbox_rc(RC)
    assert gen.openbox_rc(once) == once


def test_sunshine_list_starts_with_desktop_and_leaves_apps_running(three):
    data = json.loads(gen.sunshine_apps(gen.installed_apps(*three)))
    names = [a["name"] for a in data["apps"]]
    assert names == ["Desktop", "GridCraft", "WordCraft", "PhotoCraft", "SoundCraft"]
    word = next(a for a in data["apps"] if a["name"] == "WordCraft")
    assert word["prep-cmd"] == [{"do": f"{gen.OPEN} wordcraft", "undo": ""}]
    assert "cmd" not in word  # no command means Sunshine never kills the app on quit


def test_tint2_has_a_launcher_per_app_pointing_at_its_desktop_file(three, tmp_path):
    apps = gen.installed_apps(*three)
    rc = gen.tint2rc(apps, tmp_path / "desktop")
    launchers = [line.split("=", 1)[1].strip() for line in rc.splitlines() if line.startswith("launcher_item_app")]
    assert launchers == [str(tmp_path / "desktop" / gen.desktop_name(a)) for a in apps]
    assert "panel_items = LTC" in rc


def test_desktop_entry_launches_through_creative_open(three):
    entry = gen.desktop_file(gen.installed_apps(*three)[1])
    assert "Exec=/usr/local/bin/creative-open wordcraft" in entry
    assert "StartupWMClass=ai.storyteller.wordcraft" in entry


def test_cli_writes_everything_and_drops_stale_launchers(three, tmp_path):
    out = tmp_path / "out"
    rc = tmp_path / "rc.xml"
    rc.write_text(RC)
    desktop = out / "applications"
    desktop.mkdir(parents=True)
    (desktop / "creative-gone.desktop").write_text("[Desktop Entry]\n")
    (desktop / "other.desktop").write_text("[Desktop Entry]\n")
    code = gen.main([
        "--apps-dir", str(three[0]), "--bin-dir", str(three[1]), "--icons-root", str(tmp_path / "nosrc"),
        "--system-rc", str(rc), "--openbox-menu", str(out / "ob/menu.xml"), "--openbox-rc", str(out / "ob/rc.xml"),
        "--sunshine-apps", str(out / "sun/apps.json"), "--tint2rc", str(out / "t2/tint2rc"), "--desktop-dir", str(desktop),
    ])
    assert code == 0
    assert sorted(p.name for p in desktop.glob("*.desktop")) == [
        "creative-gridcraft.desktop", "creative-photocraft.desktop", "creative-soundcraft.desktop",
        "creative-wordcraft.desktop", "other.desktop"]
    ET.parse(out / "ob/menu.xml")
    ET.parse(out / "ob/rc.xml")
    json.loads((out / "sun/apps.json").read_text())


def test_repo_registry_produces_one_entry_per_app_in_three_categories(tmp_path):
    bins = tmp_path / "bin"
    bins.mkdir()
    for env in (DEPLOY / "apps").glob("*.env"):
        (bins / env.stem).write_text("")
    apps = gen.installed_apps(DEPLOY / "apps", bins)
    assert len(apps) == 12
    assert {k: len(v) for k, v in gen.by_category(apps).items()} == {"Documenti": 4, "Grafica": 5, "Audio e video": 3}
    assert len({a["label"] for a in apps}) == 12
