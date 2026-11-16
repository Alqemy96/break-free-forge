"""bl4forge - a local-first Borderlands 4 loadout forge built as a mesh of small modules.

Every capability lives in one module ("cell") that declares its purpose, what it needs from its
neighbours, and which port (interface) it implements. See docs/ARCHITECTURE.md.


DISCLOSURE (what this code does)
  Reads: nothing from disk. Writes: nothing. Network: none. Risk: none (pure computation on values passed in). Importing the package does no work.
"""

__version__ = "0.1.0.dev0"
