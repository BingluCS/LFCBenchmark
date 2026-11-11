"""Smoke-check native command dispatch without building or running codecs."""
import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("command", ["native-build", "native-suite", "native-suite-plot"])
def test_native_subcommands_route_to_source_scripts(command):
    result = subprocess.run([sys.executable,"-m","lfcbench",command,"--help"],
                            text=True,capture_output=True,check=True)
    assert "usage:" in result.stdout


def test_official_submodule_links_match_source_lock():
    root = Path(__file__).resolve().parents[1]
    probe = subprocess.run(["git","rev-parse","--is-inside-work-tree"],cwd=root,text=True,capture_output=True)
    if probe.returncode:
        pytest.skip("source directory has no Git metadata")
    lock = json.loads((root / "sources.lock.json").read_text())
    assert set(lock) == {"Falcons","PFPL","SPERR","SZ3","ZFP"}
    for source in lock.values():
        path = source["path"]
        entry = subprocess.run(["git","ls-files","--stage","--",path],cwd=root,
                               text=True,capture_output=True,check=True).stdout.strip()
        metadata,sep,indexed_path = entry.partition("\t")
        assert sep and indexed_path == path
        mode,revision,stage = metadata.split()
        assert mode == "160000" and stage == "0" and revision == source["commit"]
        url = subprocess.run(["git","config","-f",".gitmodules","--get",f"submodule.{path}.url"],
                             cwd=root,text=True,capture_output=True,check=True).stdout.strip()
        assert url == source["url"]
