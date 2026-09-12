"""Compatibility entrypoint for retailedge.health_monitor."""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
runpy.run_module("retailedge.health_monitor", run_name="__main__")
