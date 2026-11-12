import importlib.util
import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("webapps", DEPLOY / "web" / "webapps.py")
webapps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(webapps)


def row(**overrides):
    base = {
        "app": "gridcraft",
        "title": "GridCraft",
        "category": "Documenti",
        "description": "Fogli di calcolo.",
        "note": "",
        "owner": "storytold",
        "version": "1.2.3",
        "sha256": "ab" * 32,
    }
    return base | overrides


def test_manifest_is_complete():
    rows = webapps.read_manifest()
    names = [r["app"] for r in rows]
    assert len(names) == len(set(names))
    built = re.search(r"ALL_APPS=\(([^)]*)\)", (DEPLOY / "build-apps.sh").read_text())[1].split()
    assert sorted(names) == sorted(built)
    for r in rows:
        assert r["category"] in webapps.CATEGORIES
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"]), r["app"]
        assert re.fullmatch(r"[a-z]+", r["app"])  # nginx maps the host to a folder with this pattern
        assert r["app"] not in ("apps", "creative")  # the landing page and Moonlight Web


def test_missing_field_is_refused(tmp_path):
    path = tmp_path / "apps.tsv"
    webapps.write_manifest([row(sha256="")], path)
    with pytest.raises(ValueError, match="gridcraft: missing sha256"):
        webapps.read_manifest(path)


def test_empty_note_survives_a_round_trip(tmp_path):
    path = tmp_path / "apps.tsv"
    webapps.write_manifest([row(), row(app="deckcraft", note="Attenzione")], path)
    assert [r["note"] for r in webapps.read_manifest(path)] == ["", "Attenzione"]


def test_landing_links_each_app_on_its_own_origin():
    rows = [row(), row(app="cadcraft", title="CADCraft", category="CAD", note="Salva spesso")]
    page = webapps.render_landing(rows, "apps.example.com")
    assert 'href="https://gridcraft.apps.example.com/"' in page
    assert 'href="https://cadcraft.apps.example.com/"' in page
    assert 'href="https://creative.apps.example.com/"' in page
    assert "Salva spesso" in page
    assert page.index("<h2>Documenti</h2>") < page.index("<h2>CAD</h2>")
    assert "<h2>Grafica</h2>" not in page


def test_landing_escapes_manifest_text():
    page = webapps.render_landing([row(description="<script>x</script>")], "apps.example.com")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_web_asset_reads_the_bundle_digest():
    release = {
        "tag_name": "v1.2.3",
        "assets": [
            {"name": "gridcraft-1.2.3-linux.tar.gz", "digest": "sha256:" + "00" * 32},
            {"name": "gridcraft-web-1.2.3.zip", "digest": "sha256:" + "ab" * 32},
        ],
    }
    assert webapps.web_asset(release, "gridcraft") == ("1.2.3", "ab" * 32)


def test_web_asset_refuses_a_release_without_a_bundle():
    with pytest.raises(LookupError, match="gridcraft"):
        webapps.web_asset({"tag_name": "v1.2.3", "assets": []}, "gridcraft")
