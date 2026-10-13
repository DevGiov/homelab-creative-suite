#!/usr/bin/env python3
"""
Generate the session launcher configuration from deploy/apps/*.env.

One entry per *installed* app (a binary exists in --bin-dir), in the same order everywhere:
  - Openbox root menu (right click on the desktop) and rc.xml rules/shortcut
  - Sunshine apps.json (the app list shown by Moonlight)
  - tint2 panel (launchers + task bar) and the .desktop files it launches from

Standard library only; run by deploy/install.sh with the system python3.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from appenv import load_envs, sort_key

OPEN = "/usr/local/bin/creative-open"
RC_NS = "http://openbox.org/3.4/rc"
MENU_NS = "http://openbox.org/3.4/menu"
CLASS_GLOB = "ai.storyteller.*"
MENU_SHORTCUT = "C-A-space"
CATEGORY_ICON = {"Documenti": "Office", "Grafica": "Graphics", "Audio e video": "AudioVideo"}


def installed_apps(apps_dir: Path, bin_dir: Path, icons_root: Path | None = None) -> list[dict]:
    apps = []
    for name, env in load_envs(apps_dir).items():
        if not (bin_dir / name).is_file():
            continue
        apps.append({
            "name": name,
            "label": env.get("LABEL") or name.capitalize(),
            "category": env.get("CATEGORY") or "Altro",
            "icon": find_icon(icons_root, name),
            "_sort": sort_key(env, name),
        })
    apps.sort(key=lambda a: a["_sort"])
    return apps


def find_icon(icons_root: Path | None, name: str) -> str | None:
    """The app's own icon from its source tree, largest size first, if the sources are present."""
    if icons_root is None:
        return None
    base = icons_root / name / "assets" / "app-icon" / "hicolor"
    for size in ("512x512", "256x256", "128x128", "64x64", "48x48"):
        path = base / size / "apps" / f"ai.storyteller.{name}.png"
        if path.is_file():
            return str(path)
    return None


