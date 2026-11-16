"""builder: Turn loadout requests into a verified, re-leveled Loadout.

Ports the legacy `forge.enrich` and the request-resolution loop of `forge.cmd_build`. Each request
is resolved through the catalog (or taken as an explicit serial), re-leveled through ops, then
enriched with what the BITSTREAM says (ops.describe): decoded rarity/element/name/category/parts/odds
override the catalog's labels, with a warning where they disagree. Nothing is swallowed: a failed
re-level, a level that did not take or an undecodable serial is a warning on the item; a request
that finds nothing goes to `Loadout.unmatched`. Neighbours are reached only through their ports
(`catalog`, `ops`). Stateless. See CONTRACT.md in this directory.


DISCLOSURE (what this code does)
  Reads: nothing from disk. Writes: nothing. Network: none. Risk: none (pure computation on values passed in).
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional, Sequence, Tuple

from ...core import vocab
from ...core.module import Module
from ...core.ports import BuilderPort
from ...core.types import (
    CatalogEntry, HealthCheck, HealthReport, Loadout, LoadoutItem, LoadoutRequest, SearchQuery,
)

DEFAULT_TITLE = "Break Free Loadout"
DEFAULT_ITEM_NAME = "Item"              # legacy name of an explicit-serial entry that gave none
SEARCH_FIELDS = ("query", "type", "element", "manufacturer", "rarity", "character")

_DASH = "—"
_NO_ELEMENT = ("", "n/a", "na", "-", _DASH)      # database spellings of "no element label"

# Known answers for health(): the first 'anarchy' shotgun row of the shipped database (stored at
# level 50) and the same item re-leveled to 60.
_KNOWN_SERIAL = r"@Uge(J0Fme!K{9I5@RG/*Fs6^dF^+SzB{X<<U4k{EX7U~sh7HS*<"
_KNOWN_SERIAL_60 = r"@Uge(J0FnkbU{9I5@RG/*Fs6^dF^+SzB{X<<U4k{EX7U~sh7HS*<"
_MISS_QUERY = "zz-no-such-item-zz"
_REAL_KNOWN = dict(serial=_KNOWN_SERIAL, serial_60=_KNOWN_SERIAL_60, query="anarchy", type="shotgun",
                   name="Anarchy", element="impact")
# The same probe for the bundled synthetic dataset (data/synthetic; tests check these match its
# manifest/known_answers.json). SYNTHETIC - not game data.
_SYNTHETIC_KNOWN = dict(serial='@UggM92027QHL>Ragw5UjB>Qlpo#-Pq100', serial_60='@UggM92022%!L>Ragw5UjB>Qlpo#-Pq100',
                        query="open vault", type="shotgun", name="Open Vault", element="cryo")


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _as_level(level) -> int:
    """`level` as an int; raises ValueError/TypeError for anything that is not a whole number."""
    if isinstance(level, bool):
        raise TypeError("level must be a number, not a bool")
    return int(level)


def _element_hint(value) -> Tuple[Optional[str], Optional[str]]:
    """(vocab element or None, problem or None) for a database/request element label."""
    text = _text(value)
    if text.lower() in _NO_ELEMENT:
        return None, None
    try:
        return vocab.normalize_element(text), None
    except ValueError:
        return None, "element %r is not a known element and was ignored" % text


def _clean_serial(serial) -> str:
    """Whitespace, wrapping quotes and a trailing comma removed (a serial pasted from JSON/web)."""
    text = _text(serial)
    while text and text[-1] in ",;":
        text = text[:-1].rstrip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def describe_request(req: LoadoutRequest) -> str:
    """How a request is named in `Loadout.unmatched`: its query text, else its search fields."""
    if _text(req.query):
        return req.query
    bits = ["%s=%s" % (f, _text(getattr(req, f))) for f in SEARCH_FIELDS[1:] if _text(getattr(req, f))]
    return " ".join(bits) if bits else "(empty request)"


class BuilderModule(Module):
    name = "builder"
    purpose = "Turn loadout requests into a verified, re-leveled Loadout."
    requires = ('catalog', 'ops')
    port = BuilderPort

    # ---- BuilderPort ----------------------------------------------------------------------

    def enrich(self, entry: CatalogEntry, level: Optional[int] = None) -> LoadoutItem:
        """One catalog row -> a LoadoutItem: re-leveled (when `level` is given) and decoded.

        Never raises for a bad serial or a failing neighbour: each failure becomes a warning on the
        item. The item's `level` is what the code DECODES as, so a re-level that did not take shows
        the real level (plus a warning), never the requested one.
        """
        ops = self.dep("ops")
        serial = entry.serial
        warnings: List[str] = []

        want: Optional[int] = None
        if level is not None:
            try:
                want = _as_level(level)
                relevelled = ops.relevel(serial, want)
                if not isinstance(relevelled, str) or not relevelled:
                    raise TypeError("ops.relevel returned %r" % (relevelled,))
                serial = relevelled
            except Exception as ex:
                warnings.append("re-level to %s failed (%s) %s code left at its stored level"
                                % (level, ex, _DASH))

        info = None
        try:
            info = ops.describe(serial)
        except Exception as ex:
            warnings.append("decode failed: %s" % ex)
        dlevel = info.level if info is not None else None
        if want is not None and dlevel is not None and want != dlevel:
            warnings.append("requested level %s but the code decodes as %s" % (want, dlevel))

        rarity = entry.rarity
        element, hint_problem = _element_hint(entry.element)
        if hint_problem:
            warnings.append("catalog entry: " + hint_problem)
        hint_element = element
        category = legendary_name = None
        parts: Tuple[str, ...] = ()
        odds = ""

        if info is not None:
            warnings.extend(info.warnings)
            if info.manifest_ok:
                category = info.category
                legendary_name = info.legendary_name
                parts = tuple(p.label() for p in info.parts)
                # Decoded facts are the truth; the database's labels are hints.
                if info.rarity:
                    if rarity and rarity.strip().lower() != info.rarity.lower():
                        warnings.append("database says rarity %s, the serial says %s %s trusting the serial"
                                        % (rarity, info.rarity, _DASH))
                    rarity = info.rarity
                if info.element:
                    if hint_element and hint_element != info.element:
                        warnings.append("database says element %s, the serial says %s %s trusting the serial"
                                        % (vocab.ELEMENT_LABELS.get(hint_element, hint_element),
                                           vocab.ELEMENT_LABELS.get(info.element, info.element), _DASH))
                    element = info.element
                try:
                    odds = ops.format_odds(ops.rarity_estimate(info))
                except Exception as ex:
                    warnings.append("odds lookup failed: %s" % ex)

        return LoadoutItem(
            name=entry.name or "?", serial=serial, level=dlevel, manufacturer=entry.manufacturer,
            label=entry.label or entry.type, type=entry.type, weapon_type=entry.weapon_type,
            rarity=rarity, element=element, category=category, legendary_name=legendary_name,
            parts=parts, odds=odds, source=entry.source, warnings=tuple(warnings))

    def build(self, requests: Sequence[LoadoutRequest], level: Optional[int] = None,
              title: str = DEFAULT_TITLE) -> Loadout:
        """Resolve every request, in order, into one Loadout.

        `level=None` means "do not re-level" (items keep their stored level); an int re-levels every
        item. Misses go to `unmatched`; build-level notices (hidden/short results, a failed search,
        a skipped request) go to `Loadout.warnings`. Per-item problems stay on the items.
        """
        items: List[LoadoutItem] = []
        groups: List[str] = []
        unmatched: List[str] = []
        notices: List[str] = []

        try:
            wanted = None if level is None else _as_level(level)
        except (TypeError, ValueError):
            notices.append("level %r is not a whole number; codes were not re-leveled" % (level,))
            wanted = None

        for req in requests:
            if isinstance(req, dict):
                req = LoadoutRequest.from_dict(req)
            group = req.group or None
            if group and group not in groups:
                groups.append(group)
            if _text(req.serial):
                found = [self._explicit_item(req, wanted)]
            else:
                found = self._search_items(req, wanted, unmatched, notices)
            for item in found:
                changes = {"group": group, "note": req.note or ""}
                if req.display_name:
                    changes["display_name"] = req.display_name
                items.append(dataclasses.replace(item, **changes))

        return Loadout(title=title, level=wanted, items=tuple(items), groups=tuple(groups),
                       unmatched=tuple(unmatched), warnings=tuple(notices))

    # ---- resolving one request ------------------------------------------------------------

    def _explicit_item(self, req: LoadoutRequest, level: Optional[int]) -> LoadoutItem:
        """A request that names its serial: no search. The request's own fields stand in for the
        catalog row (legacy behaviour), and bad ones are reported on the item."""
        element, problem = _element_hint(req.element)
        entry = CatalogEntry(
            serial=_clean_serial(req.serial), name=req.name or DEFAULT_ITEM_NAME,
            type=req.type or "", manufacturer=req.manufacturer or "",
            label=req.label or req.type or "", rarity=req.rarity or "", element=element)
        item = self.enrich(entry, level)
        if problem:
            item = dataclasses.replace(item, warnings=item.warnings + ("request: " + problem,))
        return item

    def _search_items(self, req: LoadoutRequest, level: Optional[int],
                      unmatched: List[str], notices: List[str]) -> List[LoadoutItem]:
        label = describe_request(req)
        if not any(_text(getattr(req, f)) for f in SEARCH_FIELDS):
            unmatched.append(label)
            notices.append("a request with neither a serial nor any search field was skipped")
            return []
        try:
            count = int(req.count)
        except (TypeError, ValueError):
            count = 0
        if count < 1:
            notices.append("%s: count %r is not a positive number; asking for 1" % (label, req.count))
            count = 1
        query = SearchQuery(
            query=req.query, type=req.type, element=req.element, manufacturer=req.manufacturer,
            rarity=req.rarity, character=req.character, limit=count)
        try:
            result = self.dep("catalog").search(query)
        except Exception as ex:
            unmatched.append(label)
            notices.append("%s: search failed (%s: %s)" % (label, type(ex).__name__, ex))
            return []

        entries = list(result.entries)
        if result.hidden_by_pack:
            hidden = ", ".join("%s: %d" % (pack, n) for pack, n in sorted(result.hidden_by_pack.items()))
            notices.append("%s: matches hidden because they need content that is not owned (%s)"
                           % (label, hidden))
        if len(entries) < count and result.dropped_element_mismatch:
            notices.append("%s: %d catalog label(s) disagreed with the serial's element and were skipped"
                           % (label, result.dropped_element_mismatch))
        if not entries:
            unmatched.append(label)
            return []
        if len(entries) < count:
            notices.append("%s: asked for %d, found %d" % (label, count, len(entries)))
        return [self.enrich(e, level) for e in entries]

    # ---- health ---------------------------------------------------------------------------

    def health(self) -> HealthReport:
        """Known-answer checks (a one-item loadout at level 60, an explicit serial, a miss). Never raises."""
        checks: List[HealthCheck] = []
        known = dict(_REAL_KNOWN)
        if self.config.is_synthetic:      # the bundled fictional dataset has its own probe item
            known = dict(_SYNTHETIC_KNOWN)

        def check(name: str, fn) -> None:
            try:
                ok, detail = fn()
            except Exception as ex:
                ok, detail = False, "%s: %s" % (type(ex).__name__, ex)
            checks.append(HealthCheck(name, bool(ok), detail))

        def one_item_at_60():
            lo = self.build([LoadoutRequest(query=known["query"], type=known["type"], group="Probe")],
                            level=60, title="Health probe")
            it = lo.items[0] if len(lo.items) == 1 else None
            ok = (it is not None and it.level == 60 and it.serial == known["serial_60"]
                  and not it.warnings and it.legendary_name == known["name"] and it.element == known["element"]
                  and lo.groups == ("Probe",) and not lo.unmatched)
            return ok, ("'%s' %s -> %d item(s)%s" % (known["query"], known["type"], len(lo.items), "" if it is None else
                        ", level %s, %s %s, %d warning(s)" % (it.level, it.rarity, it.legendary_name,
                                                              len(it.warnings))))

        def explicit_serial():
            lo = self.build([LoadoutRequest(serial=known["serial"])], level=60)
            it = lo.items[0] if len(lo.items) == 1 else None
            return (it is not None and it.serial == known["serial_60"] and it.level == 60
                    and not it.warnings), "explicit serial re-leveled to 60"

        def no_relevel_keeps_level():
            lo = self.build([LoadoutRequest(serial=known["serial"])])
            it = lo.items[0] if len(lo.items) == 1 else None
            return (it is not None and it.serial == known["serial"] and it.level == 50
                    and lo.level is None), "level=None leaves the stored level (50)"

        def miss_is_unmatched():
            lo = self.build([LoadoutRequest(query=_MISS_QUERY)], level=60)
            return lo.unmatched == (_MISS_QUERY,) and not lo.items, "impossible query -> unmatched"

        check("one_item_at_60", one_item_at_60)
        check("explicit_serial", explicit_serial)
        check("no_relevel_keeps_level", no_relevel_keeps_level)
        check("miss_is_unmatched", miss_is_unmatched)
        bad = [c.name for c in checks if not c.ok]
        return HealthReport.from_checks(checks, "ok" if not bad else "failing: " + ", ".join(bad))


MODULE = BuilderModule
