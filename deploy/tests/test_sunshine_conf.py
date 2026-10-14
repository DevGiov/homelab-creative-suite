from pathlib import Path

CONF = Path(__file__).resolve().parent.parent / "sunshine" / "sunshine.conf"


def settings() -> dict[str, str]:
    out = {}
    for line in CONF.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def test_web_ui_origins_include_the_container_ip():
    # Regression: pairing from https://192.168.1.189:47990 failed with "CSRF Protection Error".
    origins = settings()["csrf_allowed_origins"].split(",")
    assert "https://192.168.1.189" in origins


def test_origins_use_the_form_sunshine_accepts():
    # config.cpp keeps only entries that start with https:// and are longer than 8 characters.
    for origin in settings()["csrf_allowed_origins"].split(","):
        assert origin.startswith("https://") and len(origin) > len("https://")
        assert " " not in origin and not origin.endswith("/")
