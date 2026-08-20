"""Load the pure package modules without importing Home Assistant."""

from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE = "custom_components.smart_energy_scheduler"
module = types.ModuleType(PACKAGE)
module.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "smart_energy_scheduler")]
sys.modules.setdefault(PACKAGE, module)
