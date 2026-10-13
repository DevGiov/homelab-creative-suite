import pytest
from starlette.testclient import TestClient

import server

HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


@pytest.fixture(scope="module")
def client():
    # The MCP session manager can only be started once per process, so share one app lifespan.
    with TestClient(server.app) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert len(body["apps"]) == 12 and body["apps"] == sorted(body["apps"])


def test_stale_session_id_is_not_rejected(client):
    # Regression: after a bridge restart MetaMCP kept sending its old Mcp-Session-Id and every
    # call failed with 404 "Session not found". The bridge is stateless, so any id must work.
    res = client.post("/mcp", json=LIST_TOOLS, headers={**HEADERS, "mcp-session-id": "stale-from-before-restart"})
    assert res.status_code == 200, res.text
    assert "app_command" in res.text


def test_calls_work_without_initialize(client):
    res = client.post("/mcp", json=LIST_TOOLS, headers=HEADERS)
    assert res.status_code == 200, res.text
    assert "workspace_files" in res.text
