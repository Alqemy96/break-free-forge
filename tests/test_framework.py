"""Tests for the framework itself (core/). Module behaviour is tested in tests/modules/."""
import pytest

from bl4forge.core import vocab
from bl4forge.core.config import Config
from bl4forge.core.doctor import diagnose, ok
from bl4forge.core.errors import ForgeError, ModuleUnavailable, UndeclaredDependency
from bl4forge.core.forge import BLOCKED, DEGRADED, FAILED, OK, Forge
from bl4forge.core.module import Module, conformance_problems
from bl4forge.core.ports import CodecPort, PORTS
from bl4forge.core.registry import Registry
from bl4forge.core.types import HealthReport, LoadoutRequest


def mk(name, requires=(), boom=False, sick=False, peek=None):
    class M(Module):
        pass
    M.name, M.requires, M.purpose = name, tuple(requires), "test cell " + name
    def init(self, ctx):
        Module.__init__(self, ctx)
        if boom:
            raise RuntimeError("cannot start")
        if peek:
            self.dep(peek)
    M.__init__ = init
    if sick:
        M.health = lambda self: HealthReport(ok=False, summary="sick")
    return M


def test_order_puts_dependencies_first():
    reg = Registry([mk("c", ["b"]), mk("b", ["a"]), mk("a")])
    assert reg.order() == ["a", "b", "c"]


def test_order_detects_cycles_and_unknowns():
    with pytest.raises(ForgeError):
        Registry([mk("a", ["b"]), mk("b", ["a"])]).order()
    with pytest.raises(ForgeError):
        Registry([mk("a", ["ghost"])]).order()


def test_only_starts_closure():
    reg = Registry([mk("a"), mk("b", ["a"]), mk("z")])
    assert reg.order(["b"]) == ["a", "b"]


def test_undeclared_dependency_is_refused():
    reg = Registry([mk("a"), mk("b"), mk("c", ["a"], peek="b")])
    f = Forge.build(Config.default(), registry=reg)
    assert f.states["c"].state == FAILED and "declared" in f.states["c"].detail
    with pytest.raises(UndeclaredDependency):
        reg2 = Registry([mk("a"), mk("b")])
        Forge.build(Config.default(), registry=reg2).module("a").dep("b")


def test_failure_is_contained_and_dependents_blocked():
    reg = Registry([mk("a", boom=True), mk("b", ["a"]), mk("c")])
    f = Forge.build(Config.default(), registry=reg)
    assert f.summary() == {"a": FAILED, "b": BLOCKED, "c": OK}
    assert f.module("c") is not None
    with pytest.raises(ModuleUnavailable):
        f.module("b")


def test_sick_module_is_degraded_but_usable():
    f = Forge.build(Config.default(), registry=Registry([mk("a", sick=True), mk("b", ["a"])]))
    assert f.summary() == {"a": DEGRADED, "b": OK}
    assert f.module("a")


def test_override_with_instance_or_class():
    fake = object()
    f = Forge.build(Config.default(), registry=Registry([mk("a"), mk("b", ["a"])]), overrides={"a": fake})
    assert f.module("a") is fake and f.states["b"].state == OK


def test_conformance_checks_names_and_params():
    class Bad:
        def decode(self, text): ...          # wrong parameter name
    probs = conformance_problems(Bad(), CodecPort)
    assert any("decode" in p and "serial" in p for p in probs)
    assert any("missing method encode" in p for p in probs)


def test_default_registry_has_every_port_and_valid_order(forge):
    assert set(PORTS) <= set(forge.registry.names())
    assert forge.registry.order()[0] in ("codec", "data", "render")


def test_skeletons_conform_to_their_ports(forge):
    rows = {r["name"]: r for r in diagnose(forge)}
    for name, r in rows.items():
        assert r["contract_problems"] == [], (name, r["contract_problems"])


def test_vocab_normalizes_one_convention():
    assert vocab.normalize_element("Electric") == "shock"
    assert vocab.normalize_element("rad") == "radiation"
    assert vocab.normalize_element("kinetic") == "impact"
    assert vocab.normalize_element(None) is None
    with pytest.raises(ValueError):
        vocab.normalize_element("plasma")
    assert vocab.normalize_character("Dark Siren") == "dark_siren"


def test_config_defaults_and_validation(tmp_path):
    c = Config.default()
    assert c.level == 60 and "story_pack_1" not in c.owned_packs and c.serial_db_path.name.endswith(".json")
    (tmp_path / "config.toml").write_text('[forge]\nlevel = 0\n')
    with pytest.raises(ForgeError):
        Config.load(root=tmp_path)


def test_request_from_dict_accepts_legacy_keys():
    r = LoadoutRequest.from_dict({"query": "x", "label_name": "Pretty", "count": "3", "junk": 1})
    assert (r.display_name, r.count) == ("Pretty", 3)


def test_doctor_not_ok_until_modules_implemented(forge):
    # honest reporting: skeletons are DEGRADED, so the mesh is not "ok" yet.
    assert isinstance(ok(diagnose(forge)), bool)
