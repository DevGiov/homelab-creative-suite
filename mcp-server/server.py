#!/usr/bin/env python3
"""
Creative Suite MCP Bridge Server for Proxmox Homelab.

Exposes the Creative Suite apps running on the virtual display :0 of CT 144
over Streamable HTTP (/mcp) and SSE (/sse) on port 7900.

Apps are declared in deploy/apps/<app>.env (shared with creative-app@.service).
Running apps are driven through their loopback JSON-lines control channel;
headless operations go through the app's CLI. No call ever goes through a shell.
"""

import base64
import contextlib
import functools
import itertools
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy"))
from appenv import parse_env_file  # shared with deploy/gen-session-config.py

WORKSPACE_DIR = Path(os.environ.get("CREATIVE_WORKSPACE", "/workspace"))
BIN_DIR = Path(os.environ.get("CREATIVE_BIN_DIR", "/opt/creative-suite/bin"))
APPS_DIR = Path(os.environ.get("CREATIVE_APPS_DIR", Path(__file__).resolve().parent.parent / "deploy" / "apps"))
DISPLAY = os.environ.get("DISPLAY", ":0")
CONTROL_TIMEOUT = 65.0  # apps answer within 60s or reply with a timeout error themselves
CLI_TIMEOUT = 60
LAUNCH_TIMEOUT = 15.0


class BridgeError(Exception):
    """A request the bridge refuses or cannot complete; reported to the caller as ok=False."""


# --- App registry --------------------------------------------------------------------------


AUTH_MODES = ("none", "token-file", "control-file")
EXEC_METHODS = ("engine.execute", "ui.command")
PATH_MODES = ("absolute", "workspace-relative")


@dataclass(frozen=True)
class AppSpec:
    name: str
    port: int | None  # None: the app picks a random port and publishes it in `control_file`
    cli_actions: frozenset
    open_method: str
    label: str = ""
    category: str = ""
    auth: str = "none"  # none | token-file (PhotoCraft) | control-file (PdfCraft)
    token_file: Path | None = None
    control_file: Path | None = None
    exec_method: str = "engine.execute"  # how app_command runs an engine command
    path_mode: str = "absolute"  # PhotoCraft only accepts paths relative to its automation roots

    @property
    def unit(self) -> str:
        return f"creative-app@{self.name}.service"

    @property
    def gui_bin(self) -> Path:
        return BIN_DIR / self.name

    @property
    def cli_bin(self) -> Path:
        return BIN_DIR / f"{self.name}-cli"


def choice(env: dict[str, str], key: str, allowed: tuple[str, ...], default: str, where: str) -> str:
    value = env.get(key, default)
    if value not in allowed:
        raise ValueError(f"{where}: {key}={value!r} is not one of {', '.join(allowed)}")
    return value


def spec_from_env(name: str, env: dict[str, str]) -> AppSpec:
    auth = choice(env, "AUTH", AUTH_MODES, "none", name)
    if auth == "token-file" and not env.get("TOKEN_FILE"):
        raise ValueError(f"{name}: AUTH=token-file needs TOKEN_FILE")
    if auth == "control-file" and not env.get("CONTROL_FILE"):
        raise ValueError(f"{name}: AUTH=control-file needs CONTROL_FILE")
    if auth != "control-file" and not env.get("CONTROL_PORT"):
        raise ValueError(f"{name}: CONTROL_PORT is required")
    return AppSpec(
        name=name,
        port=int(env["CONTROL_PORT"]) if env.get("CONTROL_PORT") else None,
        cli_actions=frozenset(env.get("CLI_ACTIONS", "").split()),
        open_method=env.get("OPEN_METHOD", "app.open"),
        label=env.get("LABEL") or name.capitalize(),
        category=env.get("CATEGORY", ""),
        auth=auth,
        token_file=Path(env["TOKEN_FILE"]) if env.get("TOKEN_FILE") else None,
        control_file=Path(env["CONTROL_FILE"]) if env.get("CONTROL_FILE") else None,
        exec_method=choice(env, "EXEC_METHOD", EXEC_METHODS, "engine.execute", name),
        path_mode=choice(env, "PATH_MODE", PATH_MODES, "absolute", name),
    )


