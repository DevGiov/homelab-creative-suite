"""Apps whose control channel needs authentication (PhotoCraft token file, PdfCraft control file)."""

import json
import socket
import threading

import pytest

import server
from server import AppSpec, BridgeError, control_call, load_apps

TOKEN = "ab" * 32


class AuthApp:
    """A control server that, like PhotoCraft/PdfCraft, demands `auth {token}` as the first line.

    style="okerr"   -> {"id","ok":true,"result"} / {"id","ok":false,"error":"..."}   (PhotoCraft)
    style="jsonrpc" -> {"jsonrpc","id","result"} / {"jsonrpc","id","error":{code,message}} (PdfCraft)
    """

    def __init__(self, token=TOKEN, style="okerr"):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.token, self.style = token, style
        self.lines = []  # every request line received, in order
        threading.Thread(target=self._serve, daemon=True).start()

    def _reply(self, msg, result=None, error=None):
        base = {"id": msg.get("id")}
        if self.style == "jsonrpc":
            base["jsonrpc"] = "2.0"
            return {**base, "error": {"code": -32001, "message": error}} if error else {**base, "result": result}
        return {**base, "ok": False, "error": error} if error else {**base, "ok": True, "result": result}

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._conn, args=(conn,), daemon=True).start()

    def _conn(self, conn):
        authed = False
        with conn, conn.makefile("rw", encoding="utf-8") as f:
            for line in f:
                msg = json.loads(line)
                self.lines.append(msg)
                if not authed:
                    if msg.get("method") == "auth" and msg.get("params", {}).get("token") == self.token:
                        authed = True
                        f.write(json.dumps(self._reply(msg, {"authenticated": True})) + "\n")
                    else:
                        f.write(json.dumps(self._reply(msg, error="authenticate first")) + "\n")
                        f.flush()
                        return
                else:
                    f.write(json.dumps(self._reply(msg, {"echo": msg["method"], "params": msg.get("params")})) + "\n")
                f.flush()

    def requests(self):
        return [m for m in self.lines if m.get("method") != "auth"]


def spec(app, tmp_path, **kw):
    base = {"name": "photocraft", "port": app.port, "cli_actions": frozenset(), "open_method": "app.open"}
    return AppSpec(**{**base, **kw})


def token_file(tmp_path, content=TOKEN + "\n"):
    path = tmp_path / "app.token"
    path.write_text(content)
    return path


def control_file(tmp_path, port, token=TOKEN):
    path = tmp_path / "app.control"
    path.write_text(json.dumps({"port": port, "token": token, "pid": 1}))
    return path


def test_token_file_app_authenticates_before_the_request(tmp_path):
    app = AuthApp()
    s = spec(app, tmp_path, auth="token-file", token_file=token_file(tmp_path))
    result = control_call(s, "ui.inspect", {"x": 1})
    assert result == {"ok": True, "result": {"echo": "ui.inspect", "params": {"x": 1}}}
    assert [m["method"] for m in app.lines] == ["auth", "ui.inspect"]
    assert app.lines[0]["params"] == {"token": TOKEN}


def test_wrong_token_is_reported_as_an_authentication_failure(tmp_path):
    app = AuthApp(token="cd" * 32)
    s = spec(app, tmp_path, auth="token-file", token_file=token_file(tmp_path))
    with pytest.raises(BridgeError, match="authentication"):
        control_call(s, "ui.inspect")
    assert app.requests() == []  # the real request never went out


def test_wordcraft_authenticates_with_key(tmp_path):
    class WordcraftAuthApp(AuthApp):
        def _conn(self, conn):
            authed = False
            with conn, conn.makefile("rw", encoding="utf-8") as f:
                for line in f:
                    msg = json.loads(line)
                    self.lines.append(msg)
                    if not authed:
                        if msg.get("method") == "auth" and msg.get("params", {}).get("key") == self.token:
                            authed = True
                            f.write(json.dumps(self._reply(msg, {})) + "\n")
                        else:
                            f.write(json.dumps(self._reply(msg, error="unauthorized")) + "\n")
                            f.flush()
                            return
                    else:
                        f.write(json.dumps(self._reply(msg, {"echo": msg["method"], "params": msg.get("params")})) + "\n")
                    f.flush()

    app = WordcraftAuthApp()
    s = spec(app, tmp_path, name="wordcraft", auth="token-file", token_file=token_file(tmp_path))
    result = control_call(s, "document.inspect")
    assert result == {"ok": True, "result": {"echo": "document.inspect", "params": {}}}
    assert [m["method"] for m in app.lines] == ["auth", "document.inspect"]
    assert app.lines[0]["params"] == {"key": TOKEN}


