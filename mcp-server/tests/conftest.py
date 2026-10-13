import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A temporary /workspace with a file inside and a sibling directory outside it."""
    ws = tmp_path / "workspace"
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "a.docx").write_text("x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    monkeypatch.setattr(server, "WORKSPACE_DIR", ws)
    return ws