def load_apps(apps_dir: Path) -> dict[str, AppSpec]:
    apps: dict[str, AppSpec] = {}
    for env_file in sorted(apps_dir.glob("*.env")):
        spec = spec_from_env(env_file.stem, parse_env_file(env_file.read_text()))
        clash = next((a for a in apps.values() if spec.port is not None and a.port == spec.port), None)
        if clash:
            raise ValueError(f"{spec.name} and {clash.name} share control port {spec.port}")
        apps[spec.name] = spec
    return apps


APPS = load_apps(APPS_DIR)


def get_app(name: str) -> AppSpec:
    try:
        return APPS[name]
    except KeyError:
        raise BridgeError(f"unknown app {name!r}; available: {', '.join(sorted(APPS))}") from None


# --- Workspace path confinement ------------------------------------------------------------


def resolve_workspace_path(path: str) -> Path:
    """Resolve `path` (relative to the workspace, or absolute) and require it to stay inside it."""
    root = WORKSPACE_DIR.resolve()
    target = (root / path).resolve()
    if target != root and root not in target.parents:
        raise BridgeError(f"path {path!r} is outside {WORKSPACE_DIR}")
    return target


def is_path_like(arg: str) -> bool:
    """Absolute, parent-relative, or an existing workspace entry (which may be a symlink out)."""
    if arg.startswith("/") or ".." in arg.split("/"):
        return True
    try:
        return os.path.lexists(WORKSPACE_DIR / arg)
    except (OSError, ValueError):
        return False


def sanitize_cli_args(args: list[str]) -> list[str]:
    """Confine anything that looks like a filesystem path to the workspace; pass the rest through."""
    clean = []
    for arg in args:
        if arg.startswith("~"):
            raise BridgeError(f"home-relative paths are not allowed: {arg!r}")
        clean.append(str(resolve_workspace_path(arg)) if is_path_like(arg) else arg)
    return clean


def path_for_app(app: AppSpec | None, resolved: Path) -> str:
    """Spell a confined path the way `app` wants it (PhotoCraft: relative to the workspace root)."""
    if app is not None and app.path_mode == "workspace-relative":
        return str(resolved.relative_to(WORKSPACE_DIR.resolve()))
    return str(resolved)


def confine_params(params: dict[str, Any] | None, app: AppSpec | None = None) -> dict[str, Any]:
    """Confine a top-level `path` parameter (file.open, file.saveAs, ui.screenshot, ...) to the workspace."""
    params = dict(params or {})
    if isinstance(params.get("path"), str):
        params["path"] = path_for_app(app, resolve_workspace_path(params["path"]))
    return params


# --- Transports ----------------------------------------------------------------------------

_request_ids = itertools.count(1)


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def read_control_file(app: AppSpec) -> tuple[int, str]:
    """(port, token) published by an app started with `--control FILE` (PdfCraft)."""
    try:
        data = json.loads(app.control_file.read_text())
    except FileNotFoundError:
        raise BridgeError(f"{app.name} is not running (no control file {app.control_file}); use session_launch") from None
    except (OSError, ValueError) as e:
        raise BridgeError(f"{app.name}: unusable control file {app.control_file}: {e}") from None
    port, token = (data.get("port"), data.get("token")) if isinstance(data, dict) else (None, None)
    if not isinstance(port, int) or not isinstance(token, str) or not token:
        raise BridgeError(f"{app.name}: control file {app.control_file} lacks a port and a token")
    return port, token


def app_endpoint(app: AppSpec) -> tuple[int, str | None]:
    """(port, token or None) to reach `app`'s control channel."""
    if app.auth == "control-file":
        return read_control_file(app)
    if app.auth == "token-file":
        try:
            token = app.token_file.read_text().strip()
        except FileNotFoundError:
            raise BridgeError(f"{app.name} is not running (no token file {app.token_file}); use session_launch") from None
        except OSError as e:
            raise BridgeError(f"{app.name}: cannot read token file {app.token_file}: {e}") from None
        return app.port, token
    return app.port, None


