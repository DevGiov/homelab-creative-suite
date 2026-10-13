import json
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent
RUN = DEPLOY / "bin" / "creative-run"


@pytest.fixture
def fake_bin(tmp_path):
    """A bin dir whose apps print their argv and a marker env var as JSON."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = '#!/bin/sh\nprintf \'{"argv": ["%s"], "lp": "%s"}\' "$(printf \'%s\' "$*" | sed \'s/ /","/g\')" "$LP_NUM_THREADS"\n'
    for name in ("deckcraft", "photocraft", "pdfcraft"):
        path = bin_dir / name
        path.write_text(script)
        path.chmod(0o755)
    return bin_dir


def run(fake_bin, app, **env):
    full = {"PATH": os.environ["PATH"], "CREATIVE_BIN_DIR": str(fake_bin), **env}
    res = subprocess.run([str(RUN), app], capture_output=True, text=True, env=full, check=False)
    return res


def argv(res):
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)["argv"]


def test_plain_app_gets_control_port(fake_bin):
    assert argv(run(fake_bin, "deckcraft", CONTROL_PORT="7979", LP_NUM_THREADS="1")) == ["--control", "7979"]


def test_token_file_app_gets_port_token_file_and_extra_args(fake_bin):
    res = run(fake_bin, "photocraft", AUTH="token-file", CONTROL_PORT="7878", TOKEN_FILE="/run/x.token",
              APP_ARGS="--automation-read-root /workspace", LP_NUM_THREADS="1")
    assert argv(res) == ["--control", "7878", "--control-token-file", "/run/x.token",
                         "--automation-read-root", "/workspace"]


def test_control_file_app_gets_the_file_not_a_port(fake_bin):
    res = run(fake_bin, "pdfcraft", AUTH="control-file", CONTROL_FILE="/run/p.control", LP_NUM_THREADS="1")
    assert argv(res) == ["--control", "/run/p.control"]


def test_environment_is_passed_through_to_the_app(fake_bin):
    res = run(fake_bin, "deckcraft", CONTROL_PORT="1", LP_NUM_THREADS="3")
    assert json.loads(res.stdout)["lp"] == "3"


@pytest.mark.parametrize("env,message", [
    ({}, "CONTROL_PORT"),
    ({"AUTH": "token-file", "CONTROL_PORT": "1"}, "TOKEN_FILE"),
    ({"AUTH": "control-file"}, "CONTROL_FILE"),
    ({"AUTH": "magic", "CONTROL_PORT": "1"}, "unknown AUTH"),
])
def test_incomplete_env_fails_loudly(fake_bin, env, message):
    res = run(fake_bin, "deckcraft", **env)
    assert res.returncode != 0
    assert message in res.stderr


def test_every_registry_file_builds_a_command_line(fake_bin):
    """Each deploy/apps/*.env, loaded as systemd would, yields a launchable command."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("srv", DEPLOY.parent / "mcp-server" / "server.py")
    parse = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parse)
    for env_file in sorted((DEPLOY / "apps").glob("*.env")):
        env = parse.parse_env_file(env_file.read_text())
        app = env_file.stem
        (fake_bin / app).write_text((fake_bin / "deckcraft").read_text())
        (fake_bin / app).chmod(0o755)
        res = run(fake_bin, app, **env)
        assert res.returncode == 0, f"{app}: {res.stderr}"
        assert argv(res)[0] == "--control", app
