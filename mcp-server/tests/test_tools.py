import subprocess
from pathlib import Path

import pytest

import server


class Recorder:
    """Stands in for subprocess.run and records every call."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.result = (returncode, stdout, stderr)

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        code, out, err = self.result
        return subprocess.CompletedProcess(args, code, out, err)


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder(stdout="ok")
    monkeypatch.setattr(server.subprocess, "run", rec)
    return rec


def assert_no_shell(rec):
    assert rec.calls, "expected at least one subprocess call"
    for args, kwargs in rec.calls:
        assert isinstance(args, list)
        assert not kwargs.get("shell")


def test_unknown_app_is_rejected(recorder):
    result = server.app_cli("photoshop", "info")
    assert result["ok"] is False
    assert "unknown app" in result["error"]
    assert recorder.calls == []


def test_cli_action_outside_allowlist_is_rejected(recorder):
    result = server.app_cli("deckcraft", "mcp")
    assert result["ok"] is False
    assert "not allowed" in result["error"]
    assert recorder.calls == []


def test_cli_runs_binary_with_confined_args(recorder, workspace):
    result = server.app_cli("wordcraft", "convert", ["docs/a.docx", "docs/a.pdf"])
    assert result["ok"] is True
    args, kwargs = recorder.calls[0]
    assert args == [str(server.BIN_DIR / "wordcraft-cli"), "convert",
                    str(workspace / "docs" / "a.docx"), "docs/a.pdf"]
    assert kwargs["cwd"] == workspace
    assert_no_shell(recorder)


def test_cli_rejects_escaping_args_before_running(recorder, workspace):
    result = server.app_cli("gridcraft", "cat", ["/etc/shadow"])
    assert result["ok"] is False
    assert recorder.calls == []


def test_cli_timeout_is_reported(monkeypatch, workspace):
    def boom(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 60)

    monkeypatch.setattr(server.subprocess, "run", boom)
    result = server.app_cli("deckcraft", "info", ["docs/a.docx"])
    assert result == {"ok": False, "error": "command timed out after 60s"}


def test_launch_rejects_file_outside_workspace_before_starting(recorder, workspace):
    result = server.session_launch("deckcraft", "/etc/passwd")
    assert result["ok"] is False
    assert recorder.calls == []


def test_launch_uses_systemd_without_shell(recorder, workspace, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "BIN_DIR", tmp_path)
    (tmp_path / "deckcraft").write_text("")
    ports = iter([False, True])
    monkeypatch.setattr(server, "is_port_open", lambda port, host="127.0.0.1": next(ports, True))
    result = server.session_launch("deckcraft")
    assert result == {"ok": True, "app": "deckcraft", "port": 7979}
    assert recorder.calls[0][0] == ["systemctl", "start", "creative-app@deckcraft.service"]
    assert_no_shell(recorder)


def test_launch_of_missing_binary_fails(recorder, workspace, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "BIN_DIR", tmp_path)
    result = server.session_launch("gridcraft")
    assert result["ok"] is False
    assert "not installed" in result["error"]
    assert recorder.calls == []


def test_launch_opens_file_with_declared_method(recorder, workspace, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "BIN_DIR", tmp_path)
    (tmp_path / "wordcraft").write_text("")
    monkeypatch.setattr(server, "is_port_open", lambda port, host="127.0.0.1": True)
    sent = []
    monkeypatch.setattr(server, "control_call", lambda spec, method, params=None, timeout=0: sent.append((method, params)) or {"ok": True})
    result = server.session_launch("wordcraft", "docs/a.docx")
    assert result["ok"] is True
    assert sent == [("engine.execute", {"command": "file.open", "params": {"path": str(workspace / "docs" / "a.docx")}})]


def test_stop_uses_systemd(recorder):
    server.session_stop("gridcraft")
    assert recorder.calls[0][0] == ["systemctl", "stop", "creative-app@gridcraft.service"]
    assert_no_shell(recorder)


def test_screenshot_keeps_only_basename_and_uses_display_size(monkeypatch, workspace):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "xdpyinfo":
            return subprocess.CompletedProcess(args, 0, "  dimensions:    2560x1440 pixels (677x381 millimeters)\n", "")
        out = args[-1]
        Path(out).write_bytes(b"png")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    result = server.screenshot("../../etc/evil")
    assert result["ok"] is True
    assert result["file_path"] == str(workspace / "screenshots" / "evil.png")
    assert result["resolution"] == "2560x1440"
    assert "2560x1440" in calls[1]