def app_port(app: AppSpec) -> int | None:
    """The control port, or None when it cannot be known yet (control-file app that is not running)."""
    try:
        return app_endpoint(app)[0]
    except BridgeError:
        return None


def port_is_open(app: AppSpec) -> bool:
    port = app_port(app)
    return port is not None and is_port_open(port)


def normalise_reply(reply: dict[str, Any]) -> dict[str, Any]:
    """One reply shape for every app: {"ok": bool, "result"?: ..., "error"?: str}.

    Most apps answer {"id","ok","result"|"error"}; PdfCraft answers JSON-RPC style, with the error
    as an object and no "ok" field.
    """
    reply = {k: v for k, v in reply.items() if k not in ("id", "jsonrpc")}
    error = reply.get("error")
    if isinstance(error, dict):
        return {"ok": False, "error": str(error.get("message") or json.dumps(error))}
    reply.setdefault("ok", error is None)
    return reply


def control_call(app: AppSpec, method: str, params: dict[str, Any] | None = None,
                 timeout: float = CONTROL_TIMEOUT) -> dict[str, Any]:
    """One request/reply on the app's JSON-lines control channel (see apps/*/src/control_server.rs).

    Apps with a token (PhotoCraft, PdfCraft) must be sent `auth {token}` as the first line of every
    connection, so the handshake and the request share one connection.
    """
    port, token = app_endpoint(app)

    def line(request_id, name, args):
        return json.dumps({"id": request_id, "method": name, "params": args}) + "\n"

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            reader = sock.makefile("r", encoding="utf-8")
            if token is not None:
                sock.sendall(line("auth", "auth", {"token": token}).encode())
                hello = reader.readline()
                if not hello:
                    raise BridgeError(f"{app.name} closed the connection during authentication")
                result = normalise_reply(json.loads(hello))
                if not result["ok"]:
                    raise BridgeError(f"{app.name}: authentication failed: {result.get('error', 'rejected')}")
            sock.sendall(line(next(_request_ids), method, params or {}).encode())
            reply = reader.readline()
    except ConnectionRefusedError:
        raise BridgeError(f"{app.name} is not running (control port {port}); use session_launch") from None
    except TimeoutError:
        raise BridgeError(f"{app.name} did not answer {method!r} within {timeout:.0f}s") from None
    except json.JSONDecodeError as e:
        raise BridgeError(f"{app.name} sent invalid JSON: {e}") from None
    if not reply:
        raise BridgeError(f"{app.name} closed the control connection without replying")
    try:
        return normalise_reply(json.loads(reply))
    except json.JSONDecodeError as e:
        raise BridgeError(f"{app.name} sent invalid JSON: {e}") from None


def run_command(args: list[str], timeout: int = CLI_TIMEOUT, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)


def systemctl(*args: str) -> subprocess.CompletedProcess:
    return run_command(["systemctl", *args], timeout=30)


def unit_state(app: AppSpec) -> str:
    return systemctl("is-active", app.unit).stdout.strip() or "unknown"


