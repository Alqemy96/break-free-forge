"""Shared by the save tests: a throwaway-key Forge and a small save built around REAL serials."""
from __future__ import annotations

from dataclasses import replace

from bl4forge.core.forge import Forge

TEST_KEY = bytes(range(32))
TEST_PC_BASE = bytes(range(100, 132))
STEAM_ID = "76561198000000000"

_TEMPLATE = (
    "state: \n"
    "  char_name: Hunter\n"
    "  class: Char_ExoSoldier\n"
    "  experience: \n"
    "  - type: character\n"
    "    level: 22\n"
    "    points: 355313\n"
    "  inventory: \n"
    "    items: \n"
    "      backpack: \n"
    "        slot_0: \n"
    "          serial: '{0}'\n"
    "          state_flags: 1\n"
    "        slot_1: \n"
    "          serial: '{1}'\n"
    "    equipped_inventory: \n"
    "      equipped: \n"
    "        slot_3: \n"
    "        - serial: '{2}'\n"
    "          flags: 1\n"
    "  currencies: \n"
    "    cash: 1000163543\n"
    "    eridium: 1000001124\n"
    "  lostloot: \n"
    "    items: \n"
    "    - serial: '{3}'\n"
    "      in_machine: true\n"
    "    slots: 6\n"
    "stats: \n"
    "  getcash: 0\n"
)


def real_save_yaml(serials) -> str:
    """A save with four real serials: backpack/slot_0, backpack/slot_1, equipped/slot_3, lostloot/0."""
    return _TEMPLATE.format(*serials[:4])


def save_forge(config, only=("save", "ops")) -> Forge:
    """A Forge whose save cell has the throwaway keys (never a game key)."""
    return Forge.build(replace(config, save_ps5_key=TEST_KEY, save_pc_base_key=TEST_PC_BASE), only=list(only))
