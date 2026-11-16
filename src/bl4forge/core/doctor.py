"""The doctor: one command that tells you which cell is sick and why."""
from __future__ import annotations

from typing import List

from .forge import BLOCKED, DEGRADED, FAILED, OK, Forge
from .module import conformance_problems
from .ports import PORTS

_MARK = {OK: "OK      ", DEGRADED: "DEGRADED", FAILED: "FAILED  ", BLOCKED: "BLOCKED "}


def diagnose(forge: Forge) -> List[dict]:
    rows = []
    for name in forge.registry.order(list(forge.states)):
        st = forge.states[name]
        klass = forge.registry.get(name)
        problems: List[str] = []
        if st.instance is not None and name in PORTS:
            problems = conformance_problems(st.instance, PORTS[name])
        rows.append({
            "name": name, "state": st.state, "detail": st.detail, "purpose": klass.purpose,
            "requires": list(klass.requires), "contract_problems": problems,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail}
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
