#!/usr/bin/env python3
"""
Creative Suite MCP Bridge Server for Proxmox Homelab.
Exposes Creative Suite applications (DeckCraft, WordCraft, etc.)
over Streamable HTTP (/mcp) and SSE (/sse) on port 7900.
"""

import os
import sys
import json
import time
import base64
import socket
import contextlib
import subprocess
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

WORKSPACE_DIR = "/workspace"
BIN_DIR = "/opt/creative-suite/bin"
SCREENSHOTS_DIR = os.path.join(WORKSPACE_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

mcp = FastMCP("CreativeSuite", instructions="Central MCP bridge for Proxmox Homelab Creative Suite. Manage presentations, documents, visual assets, and virtual desktop co-authoring.")
mcp.settings.transport_security.enable_dns_rebinding_protection = False

def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

@mcp.tool()
def deckcraft_app_command(command: str, params: Optional[Dict[str, Any]] = None, auto_launch: bool = True) -> Dict[str, Any]:
    """
    Execute a live command on the active DeckCraft presentation app running on the virtual desktop.
    Examples of commands:
      - 'slide.new': create a new slide
      - 'slide.inspect': inspect shapes and content on current slide
      - 'shape.insert': insert shape e.g. {"preset": "roundRect", "rect": [100, 100, 400, 200], "text": "Hello"}
      - 'slide.go': jump to slide index e.g. {"index": 0}
      - 'edit.undo': undo last edit
      - 'edit.redo': redo last edit
      - 'file.save': save presentation
    """
    cli_bin = os.path.join(BIN_DIR, "deckcraft-cli")
    gui_bin = os.path.join(BIN_DIR, "deckcraft")

    if not is_port_open(7979):
        if auto_launch:
            subprocess.Popen("DISPLAY=:0 " + gui_bin + " --control 7979 --sample &", shell=True)
            time.sleep(2)
        else:
            return {"ok": False, "error": "DeckCraft is not running on port 7979 and auto_launch=False"}

    args = [cli_bin, "app", "--port", "7979", command]
    if params:
        args.append(json.dumps(params))

    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            return {"ok": False, "error": res.stderr.strip() or res.stdout.strip(), "returncode": res.returncode}
        try:
            return {"ok": True, "result": json.loads(res.stdout)}
        except Exception:
            return {"ok": True, "result": res.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mcp.tool()
def deckcraft_cli(action: str, file_path: Optional[str] = None, extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run headless DeckCraft operations without needing a window:
    action options: 'info', 'render', 'convert', 'commands', 'describe'
    """
    cli_bin = os.path.join(BIN_DIR, "deckcraft-cli")
    cmd = [cli_bin, action]
    if file_path:
        cmd.append(file_path)
    if extra_args:
        cmd.extend(extra_args)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "ok": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mcp.tool()
def wordcraft_cli(action: str, file_path: Optional[str] = None, extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run headless WordCraft document operations:
    action options: 'info', 'text', 'inspect', 'convert', 'render', 'commands'
    """
    cli_bin = os.path.join(BIN_DIR, "wordcraft-cli")
    cmd = [cli_bin, action]
    if file_path:
        cmd.append(file_path)
    if extra_args:
        cmd.extend(extra_args)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "ok": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mcp.tool()
def creative_session_launch(app: str = "deckcraft", file_path: Optional[str] = None, sample: bool = True) -> Dict[str, Any]:
    """
    Launch or focus a Creative Suite GUI app on the virtual display :0.
    Available apps: 'deckcraft'
    """
    if app == "deckcraft":
        port = 7979
        if is_port_open(port):
            return {"ok": True, "message": f"DeckCraft is already running and listening on port {port}"}
        gui_bin = os.path.join(BIN_DIR, "deckcraft")
        cmd_str = f"DISPLAY=:0 {gui_bin} --control {port}"
        if sample:
            cmd_str += " --sample"
        if file_path:
            cmd_str += f" '{file_path}'"
        cmd_str += " &"
        subprocess.Popen(cmd_str, shell=True)
        time.sleep(2)
        return {"ok": is_port_open(port), "port": port, "app": app}
    return {"ok": False, "error": f"Unsupported app {app}"}

@mcp.tool()
def creative_session_status() -> Dict[str, Any]:
    """
    Check the live status of the virtual workstation:
    returns running apps, open IPC ports, and active X11 windows.
    """
    ports_status = {
        "deckcraft_7979": is_port_open(7979),
        "wordcraft_7981": is_port_open(7981),
        "photocraft_7878": is_port_open(7878),
    }
    try:
        x_windows = subprocess.run(
            "DISPLAY=:0 xdotool search --onlyvisible --class '.*' 2>/dev/null | while read id; do echo \"$id: $(DISPLAY=:0 xdotool getwindowname $id 2>/dev/null)\"; done",
            shell=True, capture_output=True, text=True
        ).stdout.strip().splitlines()
    except Exception:
        x_windows = []

    return {
        "ok": True,
        "virtual_display": ":0",
        "ipc_ports": ports_status,
        "visible_windows": x_windows
    }

@mcp.tool()
def creative_screenshot(filename: Optional[str] = None, include_base64: bool = False) -> Dict[str, Any]:
    """
    Capture a screenshot of the virtual workstation display :0 streamed to the user.
    Saves to /workspace/screenshots/ and optionally returns base64 PNG data for visual inspection.
    """
    if not filename:
        filename = f"screen_{int(time.time())}.png"
    if not filename.endswith(".png"):
        filename += ".png"
    filepath = os.path.join(SCREENSHOTS_DIR, filename)

    cmd = ["ffmpeg", "-f", "x11grab", "-video_size", "1920x1080", "-i", ":0", "-vframes", "1", "-y", filepath]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(filepath):
        return {"ok": False, "error": res.stderr}

    result = {
        "ok": True,
        "file_path": filepath,
        "resolution": "1920x1080",
        "size_bytes": os.path.getsize(filepath)
    }

    if include_base64:
        with open(filepath, "rb") as f:
            result["base64_data"] = base64.b64encode(f.read()).decode("utf-8")

    return result

@mcp.tool()
def creative_workspace_files(subpath: str = "") -> Dict[str, Any]:
    """
    List files and directories in the shared NAS /workspace.
    """
    target = os.path.join(WORKSPACE_DIR, subpath.lstrip("/"))
    if not os.path.exists(target):
        return {"ok": False, "error": "Path does not exist"}

    items = []
    for entry in os.scandir(target):
        items.append({
            "name": entry.name,
            "is_dir": entry.is_dir(),
            "size": entry.stat().st_size if entry.is_file() else 0
        })
    return {"ok": True, "path": target, "items": items}

async def health(request):
    return JSONResponse({"status": "ok", "service": "creative-suite-mcp", "version": "1.0.0"})

sse_app = mcp.sse_app()
http_app = mcp.streamable_http_app()

@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield

routes = [
    Route("/health", health),
    *sse_app.routes,
    *http_app.routes,
]
app = Starlette(routes=routes, lifespan=lifespan)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7900))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Starting Creative Suite MCP Bridge on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
