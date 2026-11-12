from pathlib import Path

import pytest

import siteconf

DEPLOY = Path(__file__).resolve().parent.parent
TEMPLATE = (DEPLOY / "sunshine" / "sunshine.conf").read_text()
SITE = {"WORKSTATION_ADDRESS": "10.0.0.30", "WORKSTATION_NAMES": "workstation.example.local, creative.example.local"}


def settings(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def origins() -> list[str]:
    rendered = siteconf.render_sunshine(TEMPLATE, SITE, "workstation")
    return settings(rendered)["csrf_allowed_origins"].split(",")


def test_web_ui_origins_include_the_workstation_address():
    # Regression: pairing from https://<address>:47990 failed with "CSRF Protection Error".
    assert origins() == [
        "https://10.0.0.30",
        "https://workstation",
        "https://workstation.example.local",
        "https://creative.example.local",
    ]


def test_origins_use_the_form_sunshine_accepts():
    # config.cpp keeps only entries that start with https:// and are longer than 8 characters.
    for origin in origins():
        assert origin.startswith("https://") and len(origin) > len("https://")
        assert " " not in origin and not origin.endswith("/")


def test_names_are_optional_and_not_repeated():
    site = {"WORKSTATION_ADDRESS": "10.0.0.30", "WORKSTATION_NAMES": "workstation,,"}
    assert siteconf.sunshine_origins(site, "workstation") == ["https://10.0.0.30", "https://workstation"]
    assert siteconf.sunshine_origins({"WORKSTATION_ADDRESS": "10.0.0.30"}, "ws") == ["https://10.0.0.30", "https://ws"]


def test_the_template_names_no_installation():
    # The origins of a real workstation come from /etc/creative-suite/site.env, never from this repository.
    assert settings(TEMPLATE)["csrf_allowed_origins"] == "@CSRF_ALLOWED_ORIGINS@"
    assert "WORKSTATION_ADDRESS:?" in (DEPLOY / "moonlight" / "docker-compose.yaml").read_text()


def test_missing_settings_say_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_SUITE_SITE", str(tmp_path / "site.env"))
    with pytest.raises(siteconf.SiteError, match="site.example.env"):
        siteconf.read_site()
    (tmp_path / "site.env").write_text("# empty\nWEB_DOMAIN=\n")
    with pytest.raises(siteconf.SiteError, match="WORKSTATION_ADDRESS is not set"):
        siteconf.sunshine_origins(siteconf.read_site(), "ws")
    with pytest.raises(siteconf.SiteError, match="WEB_DOMAIN is not set"):
        siteconf.render_nginx("x", siteconf.read_site())


def test_example_site_file_has_every_setting():
    site = siteconf.read_site(DEPLOY / "site.example.env")
    assert siteconf.sunshine_origins(site, "ws")[0] == "https://10.0.0.30"
    assert site["WEB_DOMAIN"] == "apps.example.com"


def test_nginx_site_matches_only_the_configured_domain():
    import re

    rendered = siteconf.render_nginx((DEPLOY / "web" / "nginx.conf").read_text(), {"WEB_DOMAIN": "apps.example.com"})
    # nginx (PCRE) writes a named group as (?<name>...), Python as (?P<name>...)
    pattern = re.search(r"server_name ~(\S+);", rendered).group(1).replace("(?<site>", "(?P<site>")
    assert "@" not in rendered
    assert re.match(pattern, "gridcraft.apps.example.com").group("site") == "gridcraft"
    assert not re.match(pattern, "gridcraft.appsXexample.com")
    assert not re.match(pattern, "gridcraft.apps.example.com.evil.test")
