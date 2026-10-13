#!/usr/bin/env python3
"""
End-to-end check of the Creative Suite MCP bridge through a real MCP client (Streamable HTTP).

    /opt/creative-suite/mcp-server/.venv/bin/python3 deploy/mcp-e2e.py [http://127.0.0.1:7900/mcp]

Exercises every tool against every installed app, plus the refusals (path traversal, unknown
app, CLI action outside the allowlist). Exits non-zero if any check fails.
"""

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7900/mcp"
EDITS = {
    "deckcraft": ("slide.new", {}),
    "wordcraft": ("text.insert", {"text": "mcp-e2e "}),
    "gridcraft": ("cell.set", {"cell": "A1", "input": "mcp-e2e"}),
}
failures = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global failures
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures += 1
        print(f"      {str(detail)[:300]}")


async def call(session: ClientSession, tool: str, **args) -> dict:
    result = await session.call_tool(tool, args)
    if result.isError:
        return {"ok": False, "error": result.content[0].text if result.content else "tool error"}
    return result.structuredContent or json.loads(result.content[0].text)


async def main() -> int:
    async with streamablehttp_client(URL) as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        tools = {t.name for t in (await session.list_tools()).tools}
        expected = {"app_command", "app_control", "app_cli", "session_launch", "session_stop",
                    "session_status", "screenshot", "workspace_files"}
        check("tool list", tools == expected, tools)

        status = await call(session, "session_status")
        apps = [name for name, a in status.get("apps", {}).items() if a["installed"]]
        check("session_status", status.get("ok") and apps, status)

        for app in apps:
            launched = await call(session, "session_launch", app=app)
            check(f"{app}: session_launch", launched.get("ok"), launched)
            inspect = await call(session, "app_control", app=app, method="ui.inspect")
            check(f"{app}: app_control ui.inspect", inspect.get("ok"), inspect)
            command, params = EDITS[app]
            edited = await call(session, "app_command", app=app, command=command, params=params)
            check(f"{app}: app_command {command}", edited.get("ok"), edited)
            cli = await call(session, "app_cli", app=app, action="commands")
            check(f"{app}: app_cli commands", cli.get("ok") and cli.get("stdout"), cli)

        shot = await call(session, "screenshot", filename="mcp-e2e.png")
        check("screenshot", shot.get("ok") and shot.get("size_bytes", 0) > 1000, shot)
        files = await call(session, "workspace_files", subpath="screenshots")
        check("workspace_files", files.get("ok") and any(i["name"] == "mcp-e2e.png" for i in files["items"]), files)

        refused = {
            "workspace_files traversal": await call(session, "workspace_files", subpath="../etc"),
            "app_cli absolute path": await call(session, "app_cli", app="wordcraft", action="info", args=["/etc/shadow"]),
            "app_cli action not allowed": await call(session, "app_cli", app="deckcraft", action="mcp"),
            "unknown app": await call(session, "app_control", app="photoshop", method="ui.inspect"),
            "screenshot path param outside": await call(session, "app_control", app=apps[0], method="ui.screenshot",
                                                        params={"path": "/root/x.png"}),
        }
        for name, result in refused.items():
            check(f"refuses {name}", result.get("ok") is False, result)

    print(f"\n{failures} check(s) failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
