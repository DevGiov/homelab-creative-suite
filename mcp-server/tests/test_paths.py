import pytest

import server
from server import BridgeError, confine_params, resolve_workspace_path, sanitize_cli_args


def test_relative_path_resolves_inside(workspace):
    assert resolve_workspace_path("docs/a.docx") == workspace / "docs" / "a.docx"


def test_empty_path_is_workspace_root(workspace):
    assert resolve_workspace_path("") == workspace


def test_absolute_path_inside_is_accepted(workspace):
    assert resolve_workspace_path(str(workspace / "docs")) == workspace / "docs"


@pytest.mark.parametrize("path", ["../outside/secret.txt", "docs/../../outside", "/etc/passwd", "/"])
def test_escaping_paths_are_rejected(workspace, path):
    with pytest.raises(BridgeError):
        resolve_workspace_path(path)


def test_sibling_with_common_prefix_is_rejected(workspace):
    # /tmp/x/workspace-evil must not pass a naive startswith("/tmp/x/workspace") check
    evil = workspace.parent / (workspace.name + "-evil")
    evil.mkdir()
    with pytest.raises(BridgeError):
        resolve_workspace_path(str(evil))


def test_symlink_out_of_workspace_is_rejected(workspace):
    (workspace / "link").symlink_to(workspace.parent / "outside")
    with pytest.raises(BridgeError):
        resolve_workspace_path("link/secret.txt")


def test_cli_args_confine_paths_and_keep_other_args(workspace):
    args = sanitize_cli_args(["docs/a.docx", "--page", "2", "=SUM(A1:A9)/2", '{"text": "a/b"}'])
    assert args == [str(workspace / "docs" / "a.docx"), "--page", "2", "=SUM(A1:A9)/2", '{"text": "a/b"}']


@pytest.mark.parametrize("arg", ["/etc/shadow", "../outside/secret.txt", "~/.ssh/id_rsa"])
def test_cli_args_reject_escapes(workspace, arg):
    with pytest.raises(BridgeError):
        sanitize_cli_args(["docs/a.docx", arg])


def test_cli_args_reject_existing_symlink_out(workspace):
    (workspace / "out.pdf").symlink_to(workspace.parent / "outside" / "secret.txt")
    with pytest.raises(BridgeError):
        sanitize_cli_args(["out.pdf"])


def test_confine_params_rewrites_path_only(workspace):
    assert confine_params({"path": "docs/a.docx", "page": 1}) == {"path": str(workspace / "docs" / "a.docx"), "page": 1}
    assert confine_params(None) == {}
    with pytest.raises(BridgeError):
        confine_params({"path": "/etc/passwd"})


def test_workspace_files_rejects_traversal(workspace):
    assert server.workspace_files("../outside")["ok"] is False
    listing = server.workspace_files("docs")
    assert listing["ok"] is True
    assert [i["name"] for i in listing["items"]] == ["a.docx"]
