"""Reader for deploy/apps/<app>.env, shared by the MCP bridge and the session generator.

The files use the KEY=VALUE subset of systemd EnvironmentFile syntax (comments, optional quotes).
Standard library only: the generator runs under the system python3, which has no `mcp` package.
"""

import shlex
from pathlib import Path

CATEGORY_ORDER = ("Documenti", "Grafica", "Audio e video")


def parse_env_file(text: str) -> dict[str, str]:
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"invalid line: {raw!r}")
        values[key.strip()] = " ".join(shlex.split(value))
    return values


def load_envs(apps_dir: Path) -> dict[str, dict[str, str]]:
    """{app name: parsed env} for every *.env in `apps_dir`, sorted by name."""
    return {f.stem: parse_env_file(f.read_text()) for f in sorted(apps_dir.glob("*.env"))}


def sort_key(env: dict[str, str], name: str) -> tuple[int, str, str]:
    """Order apps by category (documents, graphics, audio/video, then others), then label."""
    category = env.get("CATEGORY", "")
    rank = CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)
    return rank, category, env.get("LABEL", name).lower()
