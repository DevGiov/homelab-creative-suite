#!/usr/bin/env python3
"""Site settings: the values that are true for one installation only.

They live in /etc/creative-suite/site.env on each machine (CREATIVE_SUITE_SITE overrides the path), never in
this repository; deploy/site.example.env documents them.

  siteconf.py get KEY                      print a setting, or fail saying what is missing
  siteconf.py sunshine-conf TEMPLATE OUT   write sunshine.conf with the allowed origins of this workstation
  siteconf.py nginx-conf TEMPLATE OUT      write the nginx site of the browser suite for its domain
"""
import os
import re
import socket
import sys
from pathlib import Path

DEFAULT_PATH = "/etc/creative-suite/site.env"
EXAMPLE = "deploy/site.example.env"


class SiteError(Exception):
    pass


def site_path():
    return Path(os.environ.get("CREATIVE_SUITE_SITE", DEFAULT_PATH))


def parse(text):
    settings = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            settings[key.strip()] = value.strip()
    return settings


def read_site(path=None):
    path = Path(path) if path is not None else site_path()
    if not path.is_file():
        raise SiteError(f"{path} not found: create it from {EXAMPLE}")
    return parse(path.read_text(encoding="utf-8"))


def require(site, key):
    value = site.get(key, "")
    if not value:
        raise SiteError(f"{key} is not set in {site_path()} (see {EXAMPLE})")
    return value


def sunshine_origins(site, hostname):
    """Origins the Sunshine web UI accepts: the workstation address, its host name and the extra names."""
    names = [require(site, "WORKSTATION_ADDRESS"), hostname]
    names += [name.strip() for name in site.get("WORKSTATION_NAMES", "").split(",")]
    origins = []
    for name in names:
        origin = f"https://{name}"
        if name and origin not in origins:
            origins.append(origin)
    return origins


def render_sunshine(template, site, hostname):
    return template.replace("@CSRF_ALLOWED_ORIGINS@", ",".join(sunshine_origins(site, hostname)))


def render_nginx(template, site):
    return template.replace("@WEB_DOMAIN_REGEX@", re.escape(require(site, "WEB_DOMAIN")))


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    try:
        site = read_site()
        if command == "get" and len(argv) == 3:
            print(require(site, argv[2]))
        elif command == "sunshine-conf" and len(argv) == 4:
            text = render_sunshine(Path(argv[2]).read_text(encoding="utf-8"), site, socket.gethostname())
            Path(argv[3]).write_text(text, encoding="utf-8")
        elif command == "nginx-conf" and len(argv) == 4:
            Path(argv[3]).write_text(render_nginx(Path(argv[2]).read_text(encoding="utf-8"), site), encoding="utf-8")
        else:
            sys.exit(__doc__)
    except SiteError as error:
        sys.exit(f"site settings: {error}")


if __name__ == "__main__":
    main(sys.argv)
