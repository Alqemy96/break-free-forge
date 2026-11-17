"""save_verify: prove an edited save changed exactly what was planned, and nothing else.

"Passed structural checks" is never the same as "valid in game"; this tool makes the structural half
strict and repeatable so the in-game half starts from a known-good file.

  oracle     python -m bl4forge.tools.save_verify oracle FILE.sav --key-file KEY
             Decrypts FILE.sav and reports every container check PASS/FAIL: block alignment, AES-256-ECB,
             the padded AND the unpadded reading (PKCS7, zlib stream complete, trailer size, trailer
             length == inflated length; adler32 too for --platform pc), agreement with
             `_container.decrypt`, and UTF-8.

  roundtrip  python -m bl4forge.tools.save_verify roundtrip ORIGINAL.sav EDITED.sav --key-file KEY
                 --expected-diff PLAN [--allow-reserialize]
             Runs the oracle on both files, diffs the decrypted YAML line by line, and passes only when
             the changed lines are EXACTLY the ones PLAN lists and every other byte is identical. Then it
             re-encrypts the edited plaintext with `_container.encrypt` and runs the oracle on the result.
             With --allow-reserialize the comparison is on parsed values (path -> value), not bytes, so
             the game's own re-serialisation does not count as a change; the report says so.

Expected-diff file (PLAN), one planned edit per line; blank lines and lines starting with # are ignored:

  42                      line 42 of the ORIGINAL plaintext changes (to anything)
  42 = <new line>         line 42 changes and its new text is exactly <new line> (indentation optional)
  = <new line>            some line changes to exactly <new line>
  key <path>              the value at <path> changes, e.g. key state/currencies/cash
  key <path> = <value>    ...and its new value is <value>

Every planned edit must be matched by exactly one change and every change by exactly one planned edit.
`= ...` matches the new line (exact, or ignoring surrounding spaces) or the new parsed value (quotes removed). Paths are
the ones printed in the report (`/`-joined keys, `-` for a list item, `[n]` for the n-th repeat).

Exit codes: 0 every check passed, 1 a check failed (the report lists every unexpected difference),
2 bad input (unreadable file, bad key file, bad PLAN line).

DISCLOSURE (what this code does)
  Reads: the save files, the key file and the expected-diff file named on the command line. Writes: nothing
  (the re-encrypted copy exists only in memory). Network: none. Risk: none to the saves. The key comes only
  from the user's own key file; it is never printed, logged or embedded, and nothing here searches for a key.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
import zlib
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

from ..core.errors import SaveError
from ..modules.save import _aes, _container, _yamltext

EXIT_OK, EXIT_MISMATCH, EXIT_USAGE = 0, 1, 2
PLATFORMS = ("ps5", "pc")
_FOOTER_BYTES = {"ps5": 4, "pc": 8}
_KEY_FILE_MAX = 4096
PASS, FAIL, INFO = "PASS", "FAIL", "INFO"


# ---- key ---------------------------------------------------------------------------------------------
def load_key(path: str) -> bytes:
    """Read a 32-byte AES key from a file the user supplies: 64 hex digits (whitespace and an optional 0x
    allowed) or exactly 32 raw bytes. Error messages describe the file's shape, never its content."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_KEY_FILE_MAX + 1)
    except OSError as ex:
        raise SaveError("cannot read key file %s (%s)" % (path, ex.strerror or type(ex).__name__)) from None
    if len(raw) > _KEY_FILE_MAX:
        raise SaveError("key file %s is larger than %d bytes; it is not a key file" % (path, _KEY_FILE_MAX))
    try:
        compact = re.sub(r"\s+", "", raw.decode("ascii"))
    except UnicodeDecodeError:
        compact = ""
    if compact[:2].lower() == "0x":
        compact = compact[2:]
    if re.fullmatch(r"[0-9A-Fa-f]{64}", compact):
        return bytes.fromhex(compact)
    if len(raw) == 32:
        return raw
    raise SaveError("key file %s holds neither 64 hex digits nor 32 raw bytes (%d bytes read; content not shown)"
                    % (path, len(raw)))


