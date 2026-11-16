"""The cell wall: how a module declares itself and how it is allowed to see its neighbours."""
from __future__ import annotations

import inspect
from typing import ClassVar, List, Mapping, Tuple, Type

from .config import Config
from .errors import UndeclaredDependency
from .types import HealthCheck, HealthReport


class ModuleContext:
    """What a module receives at birth: config + ONLY the neighbours it declared in `requires`."""

    def __init__(self, name: str, config: Config, deps: Mapping[str, object]):
        self._name = name
        self.config = config
        self._deps = dict(deps)

    def dep(self, name: str):
        if name not in self._deps:
            raise UndeclaredDependency(
                "module %r asked for %r but did not declare it in `requires` (declared: %s)"
                % (self._name, name, ", ".join(sorted(self._deps)) or "none"))
        return self._deps[name]


class Module:
    """Base class for every cell. Subclasses implement their port and set the class attributes.

    name      registry key and attribute name on Forge (e.g. 'codec')
    purpose   one sentence: what this cell is FOR. Shown by the doctor.
    requires  names of neighbours this cell needs. Nothing else is visible to it.
    port      the Protocol (core/ports.py) this class must satisfy.
    """

    name: ClassVar[str] = ""
    purpose: ClassVar[str] = ""
    requires: ClassVar[Tuple[str, ...]] = ()
    port: ClassVar[type] = object

    def __init__(self, ctx: ModuleContext):
        self.ctx = ctx
        self.config = ctx.config

    def dep(self, name: str):
        return self.ctx.dep(name)

    def health(self) -> HealthReport:
        """Cheap self-check the doctor runs. Override with real checks (known-answer tests).

        Contract: never raise; return ok=False with a reason instead. Keep it fast (<1s).
        """
        return HealthReport(ok=True, summary="no self-check defined")


class NotImplementedModule(Module):
    """Mixin for skeleton modules: honest about being empty, so the doctor shows real progress."""

    def health(self) -> HealthReport:
        return HealthReport(ok=False, summary="not implemented yet",
                            checks=(HealthCheck("implemented", False, "skeleton only"),))

    def _todo(self, what: str):
        raise NotImplementedError("module %r has not implemented %s yet" % (self.name, what))


def conformance_problems(instance: object, port: Type) -> List[str]:
    """Compare an instance to a Protocol: missing methods and drifted parameter names."""
    problems: List[str] = []
    for attr, expected in vars(port).items():
        if attr.startswith("_") or not callable(expected):
            continue
        actual = getattr(instance, attr, None)
        if actual is None or not callable(actual):
            problems.append("missing method %s()" % attr)
            continue
        try:
            want = [p for p in inspect.signature(expected).parameters if p != "self"]
            have = [p for p in inspect.signature(actual).parameters if p != "self"]
        except (TypeError, ValueError):
            continue
        if want != have:
            problems.append("%s(%s) should be %s(%s)" % (attr, ", ".join(have), attr, ", ".join(want)))
    return problems
