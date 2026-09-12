"""Compatibility entrypoint for retailedge.metrics_api."""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
runpy.run_module("retailedge.metrics_api", run_name="__main__")
