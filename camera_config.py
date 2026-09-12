"""Compatibility wrapper for retailedge.camera_config."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from retailedge.camera_config import *  # noqa: F401,F403,E402  # type: ignore[reportMissingImports]