def by_category(apps: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for app in apps:
        groups.setdefault(app["category"], []).append(app)
    return groups


# --- Openbox ---------------------------------------------------------------------------------


def openbox_menu(apps: list[dict]) -> str:
    ET.register_namespace("", MENU_NS)
    q = lambda tag: f"{{{MENU_NS}}}{tag}"
    root = ET.Element(q("openbox_menu"))
    menu = ET.SubElement(root, q("menu"), id="root-menu", label="Creative Suite")

    def item(parent, label, command):
        node = ET.SubElement(parent, q("item"), label=label)
        action = ET.SubElement(node, q("action"), name="Execute")
        ET.SubElement(action, q("command")).text = command

    for index, (category, members) in enumerate(by_category(apps).items()):
        sub = ET.SubElement(menu, q("menu"), id=f"creative-cat-{index}", label=category)
        for app in members:
            item(sub, app["label"], f"{OPEN} {app['name']}")
    ET.SubElement(menu, q("separator"))
    item(menu, "Terminale", "x-terminal-emulator")
    reconfigure = ET.SubElement(menu, q("item"), label="Ricarica configurazione")
    ET.SubElement(reconfigure, q("action"), name="Reconfigure")
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def openbox_rc(system_rc: str) -> str:
    """Openbox's stock rc.xml plus: creative app windows maximised and focused, and a menu shortcut."""
    ET.register_namespace("", RC_NS)
    ET.register_namespace("xi", "http://www.w3.org/2001/XInclude")
    root = ET.fromstring(system_rc, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    q = lambda tag: f"{{{RC_NS}}}{tag}"

    applications = root.find(q("applications"))
    if applications is None:
        applications = ET.SubElement(root, q("applications"))
    for old in applications.findall(q("application")):
        if old.get("class") == CLASS_GLOB:
            applications.remove(old)
    rule = ET.SubElement(applications, q("application"), {"class": CLASS_GLOB})
    ET.SubElement(rule, q("maximized")).text = "yes"
    ET.SubElement(rule, q("focus")).text = "yes"

    keyboard = root.find(q("keyboard"))
    if keyboard is None:
        keyboard = ET.SubElement(root, q("keyboard"))
    for old in keyboard.findall(q("keybind")):
        if old.get("key") == MENU_SHORTCUT:
            keyboard.remove(old)
    bind = ET.SubElement(keyboard, q("keybind"), key=MENU_SHORTCUT)
    show = ET.SubElement(bind, q("action"), name="ShowMenu")
    ET.SubElement(show, q("menu")).text = "root-menu"

    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


# --- Sunshine --------------------------------------------------------------------------------


def sunshine_apps(apps: list[dict]) -> str:
    entries = [{"name": "Desktop", "image-path": "desktop.png"}]
    for app in apps:
        entry = {"name": app["label"]}
        if app["icon"]:
            entry["image-path"] = app["icon"]
        # No cmd: the stream shows the shared desktop. The app is started and raised before video
        # begins, and left running when the client quits (unsaved work is not thrown away).
        entry["prep-cmd"] = [{"do": f"{OPEN} {app['name']}", "undo": ""}]
        entries.append(entry)
    return json.dumps({"env": {"PATH": "$(PATH):$(HOME)/.local/bin"}, "apps": entries}, indent=2) + "\n"


# --- tint2 panel and .desktop launchers --------------------------------------------------------

TINT2_HEAD = """\
# Generated by deploy/gen-session-config.py - edit deploy/apps/*.env, not this file.

# Background 1: panel
rounded = 0
border_width = 0
border_sides = TBLR
background_color = #1b1b21 100
border_color = #000000 0
background_color_hover = #1b1b21 100
border_color_hover = #000000 0
background_color_pressed = #1b1b21 100
border_color_pressed = #000000 0

# Background 2: launcher buttons and idle tasks
rounded = 6
border_width = 0
border_sides = TBLR
background_color = #000000 0
border_color = #000000 0
background_color_hover = #3a3a46 100
border_color_hover = #000000 0
background_color_pressed = #55556a 100
border_color_pressed = #000000 0

# Background 3: the task that has focus
rounded = 6
border_width = 0
border_sides = TBLR
background_color = #4a6fa5 100
border_color = #000000 0
background_color_hover = #5a80b8 100
border_color_hover = #000000 0
background_color_pressed = #5a80b8 100
border_color_pressed = #000000 0

# Panel
panel_items = LTC
panel_size = 100% 48
panel_margin = 0 0
panel_padding = 6 4 6
panel_background_id = 1
wm_menu = 1
panel_dock = 0
panel_position = bottom center horizontal
panel_layer = top
panel_monitor = all
strut_policy = follow_size
autohide = 0

# Launcher
launcher_padding = 4 4 6
launcher_background_id = 0
launcher_icon_size = 36
launcher_icon_asb = 100 0 0
launcher_tooltip = 1

# Task bar
taskbar_mode = single_desktop
taskbar_padding = 8 0 4
taskbar_background_id = 0
task_text = 1
task_icon = 1
task_centered = 1
task_maximum_size = 200 40
task_padding = 8 4 6
task_font_color = #dddddd 100
task_active_font_color = #ffffff 100
task_background_id = 2
task_active_background_id = 3
urgent_nb_of_blink = 8

# Clock
time1_format = %H:%M
time1_font = Sans Bold 11
clock_font_color = #dddddd 100
clock_padding = 8 0
clock_background_id = 0
"""


def desktop_name(app: dict) -> str:
    return f"creative-{app['name']}.desktop"


def desktop_file(app: dict) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={app['label']}",
        f"Exec={OPEN} {app['name']}",
        f"Icon={app['icon'] or 'applications-graphics'}",
        f"Categories={CATEGORY_ICON.get(app['category'], 'Utility')};",
        f"StartupWMClass=ai.storyteller.{app['name']}",
        "Terminal=false",
    ]
    return "\n".join(lines) + "\n"


def tint2rc(apps: list[dict], desktop_dir: Path) -> str:
    launchers = "\n".join(f"launcher_item_app = {desktop_dir / desktop_name(a)}" for a in apps)
    return TINT2_HEAD + "\n" + launchers + "\n"


# --- CLI -------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apps-dir", type=Path, default=here / "apps")
    ap.add_argument("--bin-dir", type=Path, default=Path("/opt/creative-suite/bin"))
    ap.add_argument("--icons-root", type=Path, default=Path("/workspace/src"))
    ap.add_argument("--system-rc", type=Path, default=Path("/etc/xdg/openbox/rc.xml"))
    ap.add_argument("--openbox-menu", type=Path, required=True)
    ap.add_argument("--openbox-rc", type=Path, required=True)
    ap.add_argument("--sunshine-apps", type=Path, required=True)
    ap.add_argument("--tint2rc", type=Path, required=True)
    ap.add_argument("--desktop-dir", type=Path, required=True)
    args = ap.parse_args(argv)

    apps = installed_apps(args.apps_dir, args.bin_dir, args.icons_root)
    args.desktop_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.desktop_dir.glob("creative-*.desktop"):
        stale.unlink()  # an app that was uninstalled must disappear from the launchers
    for app in apps:
        (args.desktop_dir / desktop_name(app)).write_text(desktop_file(app))
    outputs = {
        args.openbox_menu: openbox_menu(apps),
        args.openbox_rc: openbox_rc(args.system_rc.read_text()),
        args.sunshine_apps: sunshine_apps(apps),
        args.tint2rc: tint2rc(apps, args.desktop_dir),
    }
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(f"gen-session-config: {len(apps)} apps: {', '.join(a['name'] for a in apps) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
