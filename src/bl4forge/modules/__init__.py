"""Every module ("cell") lives in its own package here and exposes `MODULE`, its Module subclass.

DISCLOSURE (what this code does)
  Reads: nothing. Writes: nothing. Network: none. Risk: none. It imports only the fixed list of module names below, never a name taken from user input.
"""
from __future__ import annotations

import importlib

from ..core.registry import Registry

# Order is documentation only; the registry derives birth order from each module's `requires`.
MODULE_NAMES = ("codec", "data", "render", "rules", "ops", "catalog", "builder", "save", "lootpak")


def default_registry() -> Registry:
    reg = Registry()
    for name in MODULE_NAMES:
        reg.register(importlib.import_module("%s.%s" % (__name__, name)).MODULE)
    return reg
