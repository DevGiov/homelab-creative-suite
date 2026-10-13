import json
import socket
import threading

import pytest

import server
from server import AppSpec, BridgeError, control_call


class FakeApp:
    """A one-connection JSON-lines control server mimicking apps/*/src/control_server.rs."""

    def __init__(self, reply=None, silent=False):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.received = []
        self.reply = reply
        self.silent = silent
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.sock.accept()
        with conn, conn.makefile("rw", encoding="utf-8") as f:
            msg = json.loads(f.readline())
            self.received.append(msg)
            if self.silent:
                conn.recv(1)  # hold the connection open without answering
                return
            reply = self.reply if self.reply is not None else {"ok": True, "result": msg["method"]}
            f.write((reply if isinstance(reply, str) else json.dumps({**reply, "id": msg["id"]})) + "\n")
            f.flush()

    def spec(self):
        return AppSpec(name="fake", port=self.port, cli_actions=frozenset(), open_method="app.open")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_round_trip_sends_method_params_and_strips_id():
    app = FakeApp()
    result = control_call(app.spec(), "ui.inspect", {"a": 1})
    assert result == {"ok": True, "result": "ui.inspect"}
    assert app.received[0]["method"] == "ui.inspect"
    assert app.received[0]["params"] == {"a": 1}
    assert isinstance(app.received[0]["id"], int)


def test_missing_params_are_sent_as_empty_object():
    app = FakeApp()
    control_call(app.spec(), "engine.commands")
    assert app.received[0]["params"] == {}


def test_refused_connection_names_the_app():
    spec = AppSpec(name="deckcraft", port=free_port(), cli_actions=frozenset(), open_method="app.open")
    with pytest.raises(BridgeError, match="deckcraft is not running"):
        control_call(spec, "ui.inspect")


def test_silent_app_times_out():
    app = FakeApp(silent=True)
    with pytest.raises(BridgeError, match="did not answer"):
        control_call(app.spec(), "ui.inspect", timeout=0.5)


def test_invalid_json_reply_is_reported():
    app = FakeApp(reply="not json")
    with pytest.raises(BridgeError, match="invalid JSON"):
        control_call(app.spec(), "ui.inspect")


def test_app_command_wraps_engine_execute(monkeypatch, workspace):
    app = FakeApp()
    monkeypatch.setitem(server.APPS, "fake", app.spec())
    result = server.app_command("fake", "file.saveAs", {"path": "docs/out.docx"})
    assert result["ok"] is True
    sent = app.received[0]
    assert sent["method"] == "engine.execute"
    assert sent["params"] == {"command": "file.saveAs", "params": {"path": str(workspace / "docs" / "out.docx")}}


def test_app_control_rejects_path_outside_workspace(monkeypatch, workspace):
    monkeypatch.setitem(server.APPS, "fake", FakeApp().spec())
    result = server.app_control("fake", "ui.screenshot", {"path": "/tmp/x.png"})
    assert result["ok"] is False
    assert "outside" in result["error"]
