"""The registry: knows every module class, their dependencies, and a safe birth order."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Type

from .errors import ForgeError
from .module import Module


class Registry:
    def __init__(self, classes: Iterable[Type[Module]] = ()):
        self._classes: Dict[str, Type[Module]] = {}
        for c in classes:
            self.register(c)

    def register(self, cls: Type[Module]) -> Type[Module]:
        if not cls.name:
            raise ForgeError("%s has no `name`" % cls.__name__)
        self._classes[cls.name] = cls
        return cls

    def names(self) -> List[str]:
        return list(self._classes)

    def get(self, name: str) -> Type[Module]:
        return self._classes[name]

    def replace(self, name: str, cls: Type[Module]) -> None:
        """Swap an implementation (e.g. a fake in a test). The port and name must match."""
        if name not in self._classes:
            raise ForgeError("cannot replace unknown module %r" % name)
        self._classes[name] = cls

    def closure(self, wanted: Sequence[str]) -> Set[str]:
        """`wanted` plus everything they transitively require."""
        out: Set[str] = set()
        stack = list(wanted)
        while stack:
            n = stack.pop()
            if n in out:
                continue
            if n not in self._classes:
                raise ForgeError("unknown module %r" % n)
            out.add(n)
            stack.extend(self._classes[n].requires)
        return out

    def order(self, only: Optional[Sequence[str]] = None) -> List[str]:
        """Dependencies-first order. Raises on unknown requirements and cycles."""
        names = self.closure(only) if only else set(self._classes)
        for n in names:
            for r in self._classes[n].requires:
                if r not in self._classes:
                    raise ForgeError("module %r requires unknown module %r" % (n, r))
        done: List[str] = []
        visiting: Set[str] = set()

        def visit(n: str):
            if n in done:
                return
            if n in visiting:
                raise ForgeError("dependency cycle through %r" % n)
            visiting.add(n)
            for r in sorted(self._classes[n].requires):
                visit(r)
            visiting.discard(n)
            done.append(n)

        for n in sorted(names):
            visit(n)
        return done