def wait_for_port(app: AppSpec, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_is_open(app):
            return True
        time.sleep(0.25)
    return port_is_open(app)


def raise_window(app: AppSpec, timeout: float = 5.0) -> bool:
    """Bring `app`'s window to the front (best effort); True if it has one."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            ids = run_command(["xdotool", "search", "--class", f"ai.storyteller.{app.name}"], timeout=5).stdout.split()
            if ids:
                run_command(["xdotool", "windowactivate", ids[0]], timeout=5)
                return True
        except (OSError, subprocess.TimeoutExpired):
            return False  # no xdotool or no display: launching the app must not fail because of it
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


def display_size() -> str:
    out = run_command(["xdpyinfo", "-display", DISPLAY], timeout=10).stdout
    match = re.search(r"dimensions:\s+(\d+x\d+)", out)
    if not match:
        raise BridgeError(f"cannot read the size of display {DISPLAY}")
    return match.group(1)


def visible_windows() -> list[str]:
    ids = run_command(["xdotool", "search", "--onlyvisible", "--name", "."], timeout=10).stdout.split()
    names = []
    for wid in ids:
        name = run_command(["xdotool", "getwindowname", wid], timeout=5).stdout.strip()
        if name:
            names.append(name)
    return names


def bridged(fn):
    """Turn BridgeError and subprocess timeouts into {"ok": False, "error": ...} tool results."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except BridgeError as e:
            return {"ok": False, "error": str(e)}
        except subprocess.TimeoutExpired as e:
            return {"ok": False, "error": f"command timed out after {e.timeout}s"}

    return wrapper


# --- MCP tools -----------------------------------------------------------------------------

mcp = FastMCP(
    "CreativeSuite",
    instructions=(
        "Central MCP bridge for the Proxmox Homelab Creative Suite (DeckCraft presentations, "
        "WordCraft documents, GridCraft spreadsheets). Apps run on a virtual desktop streamed "
        "to the user; files live under /workspace."
    ),
    # Every tool call is independent, so keep no per-client session: a bridge restart (CT reboot,
    # deploy) must not strand MetaMCP on a session id that no longer exists ("Session not found").
    stateless_http=True,
)
mcp.settings.transport_security.enable_dns_rebinding_protection = False


@mcp.tool()
@bridged
def app_command(app: str, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Run an engine command in a running app (live edit visible on the stream).
    Use app_cli(app, 'commands') to list command ids. Examples:
      - deckcraft: 'slide.new', 'shape.insert' {"preset": "roundRect", "rect": [100,100,400,200], "text": "Hi"}
      - wordcraft: 'text.insert' {"text": "Hello"}, 'format.bold'
      - gridcraft: 'cell.set' {"cell": "B2", "input": "=SUM(A1:A9)"}
      - pdfcraft: a registry command id such as 'view.zoomIn' (params are merged next to the id)
    """
    spec = get_app(app)
    params = confine_params(params, spec)
    if spec.exec_method == "ui.command":
        return control_call(spec, "ui.command", {"id": command, **params})
    return control_call(spec, "engine.execute", {"command": command, "params": params})


@mcp.tool()
@bridged
def app_control(app: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Call a raw control-channel method on a running app, e.g. 'ui.inspect', 'document.inspect',
    'engine.commands', 'ui.screenshot' {"path": "/workspace/screenshots/x.png"}, 'app.save'.
    """
    spec = get_app(app)
    return control_call(spec, method, confine_params(params, spec))


@mcp.tool()
@bridged
def app_cli(app: str, action: str, args: list[str] | None = None) -> dict[str, Any]:
    """
    Run a headless CLI operation (no window). Paths are relative to /workspace and must stay inside it.
    Actions per app:
      - deckcraft: info, render, convert, commands, describe, links, run
      - wordcraft: info, text, inspect, convert, render, run, commands, parity
      - gridcraft: info, convert, eval, cat, run, commands, functions
    Example: app_cli('wordcraft', 'convert', ['docs/in.docx', 'docs/out.pdf'])
    """
    spec = get_app(app)
    if action not in spec.cli_actions:
        raise BridgeError(f"action {action!r} not allowed for {app}; allowed: {', '.join(sorted(spec.cli_actions))}")
    res = run_command([str(spec.cli_bin), action, *sanitize_cli_args(args or [])], cwd=WORKSPACE_DIR)
    return {"ok": res.returncode == 0, "stdout": res.stdout, "stderr": res.stderr, "returncode": res.returncode}


@mcp.tool()
@bridged
def session_launch(app: str, file_path: str | None = None) -> dict[str, Any]:
    """Start an app on the virtual desktop (systemd unit) and optionally open a /workspace file in it."""
    spec = get_app(app)
    target = resolve_workspace_path(file_path) if file_path else None
    if not spec.gui_bin.exists():
        raise BridgeError(f"{app} is not installed on this workstation")
    if not port_is_open(spec):
        res = systemctl("start", spec.unit)
        if res.returncode != 0:
            raise BridgeError(f"cannot start {spec.unit}: {res.stderr.strip()}")
        if not wait_for_port(spec, LAUNCH_TIMEOUT):
            raise BridgeError(f"{app} started but its control channel did not open")
    result: dict[str, Any] = {"ok": True, "app": app, "port": app_port(spec), "raised": raise_window(spec)}
    if target:
        path = path_for_app(spec, target)
        if spec.open_method.startswith("engine:"):
            opened = control_call(spec, "engine.execute",
                                  {"command": spec.open_method.removeprefix("engine:"), "params": {"path": path}})
        else:
            opened = control_call(spec, spec.open_method, {"path": path})
        result.update(ok=bool(opened.get("ok")), opened=opened)
    return result


@mcp.tool()
@bridged
def session_stop(app: str) -> dict[str, Any]:
    """Stop an app on the virtual desktop. Unsaved changes are lost."""
    spec = get_app(app)
    res = systemctl("stop", spec.unit)
    return {"ok": res.returncode == 0, "app": app, "state": unit_state(spec), "stderr": res.stderr.strip()}


@mcp.tool()
@bridged
def session_status() -> dict[str, Any]:
    """Live status of the virtual workstation: per-app unit state and control port, visible windows."""
    apps = {
        name: {
            "installed": spec.gui_bin.exists(),
            "unit": unit_state(spec),
            "label": spec.label,
            "port": app_port(spec),
            "port_open": port_is_open(spec),
        }
        for name, spec in APPS.items()
    }
    return {"ok": True, "virtual_display": DISPLAY, "apps": apps, "visible_windows": visible_windows()}


@mcp.tool()
@bridged
def screenshot(filename: str | None = None, include_base64: bool = False) -> dict[str, Any]:
    """
    Capture the virtual display streamed to the user into /workspace/screenshots/.
    Set include_base64 to also return the PNG for visual inspection.
    """
    shots = WORKSPACE_DIR / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    name = Path(filename).name if filename else f"screen_{int(time.time())}.png"
    if not name.endswith(".png"):
        name += ".png"
    target = shots / name
    size = display_size()
    res = run_command(["ffmpeg", "-loglevel", "error", "-f", "x11grab", "-video_size", size,
                       "-i", DISPLAY, "-frames:v", "1", "-y", str(target)], timeout=30)
    if res.returncode != 0 or not target.exists():
        raise BridgeError(f"capture failed: {res.stderr.strip()}")
    result = {"ok": True, "file_path": str(target), "resolution": size, "size_bytes": target.stat().st_size}
    if include_base64:
        result["base64_data"] = base64.b64encode(target.read_bytes()).decode()
    return result


@mcp.tool()
@bridged
def workspace_files(subpath: str = "") -> dict[str, Any]:
    """List files and directories in the shared NAS /workspace."""
    target = resolve_workspace_path(subpath)
    if not target.is_dir():
        raise BridgeError(f"{subpath!r} is not a directory")
    items = [
        {"name": e.name, "is_dir": e.is_dir(), "size": e.stat().st_size if e.is_file() else 0}
        for e in sorted(os.scandir(target), key=lambda e: e.name)
    ]
    return {"ok": True, "path": str(target), "items": items}


# --- HTTP app ------------------------------------------------------------------------------


async def health(request):
    return JSONResponse({"status": "ok", "service": "creative-suite-mcp", "version": "2.0.0", "apps": sorted(APPS)})


sse_app = mcp.sse_app()
http_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


app = Starlette(routes=[Route("/health", health), *sse_app.routes, *http_app.routes], lifespan=lifespan)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7900"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Starting Creative Suite MCP Bridge on {host}:{port} with apps: {', '.join(sorted(APPS))}")
    uvicorn.run(app, host=host, port=port, log_level="info")
