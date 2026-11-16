"""The organism: builds every module in dependency order and keeps failures contained.

A module that fails to start does not take the others down. Its dependents are marked `blocked`
(not started), everything unrelated keeps working, and the doctor says exactly which cell is sick.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Type, Union

from .config import Config
from .errors import ForgeError, ModuleUnavailable
from .module import Module, ModuleContext
from .registry import Registry
from .types import HealthReport

OK, DEGRADED, FAILED, BLOCKED = "ok", "degraded", "failed", "blocked"


@dataclass
class ModuleState:
    name: str
    state: str                       # ok | degraded | failed | blocked
    detail: str = ""
    instance: Optional[Module] = None
    health: Optional[HealthReport] = None


class Forge:
    def __init__(self, config: Config, registry: Registry, states: Dict[str, ModuleState]):
        self.config = config
        self.registry = registry
        self.states = states

    # ---- construction ----
    @classmethod
    def build(cls, config: Optional[Config] = None, registry: Optional[Registry] = None,
              overrides: Optional[Mapping[str, Union[Type[Module], Module]]] = None,
              only: Optional[Sequence[str]] = None) -> "Forge":
        """Start the mesh. `only` starts just those modules plus what they need; `overrides` swaps an
        implementation (a Module subclass, or a ready instance such as a test fake)."""
        from ..modules import default_registry

        config = config or Config.load()
        registry = registry or default_registry()
        overrides = dict(overrides or {})
        for name, ov in overrides.items():
            if isinstance(ov, type):
                registry.replace(name, ov)
        states: Dict[str, ModuleState] = {}
        for name in registry.order(only):
            klass = registry.get(name)
            if name in overrides and not isinstance(overrides[name], type):
                inst = overrides[name]
                states[name] = ModuleState(name, OK, "override instance", inst, None)
                continue
            bad = [r for r in klass.requires if states[r].state in (FAILED, BLOCKED)]
            if bad:
                states[name] = ModuleState(
                    name, BLOCKED, "needs %s which is %s" % (", ".join(bad), "/".join(states[b].state for b in bad)))
                continue
            deps = {r: states[r].instance for r in klass.requires}
            try:
                inst = klass(ModuleContext(name, config, deps))
            except Exception as ex:  # a sick cell must not crash the organism
                states[name] = ModuleState(name, FAILED, "%s: %s" % (type(ex).__name__, ex))
                continue
            try:
                rep = inst.health()
            except Exception as ex:
                rep = HealthReport(ok=False, summary="health() raised %s: %s" % (type(ex).__name__, ex))
            states[name] = ModuleState(name, OK if rep.ok else DEGRADED, rep.summary, inst, rep)
        return cls(config, registry, states)

    # ---- access ----
    def module(self, name: str):
        st = self.states.get(name)
        if st is None:
            raise ForgeError("module %r is not part of this forge" % name)
        if st.state in (FAILED, BLOCKED) or st.instance is None:
            raise ModuleUnavailable("module %r is %s: %s" % (name, st.state, st.detail))
        return st.instance

    def __getattr__(self, name: str):
        if name.startswith("_") or name in ("config", "registry", "states"):
            raise AttributeError(name)
        if name in self.states:
            return self.module(name)
        raise AttributeError(name)

    def summary(self) -> Dict[str, str]:
        return {n: s.state for n, s in self.states.items()}
