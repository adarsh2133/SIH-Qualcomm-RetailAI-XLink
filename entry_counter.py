"""Compatibility entrypoint for retailedge.entry_counter."""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
runpy.run_module("retailedge.entry_counter", run_name="__main__")
