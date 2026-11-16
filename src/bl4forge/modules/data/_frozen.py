"""Read-only containers for everything the data module hands out.

The manifest is loaded once per module instance and shared by every caller, so a caller that
mutated a returned table would silently corrupt every other caller. These subclasses stay
`dict` / `list` (so `isinstance`, `==`, `json.dumps` and iteration behave exactly as before) but
refuse every mutation with TypeError. Copying, deep-copying and pickling give back plain,
mutable `dict` / `list` values.
"""
from __future__ import annotations

import copy
from typing import Any


def _refuse(self, *args, **kwargs):
    raise TypeError("%s is read-only (it is shared manifest data; copy it with dict()/list() "
                    "if you need to change it)" % type(self).__name__)


class FrozenDict(dict):
    __slots__ = ()
    __setitem__ = __delitem__ = __ior__ = _refuse
    clear = pop = popitem = setdefault = update = _refuse

    def copy(self) -> dict:
        return dict(self)

    def __copy__(self) -> dict:
        return dict(self)

    def __deepcopy__(self, memo) -> dict:
        return {copy.deepcopy(k, memo): copy.deepcopy(v, memo) for k, v in self.items()}

    def __reduce__(self):
        return (dict, (dict(self),))


class FrozenList(list):
    __slots__ = ()
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _refuse
    append = extend = insert = remove = pop = clear = sort = reverse = _refuse

    def copy(self) -> list:
        return list(self)

    def __copy__(self) -> list:
        return list(self)

    def __deepcopy__(self, memo) -> list:
        return [copy.deepcopy(v, memo) for v in self]

    def __reduce__(self):
        return (list, (list(self),))


def freeze(value: Any) -> Any:
    """Recursively replace plain dicts/lists (JSON data) with their read-only twins."""
    if isinstance(value, dict):
        return FrozenDict((k, freeze(v)) for k, v in value.items())
    if isinstance(value, list):
        return FrozenList(freeze(v) for v in value)
    return value
