"""Ports: the contract each module implements. THE FIXED POINT OF THE ARCHITECTURE.

A module may change anything about how it works inside, but not these signatures. If a port
must change, change it here on purpose, update every consumer, and re-run the doctor; never let
two modules quietly disagree. Each Protocol docstring states the module's PURPOSE, then its
INVARIANTS (rules that conformance tests enforce).

Dependency graph (arrows = "requires"):

    codec      <- (nothing)
    data       <- (nothing)
    render     <- (nothing)
    save       <- (nothing)
    lootpak    <- (nothing)
    rules      <- codec, data
    ops        <- codec, data, rules
    catalog    <- codec, data, rules, ops
    builder    <- catalog, ops
    cli        <- everything
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable

from .types import (
    Blocks, CatalogEntry, ItemInfo, Loadout, LoadoutItem, LoadoutRequest, PartRef,
    SaveItem, SearchQuery, SearchResult,
)


@runtime_checkable
class CodecPort(Protocol):
    """PURPOSE: turn '@U...' serial strings into bitstream blocks and back, bit-exactly.

    INVARIANTS
    - encode(decode(s)) == s for every valid serial (byte-identical round trip).
    - Pure functions. No manifest, no file access, no module-level mutable state.
    - Never mutates its inputs; transforms return new values.
    - Failures raise SerialError (never bare ValueError/IndexError).
    """

    def decode(self, serial: str) -> Blocks: ...
    def encode(self, blocks: Blocks) -> str: ...
    def parts_string(self, blocks: Blocks) -> str: ...
    def from_string(self, text: str) -> Blocks: ...
    def get_level(self, blocks: Blocks) -> Optional[int]: ...
    def get_category_id(self, blocks: Blocks) -> Optional[int]:
        """The item's category id (the legacy 'manufacturer index')."""
    def relevel(self, serial: str, level: int) -> str:
        """Same item, new level. Raises SerialError if the level cannot be set."""
    def int_at(self, blocks: Blocks, position: int) -> Optional[int]:
        """Value of the `position`-th plain integer block (used for the seed), else None."""
    def with_int_at(self, blocks: Blocks, position: int, value: int) -> Blocks: ...


@runtime_checkable
class DataPort(Protocol):
    """PURPOSE: the game's own tables (manifest) as read-only lookups. Knows nothing about serials.

    INVARIANTS
    - Read-only. Lazy-loads and caches per instance (no module-level globals).
    - Missing data never raises from lookups: `available()` is False and lookups return empties.
      Only `require()` raises (DataMissing).
    - `rarity` and `pack` come from part_meta.json's explicit fields; NEVER parse them out of a part
      name (14 of 20 pearlescents are named comp_05_legendary_*).
    """

    def available(self) -> bool: ...
    def require(self) -> None: ...
    def manifest_version(self) -> str: ...
    def category_names(self) -> Mapping[int, str]: ...
    def part_table(self, category_id: int) -> Mapping[int, str]: ...
    def item_names(self) -> Mapping[str, str]: ...
    def part_meta(self, category_id: int, index: int) -> Mapping[str, object]:
        """{} or {'rarity':..., 'name':..., 'pack':...} for one part ref."""
    def drops(self) -> Mapping[str, object]: ...
    def drops_by_item(self) -> Mapping[str, List[dict]]: ...
    def is_weapon_category(self, category_id: Optional[int]) -> bool: ...
    def prettify_part(self, raw: str) -> str: ...
    def prettify_legendary(self, raw_suffix: str) -> Optional[str]: ...


@runtime_checkable
class RulesPort(Protocol):
    """PURPOSE: decide what the player may legitimately hold, and whether a serial is well formed.

    INVARIANTS
    - Ownership is judged per PART, not per item name (a DLC barrel on a base-game gun is caught).
    - The owned-pack set comes from config; `story_pack_1` is not owned by default.
    - `validate` is structural only: parts resolve, exactly one rarity component (pearlescents may
      carry two), at most one element, sane level. It must never claim in-game validity.
    """

    def owned_packs(self) -> FrozenSet[str]: ...
    def pack_label(self, pack: str) -> str: ...
    def pack_of(self, category_id: Optional[int], index: int) -> str: ...
    def is_owned(self, category_id: Optional[int], index: int) -> bool: ...
    def serial_ownership(self, serial: str) -> Tuple[bool, Optional[str]]:
        """(owned, first_missing_pack_or_None) for every part in the serial."""
    def validate(self, serial: str) -> List[str]:
        """List of human-readable problems; empty list means structurally fine."""


