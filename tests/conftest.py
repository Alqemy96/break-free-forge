"""Shared fixtures.

The public tree ships NO game data and NO legacy oracle. Tests that need the serial database
(data/bl4-serial-matches.json), the extracted manifest (data/manifest/) or the legacy parity oracle
are SKIPPED cleanly when those are absent. Supply your own data (see docs/runbooks/DEVELOPER.md) to
run them.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LEGACY_SCRIPTS = ROOT / "legacy" / "skills" / "bl4-loadout" / "scripts"


def _have_data(config) -> bool:
    return config.serial_db_path.is_file() and config.manifest_dir.is_dir()


@pytest.fixture(scope="session")
def config():
    from bl4forge.core.config import Config
    return Config.default(root=ROOT)


@pytest.fixture(scope="session")
def forge(config):
    if not _have_data(config):
        pytest.skip("needs user-supplied game data (data/bl4-serial-matches.json and data/manifest/)")
    from bl4forge.core.forge import Forge
    return Forge.build(config)


@pytest.fixture(scope="session")
def legacy():
    """The legacy modules, namespaced: legacy.codec / legacy.partsdb / legacy.forge."""
    if not LEGACY_SCRIPTS.is_dir():
        pytest.skip("needs the legacy parity oracle (not part of the public tree)")
    sys.path.insert(0, str(LEGACY_SCRIPTS))
    try:
        import bl4codec, partsdb, forge as legacy_forge  # noqa: E401
    finally:
        sys.path.remove(str(LEGACY_SCRIPTS))

    class NS:
        pass
    ns = NS()
    ns.codec, ns.partsdb, ns.forge = bl4codec, partsdb, legacy_forge
    return ns


@pytest.fixture(scope="session")
def all_serials(legacy):
    """Every cleaned serial in the community database (9,875)."""
    return [e["serial"] for e in legacy.forge.load_db()]


# Tests that read the real (user-supplied) game data through paths that do not use the `forge` fixture.
_NEEDS_REAL_DATA = {
    "test_search_reports_hidden_packs_and_labels", "test_concurrent_requests_match_serial_results",
    "test_manifest_version_real_data", "test_is_weapon_category_keeps_legacy_substring_quirk",
    "test_frozen_copies_are_plain_and_mutable", "test_returned_mappings_are_read_only",
    "test_require_passes_when_present", "test_rarity_and_pack_from_part_meta_real_pearl",
    "test_prettify_prefix_is_a_label_not_a_rarity_source", "test_per_instance_cache_two_data_dirs_do_not_interfere",
    "test_health_ok_on_real_data", "test_forge_starts_data_ok", "test_unowned_content_is_hidden_and_reported_for_real",
    "test_search_hidden_by_pack_and_include_unowned", "test_identify_reports_unowned_content",
    "test_every_pearl_is_reported_as_pearl_whatever_its_name",
}


def pytest_collection_modifyitems(config, items):
    from bl4forge.core.config import Config
    cfg = Config.default(root=ROOT)
    if _have_data(cfg):
        return
    skip = pytest.mark.skip(reason="needs user-supplied game data (see docs/runbooks/DEVELOPER.md)")
    for item in items:
        if item.originalname in _NEEDS_REAL_DATA or item.name in _NEEDS_REAL_DATA:
            item.add_marker(skip)
