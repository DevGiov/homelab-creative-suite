import pytest

import server
from server import load_apps, parse_env_file


def test_repo_registry_declares_the_three_apps_on_distinct_ports():
    apps = server.APPS
    assert set(apps) == {"deckcraft", "wordcraft", "gridcraft"}
    assert len({a.port for a in apps.values()}) == len(apps)
    assert apps["deckcraft"].port == 7979
    assert "mcp" not in apps["deckcraft"].cli_actions  # stdio MCP would hang the bridge
    assert apps["wordcraft"].open_method == "engine:file.open"


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
    with pytest.raises(KeyError):
        load_apps(tmp_path)


def test_tool_schemas_expose_real_parameters():
    # FastMCP builds schemas from the signature; the error-handling decorator must preserve it.
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
    assert set(tools) == {"app_command", "app_control", "app_cli", "session_launch",
                          "session_stop", "session_status", "screenshot", "workspace_files"}
    assert set(tools["app_cli"].parameters["properties"]) == {"app", "action", "args"}
    assert tools["app_cli"].parameters["required"] == ["app", "action"]