def test_missing_token_file_says_the_app_is_not_running(tmp_path):
    app = AuthApp()
    s = spec(app, tmp_path, auth="token-file", token_file=tmp_path / "absent.token")
    with pytest.raises(BridgeError, match="not running"):
        control_call(s, "ui.inspect")


def test_control_file_gives_dynamic_port_and_token_and_jsonrpc_replies_are_normalised(tmp_path):
    app = AuthApp(style="jsonrpc")
    s = spec(app, tmp_path, name="pdfcraft", port=None, auth="control-file", control_file=control_file(tmp_path, app.port))
    result = control_call(s, "ui.state")
    assert result == {"ok": True, "result": {"echo": "ui.state", "params": {}}}


def test_jsonrpc_error_becomes_ok_false_with_message(tmp_path):
    class Failing(AuthApp):
        def _reply(self, msg, result=None, error=None):
            if msg.get("method") == "ui.open":
                return super()._reply(msg, error="no such file")
            return super()._reply(msg, result, error)

    app = Failing(style="jsonrpc")
    s = spec(app, tmp_path, name="pdfcraft", port=None, auth="control-file", control_file=control_file(tmp_path, app.port))
    assert control_call(s, "ui.open", {"path": "x.pdf"}) == {"ok": False, "error": "no such file"}


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"port": 1}', '{"token": "x"}'])
def test_unusable_control_file_is_reported(tmp_path, content):
    path = tmp_path / "app.control"
    path.write_text(content)
    s = AppSpec(name="pdfcraft", port=None, cli_actions=frozenset(), open_method="ui.open",
                auth="control-file", control_file=path)
    with pytest.raises(BridgeError, match="control file"):
        control_call(s, "ui.state")


def test_missing_control_file_says_the_app_is_not_running(tmp_path):
    s = AppSpec(name="pdfcraft", port=None, cli_actions=frozenset(), open_method="ui.open",
                auth="control-file", control_file=tmp_path / "absent")
    with pytest.raises(BridgeError, match="not running"):
        control_call(s, "ui.state")


def test_ui_command_apps_get_command_id_not_engine_execute(tmp_path, monkeypatch, workspace):
    app = AuthApp(style="jsonrpc")
    s = spec(app, tmp_path, name="pdfcraft", port=None, auth="control-file", control_file=control_file(tmp_path, app.port),
             exec_method="ui.command", open_method="ui.open")
    monkeypatch.setitem(server.APPS, "pdfcraft", s)
    result = server.app_command("pdfcraft", "view.zoomIn", {"ignored": True})
    assert result["ok"] is True
    assert app.requests()[0]["method"] == "ui.command"
    assert app.requests()[0]["params"] == {"id": "view.zoomIn", "ignored": True}


def test_workspace_relative_apps_receive_relative_paths(tmp_path, monkeypatch, workspace):
    app = AuthApp()
    s = spec(app, tmp_path, auth="token-file", token_file=token_file(tmp_path), path_mode="workspace-relative")
    monkeypatch.setitem(server.APPS, "photocraft", s)
    assert server.app_control("photocraft", "app.open", {"path": "docs/a.docx"})["ok"] is True
    assert app.requests()[0]["params"] == {"path": "docs/a.docx"}
    assert server.app_control("photocraft", "app.open", {"path": str(workspace / "docs" / "a.docx")})["ok"] is True
    assert app.requests()[1]["params"] == {"path": "docs/a.docx"}


def test_workspace_relative_apps_still_refuse_traversal(tmp_path, monkeypatch, workspace):
    app = AuthApp()
    s = spec(app, tmp_path, auth="token-file", token_file=token_file(tmp_path), path_mode="workspace-relative")
    monkeypatch.setitem(server.APPS, "photocraft", s)
    result = server.app_control("photocraft", "app.open", {"path": "../outside/secret.txt"})
    assert result["ok"] is False and "outside" in result["error"]
    assert app.lines == []


