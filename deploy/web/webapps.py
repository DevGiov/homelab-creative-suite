#!/usr/bin/env python3
"""Manifest tool for the browser (WASM) suite: deploy/web/apps.tsv is the one source of its apps.

  webapps.py list               app, owner, version and sha256 of each app, for install.sh
  webapps.py landing OUT        write the landing page
  webapps.py bump [app ...]     move apps to their latest upstream release (rewrites apps.tsv)
"""
import csv
import html
import json
import sys
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "apps.tsv"
FIELDS = ("app", "title", "category", "description", "note", "owner", "version", "sha256")
DOMAIN = "lan.devgiov.com"
CATEGORIES = ("Documenti", "Grafica", "CAD", "Audio e video")

PAGE = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Creative Suite</title>
<style>
:root {{ color-scheme: light dark; --bg: #f5f5f4; --card: #fff; --text: #1c1917; --muted: #57534e; --line: #d6d3d1; --accent: #b4530a; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1c1917; --card: #292524; --text: #f5f5f4; --muted: #a8a29e; --line: #44403c; --accent: #f59e0b; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, sans-serif; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 32px 16px 48px; }}
h1 {{ margin: 0 0 8px; font-size: 28px; }}
h2 {{ margin: 32px 0 12px; font-size: 16px; color: var(--muted); }}
p {{ margin: 0; color: var(--muted); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
a.card {{ display: block; padding: 16px; background: var(--card); border: 1px solid var(--line); border-radius: 8px; color: inherit; text-decoration: none; }}
a.card:hover, a.card:focus-visible {{ border-color: var(--accent); }}
.name {{ display: flex; justify-content: space-between; gap: 8px; font-weight: 600; }}
.version {{ color: var(--muted); font-size: 13px; font-weight: 400; }}
.note {{ margin-top: 8px; font-size: 13px; }}
</style>
</head>
<body>
<main>
<h1>Creative Suite</h1>
<p>Le app girano nel browser di questo dispositivo: i file restano qui, non sul NAS, e gli agenti non possono vederle.
Per i progetti in <code>/workspace</code> e il lavoro con gli agenti usa il desktop completo.</p>
<h2>Desktop completo</h2>
<div class="grid">
<a class="card" href="https://creative.{domain}/"><div class="name">Moonlight Web</div><p>Tutte le app in streaming dalla workstation.</p></a>
</div>
{sections}
</main>
</body>
</html>
"""


def read_manifest(path=MANIFEST):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))
    for row in rows:
        missing = [field for field in FIELDS if field != "note" and not row.get(field)]
        if missing:
            raise ValueError(f"{row.get('app', '?')}: missing {', '.join(missing)}")
    return rows


def write_manifest(rows, path=MANIFEST):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, FIELDS, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render_landing(rows):
    sections = []
    for category in CATEGORIES:
        cards = []
        for row in rows:
            if row["category"] != category:
                continue
            note = f'<p class="note">{html.escape(row["note"])}</p>' if row["note"] else ""
            cards.append(
                f'<a class="card" href="https://{html.escape(row["app"])}.{DOMAIN}/">'
                f'<div class="name">{html.escape(row["title"])}'
                f'<span class="version">{html.escape(row["version"])}</span></div>'
                f'<p>{html.escape(row["description"])}</p>{note}</a>'
            )
        if cards:
            sections.append(f'<h2>{html.escape(category)}</h2>\n<div class="grid">\n' + "\n".join(cards) + "\n</div>")
    return PAGE.format(domain=DOMAIN, sections="\n".join(sections))


def web_asset(release, app):
    """The sha256 and version of the web bundle in a GitHub release object."""
    version = release["tag_name"].removeprefix("v")
    name = f"{app}-web-{version}.zip"
    for asset in release.get("assets", []):
        if asset["name"] == name and asset.get("digest", "").startswith("sha256:"):
            return version, asset["digest"].removeprefix("sha256:")
    raise LookupError(f"{app}: {name} with a digest not found in {release['tag_name']}")


def bump(names):
    rows = read_manifest()
    for row in rows:
        if names and row["app"] not in names:
            continue
        url = f"https://api.github.com/repos/{row['owner']}/{row['app']}/releases/latest"
        with urllib.request.urlopen(url, timeout=30) as response:
            version, sha256 = web_asset(json.load(response), row["app"])
        if version != row["version"]:
            print(f"{row['app']}: {row['version']} -> {version}")
        row["version"], row["sha256"] = version, sha256
    write_manifest(rows)


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    if command == "list":
        for row in read_manifest():
            print(row["app"], row["owner"], row["version"], row["sha256"])
    elif command == "landing" and len(argv) == 3:
        Path(argv[2]).write_text(render_landing(read_manifest()), encoding="utf-8")
    elif command == "bump":
        bump(set(argv[2:]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
