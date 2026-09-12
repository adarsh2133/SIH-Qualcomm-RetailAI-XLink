"""Compatibility entrypoint; canonical launcher lives in deploy/."""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "deploy" / "launch_retailedge.py"), run_name="__main__")
