"""save_id: triage a save file - say what layers sit between you and plaintext BEFORE any key scan.

    python -m bl4forge.tools.save_id <file> [--json]
    python -m bl4forge.tools.save_id --self-test

Six checks run in order, each reported PASS / FAIL / INFO with one line of explanation:
  1. size + 16-byte block alignment     (aligned => AES-ECB is possible; not aligned => it is not raw ECB)
  2. sampled Shannon entropy            (<6.0 bits/byte: text-like; >7.5: encrypted OR compressed)
  3. compression magic                  (zlib / gzip / zstd / lz4 frame, at offset 0 and in the first 4 KiB;
                                         zlib and gzip are confirmed by a bounded trial inflate)
  4. console / container signatures     (PS3 PARAM.PFD / PARAM.SFO, PS4 sealed key, zip, 7z, sqlite, GVAS...)
  5. printable-string summary           (YAML-ish / JSON-ish flags)
  6. verdict                            (the most likely layer stack, with a machine-readable `kind`)

What this tool can NOT do: prove encryption. High entropy + block alignment + no magic is CONSISTENT with
"AES-256-ECB over zlib + trailer" (the BL4 PS5 shape), but compressed data with an unknown header looks the
same. Only a successful decrypt with the right key proves it. This tool never takes, guesses, scans for or
prints a key; it reads the one file you name and nothing else (plus the names of its sibling files).


DISCLOSURE (what this code does)
  Reads: the file given on the command line (sampled, at most ~1 MiB for entropy plus the first 64 KiB for
  strings, plus a bounded trial inflate) and the NAMES of files in the same directory. --self-test writes
  synthetic fixtures to a temporary directory and deletes it. Writes: nothing else. Network: none.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import struct
import sys
import tempfile
import zlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

BLOCK = 16
CHUNK = 64 * 1024                  # entropy sample chunk
MAX_CHUNKS = 16                    # at most 1 MiB is read for the entropy estimate
HEAD = 64 * 1024                   # bytes read for strings / text detection / magic scan
MAGIC_SCAN = 4096                  # compression magic is looked for at every offset below this
INFLATE_LIMIT = 64 * 1024 * 1024   # trial inflate stops here (zip-bomb guard)
LOW_ENTROPY = 6.0
HIGH_ENTROPY = 7.5
MIN_RUN = 6                        # printable run length counted as a "string"

PASS, FAIL, INFO = "PASS", "FAIL", "INFO"

# zlib: CMF 0x78 (deflate, 32K window) + one of the four standard FLG bytes. Any (CMF*256+FLG) % 31 == 0
# pair is a legal header; these four are what zlib itself writes (levels 0-1 / 2-5 / 6 / 7-9).
ZLIB_FLG = {0x01: "fastest", 0x5E: "fast", 0x9C: "default", 0xDA: "best"}
GZIP_MAGIC = b"\x1f\x8b"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
LZ4_FRAME_MAGIC = b"\x04\x22\x4d\x18"

# (name, offset, magic, note). Offsets are where the magic must sit. Entries marked UNVERIFIED in the note
# come from public format write-ups and were not checked against a real file from that console.
SIGNATURES: Tuple[Tuple[str, int, bytes, str], ...] = (
    ("PS3 PARAM.PFD", 0, b"\x00\x00\x00\x00PFDB", "PS3 save protection table (UNVERIFIED magic)"),
    ("PS3/PS4 PARAM.SFO", 0, b"\x00PSF", "Sony system-file-object metadata, not the save body"),
    ("PS4 sealed key", 0, b"pfsSKKey", "PS4 savedata sealed key file (UNVERIFIED magic)"),
    ("Unreal GVAS SaveGame", 0, b"GVAS", "Unreal Engine USaveGame header"),
    ("zip archive", 0, b"PK\x03\x04", "zip container"),
    ("7z archive", 0, b"7z\xbc\xaf\x27\x1c", "7-Zip container"),
    ("rar archive", 0, b"Rar!\x1a\x07", "RAR container"),
    ("xz stream", 0, b"\xfd7zXZ\x00", "xz/LZMA2 container"),
    ("bzip2 stream", 0, b"BZh", "bzip2 stream (weak 3-byte magic)"),
    ("SQLite database", 0, b"SQLite format 3\x00", "SQLite file"),
    ("UTF-8 BOM", 0, b"\xef\xbb\xbf", "text with a UTF-8 byte-order mark"),
    ("UTF-16 LE BOM", 0, b"\xff\xfe", "UTF-16 LE text"),
    ("UTF-16 BE BOM", 0, b"\xfe\xff", "UTF-16 BE text"),
)
# Sibling file names that betray a console savedata folder.
SIBLING_HINTS: Tuple[Tuple[str, str], ...] = (
    ("PARAM.PFD", "PS3 savedata folder (PFD-protected files)"),
    ("PARAM.SFO", "Sony savedata folder (PS3/PS4/PS5 metadata file present)"),
    ("sce_sys", "PS4/PS5 savedata folder layout (sce_sys/)"),
    ("sealedkey", "PS4 encrypted savedata image + sealed key (UNVERIFIED naming)"),
)
SIBLING_PREFIXES: Tuple[Tuple[str, str], ...] = (
    ("sdimg_", "PS4 encrypted savedata image (sdimg_*) (UNVERIFIED naming)"),
)

_YAML_LINE = re.compile(r"^\s*(?:-\s+)?[A-Za-z_][\w.\-]*:(?:\s|$)")
_JSON_KEY = re.compile(r'"[^"\\\n]{1,64}"\s*:')
_RUN = re.compile(rb"[\x20-\x7e]{%d,}" % MIN_RUN)


# ---------------------------------------------------------------------------------------------- data
@dataclass
class Check:
    id: str
    status: str            # PASS / FAIL / INFO
    title: str
    detail: str
    data: Dict[str, object] = field(default_factory=dict)


@dataclass
class Verdict:
    kind: str              # machine-readable, stable: see VERDICT_KINDS
    stack: str             # human-readable layer stack, outermost first
    confidence: str        # "confirmed" / "consistent" / "weak" / "none"
    notes: List[str] = field(default_factory=list)


VERDICT_KINDS = (
    "empty", "plaintext_yaml", "plaintext_json", "plaintext_text",
    "zlib_trailer_ps5", "zlib_trailer_pc", "zlib", "gzip", "zstd", "lz4",
    "container", "aes_ecb_candidate", "high_entropy_unaligned", "unknown",
)


@dataclass
class Report:
    path: str
    size: int
    checks: List[Check]
    verdict: Verdict

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------------------------- reading
def _read_samples(path: str, size: int) -> Tuple[bytes, List[bytes]]:
    """(head, entropy chunks). The whole file is read when it is small; otherwise up to MAX_CHUNKS chunks
    spread evenly across it (always including the first and the last)."""
    with open(path, "rb") as fh:
        if size <= CHUNK * MAX_CHUNKS:
            whole = fh.read()
            chunks = [whole[i:i + CHUNK] for i in range(0, len(whole), CHUNK)] or [b""]
            return whole[:HEAD], chunks
        head = fh.read(HEAD)
        step = (size - CHUNK) / (MAX_CHUNKS - 1)
        chunks = []
        for i in range(MAX_CHUNKS):
            fh.seek(int(i * step))
            chunks.append(fh.read(CHUNK))
        return head, chunks


def _read_all_bounded(path: str, limit: int) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(limit)


# ---------------------------------------------------------------------------------------------- 1 size
def check_size(size: int) -> Check:
    rem = size % BLOCK
    data = {"size": size, "blocks": size // BLOCK, "remainder": rem, "aligned": size > 0 and rem == 0}
    if size == 0:
        return Check("size", FAIL, "size / block alignment", "file is empty", data)
    if rem == 0:
        return Check("size", PASS, "size / block alignment",
                     "%d bytes = %d x 16-byte blocks: AES-ECB candidate" % (size, size // BLOCK), data)
    return Check("size", INFO, "size / block alignment",
                 "%d bytes, %d past a 16-byte boundary: NOT raw AES-ECB/CBC output" % (size, rem), data)


# ---------------------------------------------------------------------------------------------- 2 entropy
def shannon(data: bytes) -> float:
    """Shannon entropy in bits per byte (0.0 for empty input)."""
    n = len(data)
    if not n:
        return 0.0
    return -sum((c / n) * math.log2(c / n) for c in Counter(data).values())


def check_entropy(chunks: Sequence[bytes]) -> Check:
    total = Counter()
    per = []
    n = 0
    for c in chunks:
        if c:
            total.update(c)
            n += len(c)
            per.append(shannon(c))
    if not n:
        return Check("entropy", INFO, "entropy (sampled)", "nothing to measure", {"bits_per_byte": 0.0})
    h = -sum((v / n) * math.log2(v / n) for v in total.values())
    data = {"bits_per_byte": round(h, 4), "sampled_bytes": n, "chunks": len(per),
            "chunk_min": round(min(per), 4), "chunk_max": round(max(per), 4)}
    small = " (sample < 1 KiB: estimate is biased low)" if n < 1024 else ""
    if h > HIGH_ENTROPY:
        return Check("entropy", INFO, "entropy (sampled)",
                     "%.3f bits/byte: encrypted OR compressed (entropy alone cannot tell which)%s" % (h, small), data)
    if h < LOW_ENTROPY:
        return Check("entropy", INFO, "entropy (sampled)",
                     "%.3f bits/byte: structured/plain data, not ciphertext%s" % (h, small), data)
    return Check("entropy", INFO, "entropy (sampled)",
                 "%.3f bits/byte: mixed - partly compressed, binary records, or a header + payload%s" % (h, small),
                 data)


# ---------------------------------------------------------------------------------------------- 3 compression
def _zlib_header_ok(b0: int, b1: int) -> bool:
    return (b0 & 0x0F) == 8 and (b0 >> 4) <= 7 and ((b0 << 8) | b1) % 31 == 0 and not (b1 & 0x20)


def trial_inflate(data: bytes, wbits: int) -> Optional[Dict[str, object]]:
    """Inflate `data` (zlib wbits=15, gzip wbits=31) up to INFLATE_LIMIT. Returns facts or None if the
    bytes are not a valid stream start. A stream that ends cleanly reports its trailing bytes."""
    d = zlib.decompressobj(wbits)
    try:
        out = d.decompress(data, INFLATE_LIMIT)
    except zlib.error:
        return None
    if not d.eof and len(out) < 32:
        return None               # a few lucky bytes, not a stream
    return {"complete": d.eof, "out_len": len(out), "capped": len(out) >= INFLATE_LIMIT,
            "trailer": d.unused_data if d.eof else b"", "_out": out}


def bl4_trailer(trailer: bytes, out_len: int, payload: Optional[bytes] = None) -> Optional[str]:
    """'ps5' if trailer == uint32_LE(len), 'pc' if trailer == adler32 + uint32_LE(len), else None.
    The PC adler32 is checked when the full inflated `payload` is passed."""
    n = out_len & 0xFFFFFFFF
    if len(trailer) == 4 and struct.unpack("<I", trailer)[0] == n:
        return "ps5"
    if len(trailer) == 8:
        adler, length = struct.unpack("<II", trailer)
        if length == n and (payload is None or adler == zlib.adler32(payload)):
            return "pc"
    return None


def check_compression(path: str, head: bytes) -> Check:
    hits: List[Dict[str, object]] = []
    scan = head[:MAGIC_SCAN + 4]
    body: Optional[bytes] = None
    seen = set()  # formats already confirmed: later headers are inside that stream
    for off in range(0, max(0, min(len(scan) - 1, MAGIC_SCAN))):
        b0, b1 = scan[off], scan[off + 1]
        if b0 == 0x78 and "zlib" not in seen and _zlib_header_ok(b0, b1):
            if body is None:
                body = _read_all_bounded(path, INFLATE_LIMIT)
            res = trial_inflate(memoryview(body)[off:], 15)
            if res:
                hits.append({"format": "zlib", "offset": off, "level": ZLIB_FLG.get(b1, "nonstandard FLG"),
                             "complete": res["complete"], "out_len": res["out_len"],
                             "trailer_len": len(res["trailer"]),
                             "bl4_trailer": (bl4_trailer(res["trailer"], len(res["_out"]), res["_out"])
                                             if res["complete"] and not res["capped"] else None),
                             "_head": res["_out"][:HEAD]})
                seen.add(hits[-1]["format"])
        elif "gzip" not in seen and scan[off:off + 2] == GZIP_MAGIC and off + 2 < len(scan) and scan[off + 2] == 8:
            if body is None:
                body = _read_all_bounded(path, INFLATE_LIMIT)
            res = trial_inflate(memoryview(body)[off:], 31)
            if res:
                hits.append({"format": "gzip", "offset": off, "complete": res["complete"],
                             "out_len": res["out_len"], "trailer_len": len(res["trailer"]),
                             "_head": res["_out"][:HEAD]})
                seen.add(hits[-1]["format"])
        elif scan[off:off + 4] == ZSTD_MAGIC:
            hits.append({"format": "zstd", "offset": off, "complete": None,
                         "note": "magic only; Python's stdlib (<3.14) cannot decompress zstd"})
        elif scan[off:off + 4] == LZ4_FRAME_MAGIC:
            hits.append({"format": "lz4", "offset": off, "complete": None,
                         "note": "magic only; Python's stdlib cannot decompress lz4"})
    # Keep the earliest hit per format (later zlib hits inside one stream are noise).
    first: Dict[str, Dict[str, object]] = {}
    for h in hits:
        first.setdefault(str(h["format"]), h)
    found = sorted(first.values(), key=lambda h: int(h["offset"]))
    public = [{k: v for k, v in h.items() if not k.startswith("_")} for h in found]
    data: Dict[str, object] = {"streams": public}
    if found:
        data["_inner_head"] = found[0].get("_head", b"")
    if not found:
        return Check("compression", INFO, "compression magic",
                     "no zlib/gzip/zstd/lz4 stream in the first %d bytes" % MAGIC_SCAN, data)
    h = found[0]
    where = "at offset 0" if h["offset"] == 0 else "at offset %d (after a %d-byte header?)" % (h["offset"], h["offset"])
    if h["format"] in ("zlib", "gzip"):
        state = "complete stream" if h["complete"] else "valid start, stream not finished in the bytes read"
        extra = ""
        if h.get("bl4_trailer") == "ps5":
            extra = " + 4-byte uint32_LE length trailer (BL4 PS5 inner layer)"
        elif h.get("bl4_trailer") == "pc":
            extra = " + adler32/length trailer (BL4 PC inner layer)"
        elif h["complete"] and h["trailer_len"]:
            extra = " + %d unexplained trailing bytes" % h["trailer_len"]
        return Check("compression", PASS, "compression magic",
                     "%s %s: %s, inflates to %d bytes%s" % (h["format"], where, state, h["out_len"], extra), data)
    return Check("compression", PASS, "compression magic", "%s frame magic %s (%s)" % (h["format"], where, h["note"]),
                 data)


# ---------------------------------------------------------------------------------------------- 4 console
def check_console(path: str, head: bytes) -> Check:
    hits = [{"name": n, "offset": o, "note": note} for (n, o, magic, note) in SIGNATURES
            if head[o:o + len(magic)] == magic]
    siblings: List[Dict[str, str]] = []
    folder = os.path.dirname(os.path.abspath(path))
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    lower = {n.lower(): n for n in names}
    for name, note in SIBLING_HINTS:
        if name.lower() in lower:
            siblings.append({"sibling": lower[name.lower()], "note": note})
    for prefix, note in SIBLING_PREFIXES:
        for n in names:
            if n.lower().startswith(prefix):
                siblings.append({"sibling": n, "note": note})
                break
    data = {"signatures": hits, "siblings": siblings}
    if hits:
        h = hits[0]
        return Check("console", PASS, "console / container layer",
                     "%s magic at offset %d: %s" % (h["name"], h["offset"], h["note"]), data)
    if siblings:
        return Check("console", INFO, "console / container layer",
                     "no magic in the file; folder hints: " + "; ".join(s["note"] for s in siblings), data)
    return Check("console", INFO, "console / container layer",
                 "no PS3/PS4/archive/database/GVAS signature (a bare PS5-style blob has none)", data)


# ---------------------------------------------------------------------------------------------- 5 strings
def text_profile(data: bytes) -> Dict[str, object]:
    """How text-like `data` is, and whether that text looks like YAML or JSON."""
    if not data:
        return {"printable_ratio": 0.0, "utf8": False, "yaml": False, "json": False, "yaml_score": 0.0}
    try:
        text = data.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError as ex:
        # A sample cut in the middle of a multi-byte character is still UTF-8.
        utf8 = ex.start >= len(data) - 3
        text = data.decode("utf-8", errors="replace")
    good = sum(1 for ch in text if (ch.isprintable() and ch != "\ufffd") or ch in "\t\r\n")
    ratio = good / max(1, len(text))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    yaml_lines = sum(1 for ln in lines if _YAML_LINE.match(ln))
    score = yaml_lines / max(1, len(lines))
    has_doc = any(ln.rstrip() == "---" for ln in lines[:5])
    has_state = any(ln.startswith("state:") for ln in lines[:50])
    stripped = text.lstrip("﻿ \t\r\n")
    json_keys = len(_JSON_KEY.findall(text))
    is_json = False
    if stripped[:1] in ("{", "["):
        try:
            json.loads(text)
            is_json = True
        except ValueError:
            is_json = json_keys >= 3 and json_keys >= len(lines) * 0.3
    is_yaml = not is_json and (has_state or has_doc or (len(lines) >= 3 and score >= 0.5))
    return {"printable_ratio": round(ratio, 4), "utf8": utf8, "yaml": is_yaml, "json": is_json,
            "yaml_score": round(score, 3), "yaml_doc_marker": has_doc, "yaml_state_key": has_state,
            "json_keys": json_keys}


def check_strings(head: bytes, inner_head: Optional[bytes]) -> Check:
    runs = [m.group() for m in _RUN.finditer(head)]
    covered = sum(len(r) for r in runs)
    longest = sorted(set(runs), key=len, reverse=True)[:5]
    common = [r for r, _ in Counter(runs).most_common(5)]
    prof = text_profile(head)
    data: Dict[str, object] = {
        "runs": len(runs), "coverage": round(covered / max(1, len(head)), 4),
        "longest": [_show(r) for r in longest], "most_common": [_show(r) for r in common], "text": prof}
    if inner_head:
        data["inner_text"] = text_profile(inner_head)
    flag = ""
    if prof["yaml"]:
        flag = "YAML-ish"
    elif prof["json"]:
        flag = "JSON-ish"
    elif inner_head and data["inner_text"]["yaml"]:
        flag = "decompressed payload is YAML-ish"
    elif inner_head and data["inner_text"]["json"]:
        flag = "decompressed payload is JSON-ish"
    line = "%d printable runs (>=%d chars) cover %.1f%% of the first %d bytes" % (
        len(runs), MIN_RUN, 100.0 * covered / max(1, len(head)), len(head))
    if flag:
        return Check("strings", PASS, "printable strings", line + "; " + flag, data)
    return Check("strings", INFO, "printable strings", line + "; no YAML/JSON structure", data)


def _show(run: bytes, width: int = 60) -> str:
    s = run.decode("ascii", errors="replace")
    return s if len(s) <= width else s[:width - 3] + "..."


# ---------------------------------------------------------------------------------------------- 6 verdict
def ecb_repeats(head: bytes) -> int:
    """Count repeated 16-byte blocks in the head. ECB leaks equal plaintext blocks as equal ciphertext
    blocks; over compressed data a repeat is very unlikely, so >0 hints at ECB over UNcompressed data."""
    blocks = [head[i:i + BLOCK] for i in range(0, len(head) - len(head) % BLOCK, BLOCK)]
    return len(blocks) - len(set(blocks))


def decide(size: int, checks: Dict[str, Check], head: bytes) -> Verdict:
    if size == 0:
        return Verdict("empty", "empty file", "confirmed", ["nothing to identify"])
    ent = float(checks["entropy"].data.get("bits_per_byte", 0.0))
    aligned = bool(checks["size"].data["aligned"])
    text = checks["strings"].data["text"]
    streams = checks["compression"].data["streams"]
    sigs = checks["console"].data["signatures"]
    notes: List[str] = []

    if text["printable_ratio"] >= 0.95 and text["utf8"]:
        if text["yaml"]:
            return Verdict("plaintext_yaml", "plaintext YAML, no encryption", "confirmed",
                           ["already readable: no key scan needed"])
        if text["json"]:
            return Verdict("plaintext_json", "plaintext JSON, no encryption", "confirmed",
                           ["already readable: not the BL4 YAML format, though"])
        return Verdict("plaintext_text", "plaintext text (not YAML/JSON), no encryption", "confirmed", [])

    if streams and streams[0]["offset"] == 0:
        s = streams[0]
        if s["format"] == "zlib":
            inner = checks["strings"].data.get("inner_text") or {}
            if inner.get("yaml"):
                notes.append("the inflated payload is YAML-ish")
            if s.get("bl4_trailer") == "ps5":
                return Verdict("zlib_trailer_ps5",
                               "zlib + uint32_LE length trailer, NOT encrypted (BL4 PS5 inner layer)", "confirmed",
                               notes + ["a decrypted-but-still-compressed PS5 save body; inflate it, no key needed"])
            if s.get("bl4_trailer") == "pc":
                return Verdict("zlib_trailer_pc",
                               "zlib + adler32/length trailer, NOT encrypted (BL4 PC inner layer)", "confirmed",
                               notes + ["a decrypted-but-still-compressed PC save body; inflate it, no key needed"])
            if s["trailer_len"]:
                notes.append("%d bytes follow the zlib stream: not a BL4 trailer" % s["trailer_len"])
            return Verdict("zlib", "zlib stream, NOT encrypted", "confirmed" if s["complete"] else "consistent", notes)
        if s["format"] == "gzip":
            return Verdict("gzip", "gzip stream, NOT encrypted", "confirmed" if s["complete"] else "consistent", [])
        return Verdict(str(s["format"]), "%s frame, NOT encrypted (stdlib cannot inflate it)" % s["format"],
                       "consistent", ["not the BL4 PS5 shape; needs a third-party %s decoder" % s["format"]])

    if sigs:
        s = sigs[0]
        if streams:
            notes.append("a %s stream starts at offset %d inside it" % (streams[0]["format"], streams[0]["offset"]))
        return Verdict("container", "%s (%s)" % (s["name"], s["note"]), "consistent", notes)

    if streams:
        s = streams[0]
        notes.append("%d-byte header before the stream: inspect it by hand" % s["offset"])
        return Verdict("unknown", "unknown header + %s stream at offset %d" % (s["format"], s["offset"]), "weak", notes)

    if ent > HIGH_ENTROPY and aligned:
        notes += [
            "high entropy, 16-byte aligned, no magic: consistent with AES-ECB, but compressed data with an "
            "unknown header looks the same; only a decrypt with the right key proves it",
            "BL4 PC saves share this outer shape (Steam-ID-derived key, 8-byte footer); bytes alone cannot tell "
            "PS5 from PC - use where the file came from",
        ]
        reps = ecb_repeats(head)
        if reps:
            notes.append("%d repeated 16-byte blocks in the first %d bytes: ECB over UNcompressed data?"
                         % (reps, len(head)))
        return Verdict("aes_ecb_candidate", "AES-256-ECB over zlib+trailer (BL4 PS5 shape)", "consistent", notes)

    if ent > HIGH_ENTROPY:
        return Verdict("high_entropy_unaligned",
                       "high-entropy data NOT on a 16-byte boundary: not raw AES-ECB", "weak",
                       ["could be a stream cipher, AES-CTR/GCM with a tag or IV, compression with a custom header, "
                        "or a truncated/padded copy; check the size against a known-good save"])
    if aligned and ecb_repeats(head):
        notes.append("%d repeated 16-byte blocks: a block cipher in ECB over structured data is possible"
                     % ecb_repeats(head))
    notes.append("entropy %.2f bits/byte with no recognised magic or text" % ent)
    return Verdict("unknown", "unknown - see notes", "none", notes)


# ---------------------------------------------------------------------------------------------- driver
def identify(path: str) -> Report:
    """Run all checks on `path` and return the report. Raises OSError if the file cannot be read."""
    size = os.path.getsize(path)
    head, chunks = _read_samples(path, size)
    c_size = check_size(size)
    c_ent = check_entropy(chunks)
    c_comp = check_compression(path, head)
    inner = c_comp.data.pop("_inner_head", None)
    c_con = check_console(path, head)
    c_str = check_strings(head, inner if isinstance(inner, bytes) and inner else None)
    checks = {c.id: c for c in (c_size, c_ent, c_comp, c_con, c_str)}
    verdict = decide(size, checks, head)
    return Report(path, size, list(checks.values()), verdict)


def render_text(rep: Report) -> str:
    out = ["save_id: %s (%d bytes)" % (rep.path, rep.size), ""]
    for i, c in enumerate(rep.checks, 1):
        out.append("  %d. [%-4s] %-28s %s" % (i, c.status, c.title, c.detail))
    v = rep.verdict
    out += ["", "  6. VERDICT  %s" % v.stack, "     kind=%s  confidence=%s" % (v.kind, v.confidence)]
    out += ["     - %s" % n for n in v.notes]
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------- fixtures
def synthetic_yaml(n_items: int = 300) -> bytes:
    """A fake BL4-shaped YAML document (~26 KB at the default size). Synthetic: no game data."""
    rows = ["state: ", "  char_name: Synthetic", "  class: Char_Example", "  experience: ",
            "  - type: character", "    level: 30", "    points: 123456", "  inventory: ", "    items: ",
            "      backpack: "]
    for i in range(n_items):
        rows += ["        slot_%d: " % i, "          serial: '@FAKE%08d'" % i, "          state_flags: %d" % (i % 3)]
    rows += ["  currencies: ", "    cash: 1000", "    eridium: 50", ""]
    return "\n".join(rows).encode("utf-8")


def _fixture_aes_shaped(rng: random.Random, yaml: bytes) -> Optional[bytes]:
    """The BL4 PS5 container built by the repo's own code with a RANDOM throwaway key (never a game key).
    None when the save cell cannot be imported (the tool itself does not need it)."""
    try:
        from ..modules.save import _container
    except Exception:  # pragma: no cover - only when run outside the package
        return None
    throwaway = bytes(rng.getrandbits(8) for _ in range(32))
    return _container.encrypt(yaml, throwaway, "ps5")


def make_fixtures(folder: str, seed: int = 4) -> Dict[str, Tuple[str, str]]:
    """Write the synthetic fixtures into `folder`. Returns {name: (path, expected verdict kind)}."""
    rng = random.Random(seed)
    yaml = synthetic_yaml()
    packed = zlib.compress(yaml, 9)
    blobs: Dict[str, Tuple[bytes, str]] = {
        "empty.bin": (b"", "empty"),
        "random_aligned.sav": (bytes(rng.getrandbits(8) for _ in range(26624)), "aes_ecb_candidate"),
        "random_unaligned.sav": (bytes(rng.getrandbits(8) for _ in range(26627)), "high_entropy_unaligned"),
        "plain.yaml": (yaml, "plaintext_yaml"),
        "plain.json": (json.dumps({"state": {"char_name": "Synthetic", "level": 30,
                                             "items": ["@FAKE%d" % i for i in range(50)]}},
                                  indent=1).encode(), "plaintext_json"),
        "zlib_only.bin": (packed, "zlib"),
        "zlib_ps5_trailer.bin": (packed + struct.pack("<I", len(yaml)), "zlib_trailer_ps5"),
        "zlib_pc_trailer.bin": (packed + struct.pack("<II", zlib.adler32(yaml), len(yaml)), "zlib_trailer_pc"),
        "header_then_zlib.bin": (b"HDR\x00" + struct.pack("<I", len(packed)) + packed, "unknown"),
        "gzip.bin": (_gzip(yaml), "gzip"),
        "zstd_magic.bin": (ZSTD_MAGIC + bytes(rng.getrandbits(8) for _ in range(512)), "zstd"),
        "pfd.bin": (b"\x00\x00\x00\x00PFDB" + bytes(rng.getrandbits(8) for _ in range(1024)), "container"),
    }
    aes = _fixture_aes_shaped(rng, yaml)
    if aes is not None:
        blobs["aes_shaped_ps5.sav"] = (aes, "aes_ecb_candidate")
    out = {}
    for name, (blob, kind) in blobs.items():
        p = os.path.join(folder, name)
        with open(p, "wb") as fh:
            fh.write(blob)
        out[name] = (p, kind)
    return out


def _gzip(data: bytes) -> bytes:
    c = zlib.compressobj(9, zlib.DEFLATED, 31)
    return c.compress(data) + c.flush()


def self_test(verbose: bool = True) -> int:
    """Build the fixtures in a temp dir, identify each, compare the verdict kind. 0 = all pass."""
    failures = 0
    with tempfile.TemporaryDirectory(prefix="save_id_") as tmp:
        fx = make_fixtures(tmp)
        for name, (path, want) in sorted(fx.items()):
            got = identify(path).verdict.kind
            ok = got == want
            failures += not ok
            if verbose:
                print("  [%s] %-24s want %-24s got %s" % ("PASS" if ok else "FAIL", name, want, got))
    if verbose:
        print("self-test: %d fixtures, %d failed" % (len(fx), failures))
    return 0 if failures == 0 else 1


# ---------------------------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bl4forge.tools.save_id",
        description="Identify what a save file is (layers between you and plaintext) before any key scan. "
                    "Offline; reads only the file you name; never handles keys.")
    p.add_argument("file", nargs="?", help="the save file to identify")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--self-test", action="store_true", help="identify synthetic fixtures and check the verdicts")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.file:
        build_parser().error("a file is required (or --self-test)")
    if not os.path.isfile(args.file):
        print("save_id: not a file: %s" % args.file, file=sys.stderr)
        return 2
    try:
        rep = identify(args.file)
    except OSError as ex:
        print("save_id: cannot read %s: %s" % (args.file, ex), file=sys.stderr)
        return 2
    print(json.dumps(rep.to_dict(), indent=1) if args.json else render_text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())

