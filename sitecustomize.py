from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE_NAME = "futures_seat_tracker"
PACKAGE_DIR = Path(__file__).resolve().parent

if PACKAGE_NAME not in sys.modules:
    module = types.ModuleType(PACKAGE_NAME)
    module.__path__ = [str(PACKAGE_DIR)]
    module.__file__ = str(PACKAGE_DIR / "__init__.py")
    sys.modules[PACKAGE_NAME] = module
