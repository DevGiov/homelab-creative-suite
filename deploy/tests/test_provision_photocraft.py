import importlib.util
import json
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("prov", DEPLOY / "provision-photocraft.py")
prov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prov)


def test_sets_cpu_rendering_and_keeps_everything_else():
    before = {"performance": {"historyStates": 50, "renderingMode": None, "useGpu": True}, "theme": "pro"}
    after = prov.with_cpu_rendering(before)
    assert after["performance"] == {"historyStates": 50, "renderingMode": "cpu", "useGpu": False, "gpuBackend": "auto"}
    assert after["theme"] == "pro"
    assert before["performance"]["useGpu"] is True  # input not mutated


def test_handles_missing_or_null_performance_section():
    assert prov.with_cpu_rendering({})["performance"] == prov.CPU
    assert prov.with_cpu_rendering({"performance": None})["performance"] == prov.CPU


def test_provision_creates_updates_and_is_idempotent(tmp_path):
    path = tmp_path / "cfg" / "preferences.json"
    assert prov.provision(path) is True
    assert json.loads(path.read_text()) == {"performance": prov.CPU}
    assert prov.provision(path) is False
    path.write_text(json.dumps({"performance": {"useGpu": True}, "x": 1}))
    assert prov.provision(path) is True
    assert json.loads(path.read_text())["x"] == 1


def test_refuses_a_non_object_file(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text("[1, 2]")
    with pytest.raises(SystemExit):
        prov.provision(path)
    assert path.read_text() == "[1, 2]"
