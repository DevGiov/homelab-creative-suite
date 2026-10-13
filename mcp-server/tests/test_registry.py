import pytest

import server
from server import load_apps, parse_env_file

ALL_APPS = {"deckcraft", "wordcraft", "gridcraft", "photocraft", "vectorcraft", "cadcraft", "soundcraft",
            "designcraft", "pdfcraft", "lightcraft", "filmcraft", "effectcraft"}


def test_repo_registry_declares_all_twelve_apps_on_distinct_ports():
    apps = server.APPS
    assert set(apps) == ALL_APPS
    ports = [a.port for a in apps.values() if a.port is not None]
    assert len(ports) == len(set(ports))
    assert apps["deckcraft"].port == 7979
    assert apps["wordcraft"].open_method == "engine:file.open"
    assert all(a.label and a.category for a in apps.values())


def test_no_app_exposes_a_cli_action_that_would_hang_the_bridge():
    # `mcp`/`serve` speak stdio or block forever; the bridge runs CLIs to completion.
    for app in server.APPS.values():
        assert not app.cli_actions & {"mcp", "serve"}, app.name


def test_apps_with_special_channels_are_declared():
    photo, pdf = server.APPS["photocraft"], server.APPS["pdfcraft"]
    assert (photo.auth, photo.path_mode, photo.port) == ("token-file", "workspace-relative", 7878)
    assert (pdf.auth, pdf.exec_method, pdf.open_method, pdf.port) == ("control-file", "ui.command", "ui.open", None)


def test_parse_env_file_handles_comments_quotes_and_empty_values():
    # Quoted values keep their inner whitespace, as systemd's EnvironmentFile does.
    env = parse_env_file('# c\nCONTROL_PORT=1\nAPP_ARGS=\nCLI_ACTIONS="a b  c"\n')
    assert env == {"CONTROL_PORT": "1", "APP_ARGS": "", "CLI_ACTIONS": "a b  c"}
    assert set(env["CLI_ACTIONS"].split()) == {"a", "b", "c"}


def test_duplicate_ports_are_rejected(tmp_path):
    (tmp_path / "one.env").write_text("CONTROL_PORT=7979\n")
    (tmp_path / "two.env").write_text("CONTROL_PORT=7979\n")
    with pytest.raises(ValueError, match="share control port"):
        load_apps(tmp_path)


def test_missing_port_is_an_error(tmp_path):
    (tmp_path / "bad.env").write_text("CLI_ACTIONS=info\n")
    with pytest.raises(ValueError, match="CONTROL_PORT"):
        load_apps(tmp_path)


def test_tool_schemas_expose_real_parameters():
    # FastMCP builds schemas from the signature; the error-handling decorator must preserve it.
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
    assert set(tools) == {"app_command", "app_commands", "app_control", "app_cli", "session_launch",
                          "session_stop", "session_status", "screenshot", "workspace_files"}
    assert set(tools["app_cli"].parameters["properties"]) == {"app", "action", "args"}
    assert tools["app_cli"].parameters["required"] == ["app", "action"]
