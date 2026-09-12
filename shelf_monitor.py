"""Compatibility entrypoint for retailedge.shelf_monitor."""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
runpy.run_module("retailedge.shelf_monitor", run_name="__main__")