@runtime_checkable
class OpsPort(Protocol):
    """PURPOSE: understand and modify ONE serial: identify it, change element/seed, swap parts, diff.

    INVARIANTS
    - Trust the bitstream, never a database label.
    - describe() never raises on missing manifest data; it reports `manifest_ok=False` + warnings.
    - set_element round-trips byte-identically; 'impact' strips the element part.
    - swap_parts refuses cross-category swaps unless allow_cross=True.
    - Every transform returns a new serial string; the input is untouched.
    """

    def describe(self, serial: str) -> ItemInfo: ...
    def rarity_estimate(self, info: ItemInfo) -> Mapping[str, object]: ...
    def format_odds(self, estimate: Mapping[str, object]) -> str: ...
    def part_list(self, serial: str) -> List[PartRef]: ...
    def set_element(self, serial: str, element: Optional[str]) -> str: ...
    def get_seed(self, serial: str) -> Optional[int]: ...
    def set_seed(self, serial: str, seed: int) -> str: ...
    def relevel(self, serial: str, level: int) -> str:
        """Same item at a new level (delegates the bit work to codec). Raises SerialError on failure;
        never returns the original serial as if it had worked."""
    def swap_parts(self, base: str, source: str, positions: Sequence[int],
                   allow_cross: bool = False) -> str: ...
    def diff(self, serial_a: str, serial_b: str) -> List[dict]: ...


@runtime_checkable
class CatalogPort(Protocol):
    """PURPOSE: the community serial database as a searchable, verified catalog.

    INVARIANTS
    - Catalog labels are hints. When `verify_element` is on, every candidate is re-checked against the
      decoded serial and mismatches are DROPPED (and counted in dropped_element_mismatch).
    - Unowned items are filtered unless include_unowned, and the filter is REPORTED in
      hidden_by_pack - results are never silently truncated.
    - Type aliases (ar, sg, ps, repkit, grenade, rifle, ...) are resolved here; vocab handles elements.
    - Search is deterministic for a given query and database.
    """

    def count(self) -> int: ...
    def search(self, query: SearchQuery) -> SearchResult: ...
    def stats(self) -> Mapping[str, Mapping[str, int]]:
        """{'by_type': {...}, 'by_weapon_type': {...}, 'by_rarity': {...}}"""
    def find_by_serial(self, serial: str) -> Optional[CatalogEntry]: ...


@runtime_checkable
class BuilderPort(Protocol):
    """PURPOSE: turn loadout requests into a verified Loadout (search, re-level, enrich, group).

    INVARIANTS
    - Every item is re-leveled to the requested level; a level that doesn't take is a WARNING on
      the item, never silently ignored.
    - Misses go in Loadout.unmatched, never raised and never dropped silently.
    - Decoded facts (rarity/element/name) override catalog hints, with a warning when they disagree.
    """

    def enrich(self, entry: CatalogEntry, level: Optional[int] = None) -> LoadoutItem: ...
    def build(self, requests: Sequence[LoadoutRequest], level: Optional[int] = None,
              title: str = "Break Free Loadout") -> Loadout: ...


@runtime_checkable
class RenderPort(Protocol):
    """PURPOSE: present a Loadout. Pure formatting - no lookups, no file access except `write`.

    INVARIANTS
    - html() output is self-contained (inline CSS/JS) and escapes every data field. The ONLY markup
      allowed through is <em>...</em> inside `note` (legacy behaviour); anything else is escaped.
    - text() is one serial per line under group headings, safe to paste anywhere.
    """

    def html(self, loadout: Loadout) -> str: ...
    def text(self, loadout: Loadout) -> str: ...
    def write(self, loadout: Loadout, html_path: str, text_path: Optional[str] = None) -> Tuple[str, str]: ...