def test_launch_opens_the_file_with_the_apps_open_method(tmp_path, monkeypatch, workspace):
    app = AuthApp(style="jsonrpc")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "pdfcraft").write_text("")
    monkeypatch.setattr(server, "BIN_DIR", bin_dir)
    s = spec(app, tmp_path, name="pdfcraft", port=None, auth="control-file", control_file=control_file(tmp_path, app.port),
             exec_method="ui.command", open_method="ui.open")
    monkeypatch.setitem(server.APPS, "pdfcraft", s)
    result = server.session_launch("pdfcraft", "docs/a.docx")
    assert result["ok"] is True
    assert app.requests()[0] == {**app.requests()[0], "method": "ui.open", "params": {"path": str(workspace / "docs" / "a.docx")}}


def test_status_reads_the_port_from_the_control_file(tmp_path):
    app = AuthApp()
    live = spec(app, tmp_path, name="pdfcraft", port=None, auth="control-file", control_file=control_file(tmp_path, app.port))
    assert server.app_port(live) == app.port
    assert server.port_is_open(live) is True
    gone = spec(app, tmp_path, name="pdfcraft", port=None, auth="control-file", control_file=tmp_path / "nope")
    assert server.app_port(gone) is None
    assert server.port_is_open(gone) is False


# --- registry validation ---------------------------------------------------------------------


def write(tmp_path, name, body):
    (tmp_path / f"{name}.env").write_text(body)


def test_registry_parses_auth_fields(tmp_path):
    write(tmp_path, "photocraft",
          "CONTROL_PORT=7878\nAUTH=token-file\nTOKEN_FILE=/run/creative-suite/photocraft.token\n"
          "PATH_MODE=workspace-relative\nLABEL=PhotoCraft\nCATEGORY=Grafica\n")
    write(tmp_path, "pdfcraft",
          "AUTH=control-file\nCONTROL_FILE=/run/creative-suite/pdfcraft.control\nEXEC_METHOD=ui.command\nOPEN_METHOD=ui.open\n")
    apps = load_apps(tmp_path)
    assert apps["photocraft"].auth == "token-file" and apps["photocraft"].port == 7878
    assert str(apps["photocraft"].token_file) == "/run/creative-suite/photocraft.token"
    assert apps["photocraft"].path_mode == "workspace-relative"
    assert apps["photocraft"].label == "PhotoCraft"
    assert apps["pdfcraft"].port is None and apps["pdfcraft"].exec_method == "ui.command"


def test_defaults_keep_existing_apps_unchanged(tmp_path):
    write(tmp_path, "deckcraft", "CONTROL_PORT=7979\n")
    app = load_apps(tmp_path)["deckcraft"]
    assert (app.auth, app.exec_method, app.path_mode) == ("none", "engine.execute", "absolute")
    assert app.label == "Deckcraft"


@pytest.mark.parametrize("body,message", [
    ("CONTROL_PORT=1\nAUTH=token-file\n", "TOKEN_FILE"),
    ("AUTH=control-file\n", "CONTROL_FILE"),
    ("CONTROL_PORT=1\nAUTH=magic\n", "AUTH"),
    ("CONTROL_PORT=1\nEXEC_METHOD=eval\n", "EXEC_METHOD"),
    ("CONTROL_PORT=1\nPATH_MODE=weird\n", "PATH_MODE"),
    ("AUTH=none\n", "CONTROL_PORT"),
])
def test_registry_rejects_inconsistent_apps(tmp_path, body, message):
    write(tmp_path, "bad", body)
    with pytest.raises(ValueError, match=message):
        load_apps(tmp_path)


def test_two_apps_without_a_fixed_port_do_not_clash(tmp_path):
    write(tmp_path, "a", "AUTH=control-file\nCONTROL_FILE=/run/a\n")
    write(tmp_path, "b", "AUTH=control-file\nCONTROL_FILE=/run/b\n")
    assert set(load_apps(tmp_path)) == {"a", "b"}