def resolve_key(key_file: str, platform: str, steam_id: Optional[str]) -> bytes:
    """The AES key for `platform`. For pc the key file holds the base key and the Steam ID is mixed in by
    the existing `_container.pc_key`."""
    key = load_key(key_file)
    if platform == "pc":
        if not steam_id:
            raise SaveError("--platform pc needs --steam-id (the key file then holds the PC base key)")
        return _container.pc_key(key, steam_id)
    return key


def _read_file(path: str, what: str) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as ex:
        raise SaveError("cannot read %s %s (%s)" % (what, path, ex.strerror or type(ex).__name__)) from None


# ---- oracle --------------------------------------------------------------------------------------------
class Check(NamedTuple):
    name: str
    status: str             # PASS / FAIL / INFO
    detail: str = ""
    gate: bool = True       # gates decide the verdict; diagnostics (gate=False) only explain it


def _status(ok: bool) -> str:
    return PASS if ok else FAIL


class OracleResult(NamedTuple):
    checks: List[Check]
    plaintext: Optional[bytes]   # the YAML bytes `_container.decrypt` returned, if it accepted the file
    reading: Optional[str]       # "padded", "unpadded" or None

    @property
    def ok(self) -> bool:
        return self.plaintext is not None and all(c.status != FAIL for c in self.checks if c.gate)


def _stream_facts(plain: bytes, platform: str, prefix: str) -> Tuple[List[Check], Optional[bytes]]:
    """Diagnose one candidate plaintext as zlib stream + trailer, check by check. Read-only reporting: the
    verdict still comes from `_container.decrypt`, and the oracle fails if the two ever disagree."""
    footer_len = _FOOTER_BYTES[platform]
    out: List[Check] = []
    d = zlib.decompressobj()
    try:
        yaml = d.decompress(plain)
    except zlib.error as ex:
        return [Check(prefix + "zlib stream decodes", FAIL, str(ex), gate=False)], None
    out.append(Check(prefix + "zlib stream decodes", PASS, "%d bytes inflated" % len(yaml), gate=False))
    if not d.eof:
        out.append(Check(prefix + "zlib stream is complete", FAIL, "no end-of-stream marker (truncated)", gate=False))
        return out, None
    out.append(Check(prefix + "zlib stream is complete", PASS, "", gate=False))
    tail = d.unused_data
    if len(tail) != footer_len:
        out.append(Check(prefix + "trailer is %d bytes" % footer_len, FAIL,
                         "found %d bytes after the zlib stream" % len(tail), gate=False))
        return out, None
    out.append(Check(prefix + "trailer is %d bytes" % footer_len, PASS, "", gate=False))
    if platform == "ps5":
        (length,) = struct.unpack("<I", tail)
        adler_ok = True
    else:
        adler, length = struct.unpack("<II", tail)
        adler_ok = adler == zlib.adler32(yaml)
    out.append(Check(prefix + "trailer length == inflated length", _status(length == len(yaml)),
                     "trailer %d, inflated %d" % (length, len(yaml)), gate=False))
    if platform == "pc":
        out.append(Check(prefix + "trailer adler32 matches", _status(adler_ok), "", gate=False))
    good = length == len(yaml) and adler_ok
    return out, (yaml if good else None)