@runtime_checkable
class SavePort(Protocol):
    """PURPOSE: open and re-wrap Borderlands 4 save files (PS5 and PC) and patch their YAML as TEXT.

    INVARIANTS
    - decrypt -> encrypt -> decrypt gives identical YAML (the compressed bytes may differ).
    - Keys come from config ([save]); a missing key raises SaveKeyMissing, never a wrong-key guess.
    - Editing is line-level: every patch changes exactly the value on one existing line and
      nothing else (no re-serialisation, line endings and spacing kept). Pure text in, text out.
    - Files are only ever COPIED: write_copy refuses the source path, records the source sha256 and
      proves the source is unchanged. Failures raise SaveError.
    - `ref` addresses: "backpack/slot_N", "equipped/slot_N", "lostloot/<index>".
    """

    def decrypt_ps5(self, data: bytes) -> str: ...
    def encrypt_ps5(self, yaml_text: str) -> bytes: ...
    def decrypt_pc(self, data: bytes, steam_id: str) -> str: ...
    def encrypt_pc(self, yaml_text: str, steam_id: str) -> bytes: ...
    def summary(self, yaml_text: str) -> Dict[str, object]:
        """character name/class/difficulty, level, xp points, currencies; absent facts are None."""
    def list_items(self, yaml_text: str) -> List[SaveItem]: ...
    def set_currency(self, yaml_text: str, name: str, value: int) -> str: ...
    def set_shared_point_pool(self, yaml_text: str, name: str, value: int) -> str:
        """Profile saves: set domains>local>progression_shared>point_pools>name (0..2**31-1), one line."""
    def shared_pool_report(self, yaml_text: str, name: str = "echotokenprogresspoints") -> Optional[Dict[str, object]]:
        """Read-only {name, value, spent (sdu_upgrades points_spent), available, pools}; None if absent."""
    def set_progress(self, yaml_text: str, level: Optional[int] = None,
                     points: Optional[int] = None) -> str: ...
    def set_serial(self, yaml_text: str, ref: str, serial: str) -> str: ...
    def changed_lines(self, before: str, after: str) -> List[Tuple[int, str, str]]:
        """(1-based line number, old line, new line) for every line that differs."""
    def sha256(self, data: bytes) -> str: ...
    def write_copy(self, source_path: str, dest_path: str, data: bytes,
                   overwrite: bool = False) -> Dict[str, object]: ...


@runtime_checkable
class LootPakPort(Protocol):
    """PURPOSE: turn one TOML config into a PS5 loot pak (value retargets of `gbx_ue_data_table0`), with proof.

    INVARIANTS
    - v1 edits VALUES only (`set_leaf`): no struct or leaf inserts, no new pool strings. A value that is not
      already in the string pool is refused, never invented.
    - Leaves are located by structure (row name windows + a sentinel probe decoded by `bl4 ncs show`), never by
      hard-coded bit positions. Rows and fields are named in the config.
    - The plan is produced (and printable) before anything is written. The built pak is extracted and decoded
      again; its diff against the base decode must be exactly the planned lines or the build FAILS.
    - Nothing is written into the base's folder, an existing out folder, or under a folder named backups.
    - No console or network code. Tools run as subprocesses behind a replaceable adapter. Failures raise
      LootPakError (config problems raise ConfigError).
    """

    def load_config(self, path: str) -> object: ...
    def plan(self, config: object) -> object: ...
    def build(self, config: object, out_dir: str) -> object: ...


# name -> port, used by the registry and the doctor to check conformance.
PORTS: Dict[str, type] = {
    "codec": CodecPort,
    "data": DataPort,
    "rules": RulesPort,
    "ops": OpsPort,
    "catalog": CatalogPort,
    "builder": BuilderPort,
    "render": RenderPort,
    "save": SavePort,
    "lootpak": LootPakPort,
}
