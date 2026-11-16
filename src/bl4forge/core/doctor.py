"""The doctor: one command that tells you which cell is sick and why."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List

from .forge import BLOCKED, DEGRADED, FAILED, OK, Forge
from .module import conformance_problems
from .ports import PORTS

_MARK = {OK: "OK      ", DEGRADED: "DEGRADED", FAILED: "FAILED  ", BLOCKED: "BLOCKED "}


def _variants(path: str) -> List[str]:
    """A path as written and with the other slash style, so either spelling in a message is caught."""
    return [path, path.replace("\\", "/"), path.replace("/", "\\")]


def make_scrubber(config) -> Callable[[str], str]:
    """Return a function that replaces absolute local paths in a message with non-identifying labels.

    Health/doctor details are shown in the UI and pasted into bug reports, so they must not leak the
    user's folder layout or account name. Anything under the project root becomes a relative path; the
    data folder, the config file, the loot-pak tool paths and the home folder get fixed labels.
    """
    pairs: List[tuple] = []

    def add(path, label):
        if path:
            for v in _variants(str(path)):
                if len(v) > 3:
                    pairs.append((v, label))

    try:
        add(config.data_dir, config.data_label)
        add(os.environ.get("BL4FORGE_CONFIG", ""), "<config file>")
        add(Path(config.root) / "config.toml", "config.toml")
        for key, value in dict(config.lootpak).items():
            add(value, "<%s path>" % key)
        add(config.root, ".")
        add(Path.home(), "~")
    except Exception:       # a scrubber must never break the doctor
        pass
    pairs.sort(key=lambda kv: -len(kv[0]))

    def scrub(text):
        if not isinstance(text, str):
            return text
        for needle, label in pairs:
            text = text.replace(needle + "/", label + "/").replace(needle + "\\", label + "/").replace(needle, label)
        return text
    return scrub


def diagnose(forge: Forge) -> List[dict]:
    scrub = make_scrubber(forge.config)
    rows = []
    for name in forge.registry.order(list(forge.states)):
        st = forge.states[name]
        klass = forge.registry.get(name)
        problems: List[str] = []
        if st.instance is not None and name in PORTS:
            problems = [scrub(x) for x in conformance_problems(st.instance, PORTS[name])]
        rows.append({
            "name": name, "state": st.state, "detail": scrub(st.detail), "purpose": klass.purpose,
            "requires": list(klass.requires), "contract_problems": problems,
            "checks": [{"name": c.name, "ok": c.ok, "detail": scrub(c.detail)}
                       for c in (st.health.checks if st.health else ())],
        })
    return rows


def format_report(rows: List[dict], verbose: bool = False) -> str:
    out = []
    width = max((len(r["name"]) for r in rows), default=8)
    for r in rows:
        needs = ("  <- " + ", ".join(r["requires"])) if r["requires"] else ""
        out.append("%s  %-*s  %s%s" % (_MARK[r["state"]], width, r["name"], r["detail"] or r["purpose"], needs))
        for p in r["contract_problems"]:
            out.append("          contract: %s" % p)
        if verbose:
            out.append("          purpose: %s" % r["purpose"])
            for c in r["checks"]:
                out.append("          [%s] %s %s" % ("x" if c["ok"] else " ", c["name"], c["detail"]))
    healthy = sum(1 for r in rows if r["state"] == OK and not r["contract_problems"])
    out.append("")
    out.append("%d/%d modules healthy" % (healthy, len(rows)))
    return "\n".join(out)


def ok(rows: List[dict]) -> bool:
    return all(r["state"] == OK and not r["contract_problems"] for r in rows)
