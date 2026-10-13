"""Command discovery and output limits: raw command listings are 19-314 KB per app."""

import json
import socket
import threading

import pytest

import server
from server import AppSpec


class ListingApp:
    """A control server that answers one request with a canned reply."""

    def __init__(self, reply):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.reply, self.methods = reply, []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn, conn.makefile("rw", encoding="utf-8") as f:
                msg = json.loads(f.readline())
                self.methods.append(msg["method"])
                f.write(json.dumps({"id": msg["id"], "ok": True, "result": self.reply}) + "\n")
                f.flush()


def commands(n=300):
    items = [{"id": f"layer.op{i}", "label": f"Layer operation {i}", "menu": ["Layer"], "params": "{x?: n}" + "p" * 400,
              "enabled": i % 2 == 0, "shortcut": ""} for i in range(n)]
    items += [
        {"id": "shape.rectangle", "label": "Rectangle", "menu": ["Object", "Shape"], "params": "{x, y, width, height}", "enabled": True},
        {"id": "file.saveAs", "label": "Save As", "menu": "File", "params": "{path?}", "enabled": True, "shortcut": "Ctrl+Shift+S"},
    ]
    return items


@pytest.fixture
def app(monkeypatch):
    def make(reply, **spec):
        fake = ListingApp(reply)
        s = AppSpec(name="fake", port=fake.port, cli_actions=frozenset(), open_method="app.open", **spec)
        monkeypatch.setitem(server.APPS, "fake", s)
        return fake

    return make


def test_filter_matches_id_label_and_menu_case_insensitively(app):
    app(commands())
    out = server.app_commands("fake", "RECT")
    assert out["ok"] and [c["id"] for c in out["commands"]] == ["shape.rectangle"]
    assert [c["id"] for c in server.app_commands("fake", "save as")["commands"]] == ["file.saveAs"]
    assert [c["id"] for c in server.app_commands("fake", "object shape")["commands"]] == ["shape.rectangle"]  # all terms, any field


def test_results_are_limited_and_report_the_total(app):
    app(commands(300))
    out = server.app_commands("fake", "layer", limit=10)
    assert len(out["commands"]) == 10
    assert out["matched"] == 150 and out["total"] == 302 and out["truncated"] is True  # half are disabled


def test_default_limit_keeps_the_reply_small(app):
    app(commands(300))
    out = server.app_commands("fake")
    assert len(out["commands"]) == server.DEFAULT_COMMAND_LIMIT
    assert len(json.dumps(out)) < 12_000


def test_parameter_docs_are_shortened(app):
    app(commands(5))
    out = server.app_commands("fake", "op0")
    assert len(out["commands"][0]["params"]) <= server.PARAMS_PREVIEW + 1
    assert out["commands"][0]["params"].endswith("…")


def test_only_enabled_commands_unless_asked(app):
    app(commands(10))
    enabled = server.app_commands("fake", "layer", limit=50)
    assert all(c["enabled"] for c in enabled["commands"]) and enabled["matched"] == 5
    everything = server.app_commands("fake", "layer", limit=50, include_disabled=True)
    assert everything["matched"] == 10


def test_pdfcraft_style_listing_and_ui_command_method(app):
    fake = app({"commands": commands(3)}, exec_method="ui.command")
    out = server.app_commands("fake", "rect")
    assert [c["id"] for c in out["commands"]] == ["shape.rectangle"]
    assert fake.methods == ["ui.commands"]


def test_engine_commands_is_used_by_default(app):
    fake = app(commands(3))
    server.app_commands("fake")
    assert fake.methods == ["engine.commands"]


def test_limit_is_clamped(app):
    app(commands(300))
    big = server.app_commands("fake", "layer", limit=10_000, include_disabled=True)
    assert len(big["commands"]) == server.MAX_COMMAND_LIMIT and big["matched"] == 300
    assert len(server.app_commands("fake", "layer", limit=0)["commands"]) == 1


def test_app_not_running_is_reported(monkeypatch):
    s = AppSpec(name="fake", port=1, cli_actions=frozenset(), open_method="app.open")
    monkeypatch.setitem(server.APPS, "fake", s)
    out = server.app_commands("fake", "x")
    assert out["ok"] is False and "not running" in out["error"]


def test_cli_output_is_capped_with_a_pointer_to_app_commands(monkeypatch, workspace):
    import subprocess

    big = "x" * (server.MAX_CLI_OUTPUT * 3)
    monkeypatch.setattr(server.subprocess, "run", lambda a, **k: subprocess.CompletedProcess(a, 0, big, "warn"))
    out = server.app_cli("deckcraft", "commands")
    assert out["ok"] is True
    assert len(out["stdout"]) < server.MAX_CLI_OUTPUT + 300
    assert out["truncated"] == {"stdout": len(big)}
    assert "app_commands" in out["stdout"]
    assert out["stderr"] == "warn"


def test_small_cli_output_is_untouched(monkeypatch, workspace):
    import subprocess

    monkeypatch.setattr(server.subprocess, "run", lambda a, **k: subprocess.CompletedProcess(a, 0, "12\n", ""))
    out = server.app_cli("gridcraft", "eval", ["=1+1"])
    assert out == {"ok": True, "stdout": "12\n", "stderr": "", "returncode": 0}


def test_status_does_not_report_the_port_of_a_stopped_control_file_app(monkeypatch, tmp_path):
    control = tmp_path / "pdf.control"
    control.write_text(json.dumps({"port": 42227, "token": "t", "pid": 1}))
    s = AppSpec(name="pdfcraft", port=None, cli_actions=frozenset(), open_method="ui.open", auth="control-file", control_file=control)
    monkeypatch.setattr(server, "APPS", {"pdfcraft": s})
    monkeypatch.setattr(server, "unit_state", lambda app: "inactive")
    monkeypatch.setattr(server, "visible_windows", list)
    out = server.session_status()
    assert out["apps"]["pdfcraft"]["port"] is None and out["apps"]["pdfcraft"]["port_open"] is False
