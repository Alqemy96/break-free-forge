"""Names the tests search for, chosen by which dataset is active.

With no data of your own the program uses data/synthetic (fictional: "SYNTHETIC - not game data"). Tests
that search the catalog by item name take the name from here, so the same test runs against either dataset.
Everything in the SYNTHETIC column is invented; the REAL column are community item names used only when you
point the program at your own data (BL4FORGE_DATA).
"""
from pathlib import Path
from types import SimpleNamespace

from bl4forge.core.config import Config

ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC = Config.default(root=ROOT).is_synthetic

import json

_cfg = Config.default(root=ROOT)


def _rows():
    if not SYNTHETIC:
        return 9875                    # the community database the maintainer tested against
    with open(_cfg.serial_db_path, encoding="utf-8") as fh:
        return len(json.load(fh))


D = SimpleNamespace(
    CATALOG_ROWS=_rows(),
    synthetic=SYNTHETIC,
    SHOTGUN_Q="open vault" if SYNTHETIC else "anarchy",            # a cryo shotgun
    SHOTGUN_NAME="Open Vault" if SYNTHETIC else "Anarchy",
    GEAR_Q="cold storage" if SYNTHETIC else "super soldier",       # a gear item whose label says cryo
    WOMBO_Q="clear sightline" if SYNTHETIC else "wombo combo",
    PLASMA_Q="source code" if SYNTHETIC else "plasma coil",
    MFR="open vault" if SYNTHETIC else "maliwan",                  # a manufacturer substring
    AR_MFR="breakfree" if SYNTHETIC else "vladof",
)


def rules_known():
    """Known-answer serials and refs for the rules tests: the shipped synthetic set, or the real constants."""
    if not SYNTHETIC:
        from bl4forge.modules.rules import _known
        return _known
    with open(_cfg.manifest_dir / "known_answers.json", encoding="utf-8") as fh:
        r = json.load(fh)["rules"]
    return SimpleNamespace(
        BASE_SERIAL=r["base_serial"], STORY_PACK_SERIAL=r["story_serial"], STORY_PACK_REF=tuple(r["story_ref"]),
        STORY_PACK=r["story_pack"], BOUNTY_SERIAL=r["bounty_serial"], BOUNTY_REF=tuple(r["bounty_ref"]),
        BOUNTY_PACK=r["bounty_pack"], TWO_COMPS_SERIAL=r["two_comps_serial"],
        PEARL_TWO_COMPS_SERIAL=r["pearl_two_comps_serial"], KIT_SERIAL=r["kit_serial"])
