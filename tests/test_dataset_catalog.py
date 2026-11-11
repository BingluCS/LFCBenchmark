"""Validate selected-dataset inventory."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inventory_can_select_one_available_dataset(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    script = load_script("inventory_sdrbench")
    monkeypatch.setattr(script, "SHAPES", {"NYX": [2, 2, 2]})
    directory = tmp_path / "NYX"
    directory.mkdir()
    np.arange(8, dtype="<f4").tofile(directory / "sample.f32")
    output = tmp_path / "inventory.json"
    monkeypatch.setattr(sys, "argv", ["inventory_sdrbench", "--data-root", str(tmp_path),
                                      "--datasets", "NYX", "--output", str(output)])
    script.main()
    result = json.loads(output.read_text())
    assert list(result) == ["NYX"] and result["NYX"][0]["elements"] == 8
