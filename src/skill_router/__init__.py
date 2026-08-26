"""
skill_router — packaging shim for Skill Router.

The canonical implementation lives at ``skill.py`` in the repository root.
This package exists so the project can be installed with ``pip install``
and discovered as ``skill-router`` on the command line.

Do not import from this shim when running from a source checkout — import
``skill`` directly.  The shim is for installed-package use only.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Locate the sibling skill.py (works in editable installs and wheels
# because skill.py is shipped alongside this package).
_THIS = Path(__file__).resolve()
_REPO = _THIS.parent.parent.parent  # src/skill_router/../../.. → repo root
_SKILL_PY = _REPO / "skill.py"

if _SKILL_PY.exists():
    _spec = importlib.util.spec_from_file_location("skill_router._skill", _SKILL_PY)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["skill_router._skill"] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

    # Re-export the public API
    route = _mod.route
    sync = _mod.sync
    validate_all = _mod.validate_all
    bootstrap = _mod.bootstrap
    doctor = _mod.doctor
    get_stats = _mod.get_stats
    VERSION = _mod.VERSION
    main = _mod.main
else:
    raise ImportError(
        "skill_router shim could not find skill.py. "
        "Install the project from the repository root or use 'pip install -e .'"
    )

__all__ = [
    "route", "sync", "validate_all", "bootstrap",
    "doctor", "get_stats", "VERSION", "main",
]