def oracle(data: bytes, key: bytes, platform: str) -> OracleResult:
    """Every container check on one encrypted save, PASS/FAIL. Decryption is `_aes.ecb_decrypt`; PKCS7 is
    `_container.pkcs7_unpad`; the verdict is `_container.decrypt` (padded first, unpadded fallback)."""
    if platform not in PLATFORMS:
        raise SaveError("unknown platform %r" % platform)
    checks: List[Check] = []
    aligned = len(data) > 0 and len(data) % 16 == 0
    checks.append(Check("ciphertext is a non-empty multiple of 16 bytes", _status(aligned), "%d bytes" % len(data)))
    if not aligned:
        return OracleResult(checks, None, None)
    try:
        raw = _aes.ecb_decrypt(key, data)
    except SaveError as ex:
        checks.append(Check("AES-256-ECB decrypt", FAIL, str(ex)))
        return OracleResult(checks, None, None)
    checks.append(Check("AES-256-ECB decrypt", PASS, "%d blocks" % (len(data) // 16)))

    readings: Dict[str, bytes] = {}
    packed_len: Dict[str, int] = {}
    try:
        padded = _container.pkcs7_unpad(raw)
        checks.append(Check("padded: PKCS7 padding valid", PASS, "%d pad bytes" % (len(raw) - len(padded)), gate=False))
    except SaveError as ex:
        padded = None
        checks.append(Check("padded: PKCS7 padding valid", FAIL, str(ex), gate=False))
    if padded is not None:
        sub, yaml = _stream_facts(padded, platform, "padded: ")
        checks.extend(sub)
        if yaml is not None:
            readings["padded"], packed_len["padded"] = yaml, len(padded)
    sub, yaml = _stream_facts(raw, platform, "unpadded: ")
    checks.extend(sub)
    if yaml is not None:
        readings["unpadded"], packed_len["unpadded"] = yaml, len(raw)

    reading = "padded" if "padded" in readings else ("unpadded" if "unpadded" in readings else None)
    checks.append(Check("a padded or unpadded reading validates (zlib stream + trailer)", _status(reading is not None),
                        {0: "neither reading validates: wrong key, wrong platform or corrupt file",
                         1: "%s reading" % reading, 2: "both readings validate; the padded one is used"}[len(readings)]))
    try:
        plaintext: Optional[bytes] = _container.decrypt(data, key, platform)
        checks.append(Check("_container.decrypt accepts the file", PASS, "%d bytes of YAML" % len(plaintext)))
    except SaveError as ex:
        plaintext = None
        checks.append(Check("_container.decrypt accepts the file", FAIL, str(ex)))
    agree = (plaintext is None and reading is None) or (
        plaintext is not None and reading is not None and readings[reading] == plaintext)
    checks.append(Check("oracle diagnostics agree with _container.decrypt", _status(agree),
                        "" if agree else "the step-by-step reading and the container disagree; trust neither"))
    if reading == "padded" and packed_len["padded"] % 16 == 0:
        checks.append(Check("padding form", INFO, "packed data is block-aligned yet carries a full PKCS7 block; the "
                            "game itself writes no padding here. Whether the game loads this form: UNVERIFIED", gate=False))
    elif reading is not None:
        checks.append(Check("padding form", INFO, "%s, as the game writes it" % reading, gate=False))
    if plaintext is not None:
        try:
            plaintext.decode("utf-8")
            checks.append(Check("plaintext is UTF-8", PASS, ""))
        except UnicodeDecodeError as ex:
            checks.append(Check("plaintext is UTF-8", FAIL, str(ex)))
    return OracleResult(checks, plaintext, reading)


def render_oracle(title: str, result: OracleResult) -> List[str]:
    lines = ["== oracle: %s" % title]
    diag = [c for c in result.checks if not c.gate]
    gates = [c for c in result.checks if c.gate]
    for group, label in ((gates[:2], None), (diag, "readings (diagnostic; normally exactly one reading validates)"),
                         (gates[2:], None)):
        if label:
            lines.append("   %s:" % label)
        for c in group:
            lines.append("%s%-4s  %s%s" % ("      " if not c.gate else "   ", c.status, c.name,
                                            ("  [%s]" % c.detail) if c.detail else ""))
    lines.append("   ORACLE %s" % ("PASS" if result.ok else "FAIL"))
    return lines


# ---- plan (expected-diff file) -----------------------------------------------------------------------
class Expectation(NamedTuple):
    plan_line: int            # line number in the PLAN file, for the report
    source: str               # the PLAN line as written
    line: Optional[int]       # 1-based line in the ORIGINAL plaintext
    path: Optional[str]       # value path (see module docstring)
    content: Optional[str]    # new line text, or new value


_PLAN = re.compile(r"^(?P<line>\d+)?\s*(?:key\s+(?P<path>\S+))?\s*(?:=\s?(?P<content>.*))?$")


def parse_plan(text: str) -> List[Expectation]:
    out: List[Expectation] = []
    for n, raw in enumerate(text.splitlines(), 1):
        body = raw.rstrip("\r")
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        m = _PLAN.match(body.strip() if not body.lstrip().startswith("=") else body.lstrip())
        if not m or not (m.group("line") or m.group("path") or m.group("content") is not None):
            raise SaveError("expected-diff line %d is not understood: %r (use N, N = text, = text, key PATH "
                            "or key PATH = value)" % (n, body))
        line = int(m.group("line")) if m.group("line") else None
        if line is not None and line < 1:
            raise SaveError("expected-diff line %d: line numbers start at 1" % n)
        out.append(Expectation(n, body, line, m.group("path"), m.group("content")))
    return out


# ---- differences ---------------------------------------------------------------------------------------
class Change(NamedTuple):
    line: Optional[int]       # 1-based line in ORIGINAL (None: exists only in EDITED)
    path: Optional[str]
    old: Optional[str]
    new: Optional[str]
    note: str = ""
    new_value: Optional[str] = None   # the parsed new value (for `key PATH = value` and `= value`)


_UNKEYED = "(unkeyed)"


def value_map(text: str) -> Dict[str, Tuple[int, str]]:
    """path -> (1-based line, normalised value) for every non-blank, non-comment line, using the existing
    `_yamltext.scan` path tracker. Quotes are removed with `_yamltext.unquote` and trailing spaces ignored,
    so `key: 'x'`, `key: "x"` and `key: x` are the same value. Lines that are not `key: value` (bare list
    scalars and anything else) are kept, in order, under `(unkeyed)`. Repeats get `[n]`."""
    lines = _yamltext.split_lines(text)
    recs = {r.idx: r for r in _yamltext.scan(lines)}
    seen: Dict[str, int] = {}
    out: Dict[str, Tuple[int, str]] = {}
    for idx, line in enumerate(lines):
        rec = recs.get(idx)
        if rec is not None:
            base, value = "/".join(rec.path + (rec.key,)), _yamltext.unquote(rec.value)
        else:
            body = line.rstrip("\r\n").strip()
            if not body or body.startswith("#"):
                continue
            base = _UNKEYED
            value = _yamltext.unquote(body[1:]) if body.startswith("-") else body
        n = seen.get(base, 0)
        seen[base] = n + 1
        out[base if n == 0 else "%s[%d]" % (base, n)] = (idx + 1, value)
    return out


def line_changes(before: str, after: str) -> List[Change]:
    """Byte-exact line differences, via the existing `_yamltext.changed_lines` (line numbers are ORIGINAL's)."""
    paths = {ln: p for p, (ln, _v) in value_map(before).items()}
    new_values = {ln: v for _p, (ln, v) in value_map(after).items()}
    a, b = _yamltext.split_lines(before), _yamltext.split_lines(after)
    same_count = len(a) == len(b)
    out: List[Change] = []
    for n, old, new in _yamltext.changed_lines(before, after):
        note = ""
        if same_count and old == new:
            note = "line endings differ: %r -> %r" % (a[n - 1][len(old):], b[n - 1][len(new):])
        out.append(Change(n, paths.get(n), old, new, note, new_values.get(n) if same_count else None))
    return out


def value_changes(before: str, after: str) -> List[Change]:
    """Differences between parsed values (path -> value); formatting is ignored."""
    ma, mb = value_map(before), value_map(after)
    out: List[Change] = []
    for path in list(ma) + [p for p in mb if p not in ma]:
        va, vb = ma.get(path), mb.get(path)
        if va is not None and vb is not None and va[1] == vb[1]:
            continue
        out.append(Change(va[0] if va else None, path, va[1] if va else None, vb[1] if vb else None,
                          "" if va and vb else ("removed" if va else "added (EDITED line %d)" % vb[0]),
                          vb[1] if vb else None))
    return out


def _matches(e: Expectation, c: Change) -> bool:
    if e.line is not None and c.line != e.line:
        return False
    if e.path is not None and c.path != e.path:
        return False
    if e.content is not None:
        want = e.content.strip()
        if not ((c.new is not None and (e.content == c.new or want == c.new.strip()))
                or (c.new_value is not None and want == c.new_value)):
            return False
    return True


def assign(changes: Sequence[Change], plan: Sequence[Expectation]) -> Dict[int, int]:
    """Maximum one-to-one matching change index -> plan index (augmenting paths), so an ambiguous `= text`
    line can never steal the change a more specific line needed."""
    owner: Dict[int, int] = {}            # plan index -> change index

    def place(ci: int, seen: Set[int]) -> bool:
        for ei, e in enumerate(plan):
            if ei in seen or not _matches(e, changes[ci]):
                continue
            seen.add(ei)
            if ei not in owner or place(owner[ei], seen):
                owner[ei] = ci
                return True
        return False

    for ci in range(len(changes)):
        place(ci, set())
    return {ci: ei for ei, ci in owner.items()}


def _describe(c: Change) -> List[str]:
    where = ("line %d" % c.line) if c.line is not None else "new line"
    head = "%s%s%s" % (where, ("  (%s)" % c.path) if c.path else "", ("  [%s]" % c.note) if c.note else "")
    return [head, "      - %r" % (c.old,) if c.old is not None else "      - (absent)",
            "      + %r" % (c.new,) if c.new is not None else "      + (absent)"]


# ---- roundtrip -----------------------------------------------------------------------------------------
class RoundtripResult(NamedTuple):
    ok: bool
    report: List[str]


def roundtrip(original: bytes, edited: bytes, key: bytes, platform: str, plan: Sequence[Expectation],
              allow_reserialize: bool = False) -> RoundtripResult:
    report: List[str] = []
    ro, re_ = oracle(original, key, platform), oracle(edited, key, platform)
    report += render_oracle("ORIGINAL", ro) + render_oracle("EDITED", re_)
    if not (ro.ok and re_.ok):
        report.append("ROUNDTRIP FAIL: a file does not pass the oracle; nothing was compared")
        return RoundtripResult(False, report)
    a, b = ro.plaintext.decode("utf-8"), re_.plaintext.decode("utf-8")
    ok = True

    report.append("== diff")
    if allow_reserialize:
        byte_diff = len(_yamltext.changed_lines(a, b))
        report.append("   mode: PARSED VALUES (--allow-reserialize). %d line(s) differ as bytes; formatting is "
                      "ignored and values are compared path by path. This is weaker than byte mode." % byte_diff)
        changes = value_changes(a, b)
    else:
        report.append("   mode: BYTES (line-exact). Every line not listed in the plan must be byte-identical.")
        changes = line_changes(a, b)
    match = assign(changes, plan)
    unexpected = [c for i, c in enumerate(changes) if i not in match]
    used = set(match.values())
    missing = [e for i, e in enumerate(plan) if i not in used]
    for i, c in enumerate(changes):
        if i in match:
            d = _describe(c)
            report.append("   PASS  planned   %s   <- plan line %d" % (d[0], plan[match[i]].plan_line))
            report += ["   " + x for x in d[1:]]
    for c in unexpected:
        d = _describe(c)
        report.append("   FAIL  UNEXPECTED  %s" % d[0])
        report += ["   " + x for x in d[1:]]
    for e in missing:
        report.append("   FAIL  PLANNED BUT NOT FOUND  plan line %d: %r" % (e.plan_line, e.source))
    ok = ok and not unexpected and not missing
    report.append("   %d change(s), %d planned, %d unexpected, %d planned edit(s) not found"
                  % (len(changes), len(changes) - len(unexpected), len(unexpected), len(missing)))

    if not allow_reserialize:
        la, lb = _yamltext.split_lines(a), _yamltext.split_lines(b)
        if len(la) == len(lb):
            listed = {c.line for c in changes}
            spliced = "".join(lb[i] if (i + 1) in listed else la[i] for i in range(len(la)))
            same = spliced == b
            report.append("   %s  every unlisted line is byte-identical (ORIGINAL with only the changed lines "
                          "swapped in == EDITED)" % _status(same))
            ok = ok and same
        else:
            report.append("   INFO  line count changed %d -> %d; inserted/removed lines are listed above as "
                          "changes and each needs its own plan line" % (len(la), len(lb)))

    report.append("== re-encrypt EDITED plaintext with _container.encrypt")
    blob = _container.encrypt(re_.plaintext, key, platform)
    rr = oracle(blob, key, platform)
    report += render_oracle("re-encrypted EDITED", rr)
    back = rr.ok and rr.plaintext == re_.plaintext
    report.append("   %s  re-encrypted EDITED plaintext passes the oracle and decrypts to the same bytes" % _status(back))
    report.append("   INFO  re-encrypted bytes %s EDITED.sav (compression level and padding may legitimately "
                  "differ; the plaintext is what counts)" % ("are identical to" if blob == edited else "differ from"))
    ok = ok and back
    report.append("ROUNDTRIP %s" % ("PASS" if ok else "FAIL"))
    return RoundtripResult(ok, report)


# ---- CLI -----------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--key-file", required=True,
                        help="file holding YOUR key: 64 hex digits or 32 raw bytes (for --platform pc, the PC "
                             "base key). It is never printed. No key ships with this tool.")
    common.add_argument("--platform", choices=PLATFORMS, default="ps5", help="save platform (default ps5)")
    common.add_argument("--steam-id", help="Steam ID, needed with --platform pc")
    p = argparse.ArgumentParser(prog="python -m bl4forge.tools.save_verify",
                                description="Prove a save edit changed exactly what was planned. Offline; "
                                            "reads only the files you name; writes nothing.")
    sub = p.add_subparsers(dest="mode", metavar="{oracle,roundtrip}")
    sub.required = True
    o = sub.add_parser("oracle", parents=[common], help="report every container check on one save")
    o.add_argument("save", help="encrypted save file")
    r = sub.add_parser("roundtrip", parents=[common], help="prove EDITED differs from ORIGINAL only as planned")
    r.add_argument("original", help="the untouched save")
    r.add_argument("edited", help="the edited save")
    r.add_argument("--expected-diff", required=True, metavar="PLAN",
                   help="planned edits, one per line (an empty file means: nothing may change)")
    r.add_argument("--allow-reserialize", action="store_true",
                   help="compare parsed values instead of bytes (tolerates the game's re-serialisation)")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        key = resolve_key(args.key_file, args.platform, args.steam_id)
        if args.mode == "oracle":
            result = oracle(_read_file(args.save, "save"), key, args.platform)
            print("\n".join(render_oracle(args.save, result)))
            return EXIT_OK if result.ok else EXIT_MISMATCH
        plan_bytes = _read_file(args.expected_diff, "expected-diff file")
        try:
            plan = parse_plan(plan_bytes.decode("utf-8"))
        except UnicodeDecodeError:
            raise SaveError("expected-diff file %s is not UTF-8 text" % args.expected_diff) from None
        rt = roundtrip(_read_file(args.original, "save"), _read_file(args.edited, "save"), key, args.platform,
                       plan, args.allow_reserialize)
        print("\n".join(rt.report))
        return EXIT_OK if rt.ok else EXIT_MISMATCH
    except SaveError as ex:
        print("error: %s" % ex, file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
