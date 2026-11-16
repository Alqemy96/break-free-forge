"""The doubles must themselves honour the ports, or they prove nothing."""
import pytest

from bl4forge.core.module import conformance_problems
from bl4forge.core.ports import OpsPort, RulesPort
from tests.doubles import LegacyOps, LegacyRules, build_forge


def test_doubles_conform_to_ports(legacy, config):
    assert conformance_problems(LegacyRules(legacy, config), RulesPort) == []
    assert conformance_problems(LegacyOps(legacy, config), OpsPort) == []


def test_double_describe_returns_typed_info(legacy, config, all_serials):
    ops = LegacyOps(legacy, config)
    info = ops.describe(all_serials[0])
    assert info.serial == all_serials[0] and info.level == 50 and info.manifest_ok
    # elements follow the shared vocabulary, never 'Cryo'/'Impact' capitalised labels
    from bl4forge.core.vocab import ELEMENTS
    seen = {ops.describe(s).element for s in all_serials[:400]}
    assert seen <= set(ELEMENTS) | {None}


def test_build_forge_mixes_real_and_double(legacy, config):
    f = build_forge(config, legacy, doubles=("rules", "ops"), only=["rules", "ops", "codec", "data"])
    assert f.states["codec"].state == "ok" and f.module("rules") is not None
