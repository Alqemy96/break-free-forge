> Historical note (public copy): the "legacy" oracle and the 9,875-serial database mentioned below are NOT shipped; parity tests that need them skip. Kept for the reasoning behind the module rules.

# Rules of engagement for anyone (human or agent) building a module

1. **You own exactly one module directory** `src/bl4forge/modules/<name>/` plus the tests
   `tests/modules/test_<name>*.py`. Do not edit `core/`, another module, `legacy/`, or `data/`.
2. **The port is fixed.** Implement `core/ports.py::<Name>Port` exactly (method names and parameter
   names; the doctor checks them). If you believe a port must change, append a request to
   `docs/CHANGE_REQUESTS.md` (what, why, who it affects) and keep going with the current port.
3. **See only declared neighbours.** Get them with `self.dep("name")`, and only names listed in your
   class's `requires`. Never import another module's package.
4. **Shared things live in `core/`.** Use `core.types`, `core.vocab`, `core.errors`. Raise
   `ForgeError` subclasses (never bare `ValueError`/`KeyError` across a port).
5. **No module-level mutable state, no globals, no singletons.** Per-instance caches only. Two
   Forge instances in one process must not interfere (legacy `partsdb` violated this).
6. **Stdlib only. Python 3.10-3.14.** No third-party imports in `src/`.
7. **Honest `health()`**: replace the skeleton's. Known-answer self-checks, fast (<1 s), never raises.
8. **Parity with legacy is the acceptance bar.** The legacy scripts in `legacy/skills/bl4-loadout/
   scripts/` are the oracle. Your parity tests must run your module and the legacy function over the
   whole serial database (9,875 codes) and show identical results. Where a result is intentionally
   different (e.g. elements are now lower-case vocab names), the test states the mapping explicitly.
   A legacy bug you choose NOT to preserve is documented in your module's CONTRACT.md "Deviations".
9. **Preserve the hard-won rules** in your CONTRACT.md "Invariants". Each one gets a test named after it.
10. **Done means:** `python3 -m pytest tests/modules/test_<name>*.py` is green, the doctor shows your
    module `OK` with no contract problems (`python -m bl4forge doctor`), and you have reported
    results, deviations, and any change requests in your final message.
