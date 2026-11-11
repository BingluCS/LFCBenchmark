#!/usr/bin/env python3
"""Build a publishable site data directory from audited repository inputs."""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from export_leaderboard import export

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path) -> None:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="opensdc-site-", dir=output.parent) as temporary:
        stage = Path(temporary) / "data"
        shutil.copytree(ROOT / "docs/data", stage)
        export(ROOT / "docs/data/quality", stage / "leaderboard.json")
        stage.rename(output)
    print(f"Published data prepared at {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new site data directory")
    build(parser.parse_args().output)
