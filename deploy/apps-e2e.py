#!/usr/bin/env python3
"""
Per-app end-to-end check through the MCP bridge (a real Streamable HTTP client), plus idle CPU.

    /opt/creative-suite/mcp-server/.venv/bin/python3 deploy/apps-e2e.py [app ...] [--url URL]

For every installed app (or the ones named): session_launch -> window present -> authenticated
ui.inspect -> a read-only command listing -> screenshot of the display (kept in
/workspace/screenshots/apps-<app>.png) -> idle CPU over a short window -> session_stop for apps
this run started. Prints a Markdown table; exits non-zero if any app failed a functional check.
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
URL = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--url=")), "http://127.0.0.1:7900/mcp")
SETTLE = 6.0  # seconds after the control channel answers, before measuring
WINDOW = 8.0  # seconds of CPU accounting
CLK = 100  # USER_HZ


async def call(session: ClientSession, tool: str, **args) -> dict:
    result = await session.call_tool(tool, args)
    if result.isError:
        return {"ok": False, "error": result.content[0].text if result.content else "tool error"}
    return result.structuredContent or json.loads(result.content[0].text)


def main_pid(app: str) -> int:
    out = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", f"creative-app@{app}.service"],
                         capture_output=True, text=True, check=False).stdout.strip()
    return int(out or 0)


def cpu_ticks(pid: int) -> int:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])  # utime + stime


def has_window(app: str) -> bool:
    res = subprocess.run(["xdotool", "search", "--class", f"ai.storyteller.{app}"], capture_output=True,
                         text=True, env={"DISPLAY": ":0", "PATH": "/usr/bin:/bin"}, check=False)
    return bool(res.stdout.split())


def idle_cpu(app: str) -> float | None:
    pid = main_pid(app)
    if not pid:
        return None
    time.sleep(SETTLE)
    try:
        before = cpu_ticks(pid)
        time.sleep(WINDOW)
        return (cpu_ticks(pid) - before) * 100 / (WINDOW * CLK)
    except (FileNotFoundError, ProcessLookupError):
        return None


async def check_app(session: ClientSession, app: str, was_running: bool) -> dict:
    row = {"app": app, "launch": "-", "window": "-", "inspect": "-", "commands": "-", "screenshot": "-", "cpu": "-", "ok": True}

    def fail(key: str, detail: object) -> None:
        row[key] = "FAIL"
        row["ok"] = False
        row.setdefault("errors", []).append(f"{key}: {str(detail)[:200]}")

    launched = await call(session, "session_launch", app=app)
    if not launched.get("ok"):
        fail("launch", launched)
        return row
    row["launch"] = "ok"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not has_window(app):
        await asyncio.sleep(0.5)
    row["window"] = "ok" if has_window(app) else "none"
    if row["window"] != "ok":
        fail("window", "no X window with class ai.storyteller." + app)

    inspect = await call(session, "app_control", app=app, method="ui.inspect")
    if inspect.get("ok"):
        row["inspect"] = "ok"
    else:
        fail("inspect", inspect)
    # PhotoCraft opens a modal "Switched to CPU rendering" unless the CPU preference is stored.
    notice = (inspect.get("result") or {}).get("gpuFallbackNotice") if inspect.get("ok") else None
    if notice:
        fail("inspect", f"a GPU fallback dialog is open: {notice}")

    listing = await call(session, "app_commands", app=app, limit=3, include_disabled=True)
    if listing.get("ok") and listing.get("commands") and listing["total"] > 0:
        row["commands"] = "ok"
    else:
        fail("commands", listing)

    shot = await call(session, "screenshot", filename=f"apps-{app}.png")
    if shot.get("ok") and shot.get("size_bytes", 0) > 1000:
        row["screenshot"] = "ok"
    else:
        fail("screenshot", shot)

    cpu = idle_cpu(app)
    row["cpu"] = "-" if cpu is None else f"{cpu:.0f}%"

    if not was_running:
        stopped = await call(session, "session_stop", app=app)
        if not stopped.get("ok") or stopped.get("state") == "active":
            fail("launch", f"session_stop: {stopped}")
    return row


async def main() -> int:
    async with streamablehttp_client(URL) as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        status = await call(session, "session_status")
        installed = {n: a for n, a in status.get("apps", {}).items() if a["installed"]}
        names = ARGS or sorted(installed)
        unknown = [n for n in names if n not in installed]
        if unknown:
            print(f"not installed: {', '.join(unknown)}")
            return 2
        rows = []
        for app in names:
            print(f"... {app}", flush=True)
            rows.append(await check_app(session, app, installed[app]["unit"] == "active"))

    cols = ["app", "launch", "window", "inspect", "commands", "screenshot", "cpu"]
    print("\n| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for row in rows:
        print("| " + " | ".join(str(row[c]) for c in cols) + " |")
    for row in rows:
        for err in row.get("errors", []):
            print(f"  {row['app']}: {err}")
    bad = [r["app"] for r in rows if not r["ok"]]
    print(f"\nfailed: {', '.join(bad)}" if bad else "\nall apps passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
