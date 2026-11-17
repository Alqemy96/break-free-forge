"""save_fix: verify, and recompute after an edit, the integrity checksum inside a save file, per game.

Borderlands 4 has no integrity field in its YAML, so BL4 saves need nothing from this tool. Most other
games do: edit the decrypted save and the stored checksum no longer matches, and the game rejects it.
This tool holds the generic machinery plus a registry (`FIXERS`) of per-game definitions. It ships ONE
entry, `demo`, a FICTIONAL format that exists only to document the pattern; it is not a real game and no
real game definition, key or seed is shipped here.

    python -m bl4forge.tools.save_fix list
    python -m bl4forge.tools.save_fix verify <file> --game <name> [--key-file <file>]
    python -m bl4forge.tools.save_fix fix    <file> --game <name> [--key-file <file>] [-o <out>] [--overwrite]

Adding a game = adding one `ChecksumFixer` to `FIXERS`:
  name, algorithm (a `checksums.get()` name, e.g. 'crc32', 'joaat:0x...'), locator (where the stored
  value lives: `Locator.fixed(off)`, `Locator.tail(n)` or `Locator.struct(field, base=.., base_ptr=..)`),
  byteorder, coverage (which bytes are hashed and how the checksum field itself is treated), the
  encryption layer ('plain', 'aes256-ecb-pkcs7', 'aes256-ecb-raw') and an optional magic prefix.
  `verify()` and `fix()` work on the PLAINTEXT; a game with an odd scheme (two checksums, a checksum
  of a checksum, ...) subclasses ChecksumFixer and overrides that pair.

Exit codes: 0 = checksum valid / fix written, 1 = checksum mismatch (verify), 2 = error.

DISCLOSURE (what this code does)
  Reads: the save file named on the command line and, for an encrypted layer, the --key-file (32 raw
  bytes or 64 hex digits; held in memory only and never printed, logged or written). Writes: `fix` writes
  ONLY a new file at --out (default '<name>.fixed<ext>' beside the input); the input is never opened for
  writing, writing onto the input is refused, and an existing destination is refused unless --overwrite.
  Network: none. Risk: a wrong game definition produces a file the game rejects or misreads; keep the
  original and test on a copy.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass, field as dc_field
from typing import Dict, List, Optional, Sequence

from ..core.errors import SaveError
from ..modules import checksums
from ..modules.save._aes import ecb_decrypt, ecb_encrypt
from ..modules.save._container import pkcs7_pad, pkcs7_unpad

BYTEORDERS = ("little", "big")
LAYERS = ("plain", "aes256-ecb-pkcs7", "aes256-ecb-raw")
FIELD_MODES = ("zero", "skip")


# ---------------------------------------------------------------- where the checksum lives
@dataclass(frozen=True)
class Locator:
    """Where the stored checksum sits in the plaintext.

    kind 'fixed'  : at `offset` bytes from the start of the file.
    kind 'tail'   : the last `n` bytes of the file (`n` must equal the algorithm's size).
    kind 'struct' : `field` bytes into a struct. The struct starts at `base`, or, when `base_ptr` is set,
                    at the u32 read from offset `base_ptr` (in the entry's byte order).
    """

    kind: str
    offset: int = 0
    n: int = 0
    field: int = 0
    base: int = 0
    base_ptr: Optional[int] = None

    @classmethod
    def fixed(cls, offset: int) -> "Locator":
        return cls("fixed", offset=offset)

    @classmethod
    def tail(cls, n: int) -> "Locator":
        return cls("tail", n=n)

    @classmethod
    def struct(cls, field: int, base: int = 0, base_ptr: Optional[int] = None) -> "Locator":
        return cls("struct", field=field, base=base, base_ptr=base_ptr)

    def resolve(self, data: bytes, size: int, byteorder: str) -> int:
        """File offset of the `size`-byte checksum field in `data`."""
        if self.kind == "fixed":
            off = self.offset
        elif self.kind == "tail":
            if self.n != size:
                raise SaveError("tail locator covers %d bytes but the checksum is %d bytes" % (self.n, size))
            off = len(data) - self.n
        elif self.kind == "struct":
            if self.base_ptr is None:
                base = self.base
            else:
                if not 0 <= self.base_ptr <= len(data) - 4:
                    raise SaveError("struct pointer at %d is outside the %d-byte file" % (self.base_ptr, len(data)))
                base = int.from_bytes(data[self.base_ptr:self.base_ptr + 4], byteorder)
            off = base + self.field
        else:
            raise SaveError("unknown locator kind %r" % self.kind)
        if off < 0 or off + size > len(data):
            raise SaveError("checksum field %d..%d is outside the %d-byte file" % (off, off + size, len(data)))
        return off


@dataclass(frozen=True)
class Coverage:
    """Which bytes are hashed. `start`/`end` are file offsets (end None = end of file; negative values
    count back from the end). When the checksum field falls inside the range, `field` says what to do:
    'zero' hashes it as zero bytes, 'skip' leaves it out of the hashed data."""

    start: int = 0
    end: Optional[int] = None
    field: str = "zero"

    def covered(self, data: bytes, off: int, size: int) -> bytes:
        n = len(data)
        s = self.start if self.start >= 0 else n + self.start
        e = n if self.end is None else (self.end if self.end >= 0 else n + self.end)
        if not 0 <= s <= e <= n:
            raise SaveError("coverage %d..%d does not fit the %d-byte file" % (s, e, n))
        lo, hi = max(s, off), min(e, off + size)
        if lo >= hi:
            return bytes(data[s:e])
        if self.field == "zero":
            return bytes(data[s:lo]) + bytes(hi - lo) + bytes(data[hi:e])
        if self.field == "skip":
            return bytes(data[s:lo]) + bytes(data[hi:e])
        raise SaveError("unknown coverage field mode %r (expected one of %s)" % (self.field, ", ".join(FIELD_MODES)))


# ---------------------------------------------------------------- the per-game definition
@dataclass(frozen=True)
class CheckResult:
    """Outcome of verify(): where the field is, what is stored, what it should be."""

    ok: bool
    offset: int
    stored: bytes
    computed: bytes


@dataclass(frozen=True)
class ChecksumFixer:
    """One game's checksum rule. verify()/fix() take and return PLAINTEXT bytes."""

    name: str
    title: str
    algorithm: str
    locator: Locator
    byteorder: str = "little"
    coverage: Coverage = dc_field(default_factory=Coverage)
    layer: str = "plain"
    magic: bytes = b""
    demo: bool = False
    notes: str = ""

    def algo(self) -> checksums.Algorithm:
        try:
            return checksums.get(self.algorithm)
        except ValueError as ex:
            raise SaveError("%s: %s" % (self.name, ex)) from None

    def _check(self, plain: bytes) -> None:
        if self.byteorder not in BYTEORDERS:
            raise SaveError("%s: byteorder must be 'little' or 'big', not %r" % (self.name, self.byteorder))
        if self.magic and not bytes(plain).startswith(self.magic):
            raise SaveError("%s: file does not start with the expected magic; wrong --game, wrong key, "
                            "or not a save of this format" % self.name)

    def verify(self, plain: bytes) -> CheckResult:
        """Recompute the checksum and compare it with the stored one."""
        self._check(plain)
        algo = self.algo()
        off = self.locator.resolve(plain, algo.size, self.byteorder)
        stored = bytes(plain[off:off + algo.size])
        computed = algo.digest(self.coverage.covered(plain, off, algo.size), self.byteorder)
        return CheckResult(stored == computed, off, stored, computed)

    def fix(self, plain: bytes) -> bytes:
        """The plaintext with the stored checksum replaced by the recomputed one; nothing else changes."""
        res = self.verify(plain)
        return bytes(plain[:res.offset]) + res.computed + bytes(plain[res.offset + len(res.computed):])


# ---------------------------------------------------------------- the encryption layer
def open_layer(data: bytes, layer: str, key: Optional[bytes]) -> bytes:
    """File bytes -> plaintext. Strict: a wrong key on a padded layer fails here instead of later."""
    if layer == "plain":
        return bytes(data)
    if layer not in LAYERS:
        raise SaveError("unknown layer %r (expected one of %s)" % (layer, ", ".join(LAYERS)))
    if key is None:
        raise SaveError("this game's save is encrypted; pass --key-file")
    raw = ecb_decrypt(key, bytes(data))
    return pkcs7_unpad(raw) if layer == "aes256-ecb-pkcs7" else raw


def close_layer(plain: bytes, layer: str, key: Optional[bytes]) -> bytes:
    """Plaintext -> file bytes, the inverse of open_layer."""
    if layer == "plain":
        return bytes(plain)
    if layer not in LAYERS:
        raise SaveError("unknown layer %r (expected one of %s)" % (layer, ", ".join(LAYERS)))
    if key is None:
        raise SaveError("this game's save is encrypted; pass --key-file")
    body = pkcs7_pad(bytes(plain)) if layer == "aes256-ecb-pkcs7" else bytes(plain)
    return ecb_encrypt(key, body)


def read_key_file(path: str) -> bytes:
    """A key file holds exactly 32 raw bytes, or 64 hex digits (whitespace ignored). The key is never
    echoed, not even in error messages."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if len(raw) == 32:
        return raw
    try:
        key = bytes.fromhex("".join(raw.decode("ascii").split()))
    except (UnicodeDecodeError, ValueError):
        raise SaveError("key file must hold 32 raw bytes or 64 hex digits") from None
    if len(key) != 32:
        raise SaveError("key file holds %d bytes; AES-256 needs 32" % len(key))
    return key


# ---------------------------------------------------------------- the registry
DEMO_MAGIC = b"DEMQ"
DEMO_HEADER = 16


def demo_save(body: bytes, version: int = 1, flags: int = 0) -> bytes:
    """Build a valid save of the fictional demo format (DEMO DATA, not a real game).

    Layout, little-endian: 0 magic 'DEMQ' | 4 u16 version | 6 u16 flags | 8 u32 body length |
    12 u32 crc32 | 16 body. The crc32 covers the whole file with its own 4 bytes taken as zero.
    """
    header = DEMO_MAGIC + version.to_bytes(2, "little") + flags.to_bytes(2, "little") \
        + len(body).to_bytes(4, "little") + bytes(4)
    return FIXERS["demo"].fix(header + bytes(body))


FIXERS: Dict[str, ChecksumFixer] = {
    "demo": ChecksumFixer(
        name="demo",
        title="DEMO DATA: fictional 'Demo Quest' save format (not a real game)",
        algorithm="crc32",
        locator=Locator.struct(field=12, base=0),
        byteorder="little",
        coverage=Coverage(start=0, end=None, field="zero"),
        layer="plain",
        magic=DEMO_MAGIC,
        demo=True,
        notes="Documents the pattern only. 16-byte header, crc32 of the whole file with the field zeroed.",
    ),
}


def get_fixer(name: str, fixers: Optional[Dict[str, ChecksumFixer]] = None) -> ChecksumFixer:
    table = FIXERS if fixers is None else fixers
    try:
        return table[name]
    except KeyError:
        raise SaveError("no fixer for game %r; known: %s" % (name, ", ".join(sorted(table)) or "(none)")) from None


# ---------------------------------------------------------------- CLI
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _default_out(path: str) -> str:
    stem, ext = os.path.splitext(path)
    return stem + ".fixed" + ext


def _same_file(a: str, b: str) -> bool:
    if os.path.exists(a) and os.path.exists(b):
        return os.path.samefile(a, b)
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _load(args: argparse.Namespace, fixers: Optional[Dict[str, ChecksumFixer]]):
    fixer = get_fixer(args.game, fixers)
    key = read_key_file(args.key_file) if args.key_file else None
    if key is not None and fixer.layer == "plain":
        print("note: %s saves are not encrypted; --key-file ignored" % fixer.name)
        key = None
    with open(args.file, "rb") as fh:
        data = fh.read()
    return fixer, key, data


def _cmd_list(args: argparse.Namespace, fixers: Optional[Dict[str, ChecksumFixer]]) -> int:
    table = FIXERS if fixers is None else fixers
    for name in sorted(table):
        f = table[name]
        print("%-12s %-10s %-6s %-16s %s" % (name, f.algorithm, f.byteorder, f.layer, f.title))
    return 0


def _cmd_verify(args: argparse.Namespace, fixers: Optional[Dict[str, ChecksumFixer]]) -> int:
    fixer, key, data = _load(args, fixers)
    res = fixer.verify(open_layer(data, fixer.layer, key))
    state = "OK" if res.ok else "MISMATCH"
    print("%s: %s checksum at offset %d: stored %s, computed %s"
          % (state, fixer.algorithm, res.offset, res.stored.hex(), res.computed.hex()))
    return 0 if res.ok else 1


def _cmd_fix(args: argparse.Namespace, fixers: Optional[Dict[str, ChecksumFixer]]) -> int:
    fixer, key, data = _load(args, fixers)
    out = args.out or _default_out(args.file)
    if _same_file(out, args.file):
        raise SaveError("refusing to write onto the input file; choose another --out")
    plain = open_layer(data, fixer.layer, key)
    before = fixer.verify(plain)
    fixed_plain = fixer.fix(plain)
    new = close_layer(fixed_plain, fixer.layer, key)
    after = fixer.verify(open_layer(new, fixer.layer, key))       # round-trip gate before anything is written
    if not after.ok:
        raise SaveError("internal check failed: the re-wrapped file does not verify; nothing written")
    with open(out, "wb" if args.overwrite else "xb") as fh:
        fh.write(new)
    if before.ok:
        print("checksum was already valid; wrote an identical-content copy")
    else:
        print("fixed %s at offset %d: %s -> %s" % (fixer.algorithm, before.offset, before.stored.hex(), after.computed.hex()))
    print("input  %s sha256 %s" % (args.file, _sha(data)))
    print("output %s sha256 %s" % (out, _sha(new)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m bl4forge.tools.save_fix",
                                description="Verify or recompute the integrity checksum inside a save file.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list the known game definitions")
    for name, text in (("verify", "check the stored checksum"), ("fix", "write a copy with the checksum recomputed")):
        sp = sub.add_parser(name, help=text)
        sp.add_argument("file", help="the save file (never modified)")
        sp.add_argument("--game", required=True, help="game definition name (see 'list')")
        sp.add_argument("--key-file", help="32 raw bytes or 64 hex digits; needed only for encrypted layers")
        if name == "fix":
            sp.add_argument("-o", "--out", help="output path (default: <file>.fixed<ext>)")
            sp.add_argument("--overwrite", action="store_true", help="replace an existing --out file")
    return p


def main(argv: Optional[Sequence[str]] = None, fixers: Optional[Dict[str, ChecksumFixer]] = None) -> int:
    """CLI entry point. `fixers` replaces the registry (tests use it); the CLI uses FIXERS."""
    args = build_parser().parse_args(argv)
    handler = {"list": _cmd_list, "verify": _cmd_verify, "fix": _cmd_fix}[args.cmd]
    try:
        return handler(args, fixers)
    except FileExistsError:
        print("error: %s already exists; pass --overwrite or choose another --out" % (args.out or _default_out(args.file)),
              file=sys.stderr)
        return 2
    except (SaveError, OSError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 2


__all__: List[str] = ["Locator", "Coverage", "CheckResult", "ChecksumFixer", "FIXERS", "demo_save",
                      "get_fixer", "open_layer", "close_layer", "read_key_file", "main"]


if __name__ == "__main__":
    sys.exit(main())
