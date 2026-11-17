"""save_history: format-aware version control for Borderlands 4 saves. Offline, stdlib only.

The game re-serialises a save on every load, so two saves that hold the same values rarely share bytes and a
byte diff is noise. This tool keeps snapshots of a save and diffs them SEMANTICALLY. Each snapshot stores the
encrypted original byte for byte (so it can be restored) and a normalized plaintext: the YAML parsed and
written back in one canonical form (sorted keys, one quoting style, stable number formatting). `diff`
compares the parsed trees, so a value that did not change never shows up.

    python -m bl4forge.tools.save_history init <dir>
    python -m bl4forge.tools.save_history snapshot <file.sav> --key-file <key> --message "after vault run"
    python -m bl4forge.tools.save_history log
    python -m bl4forge.tools.save_history diff <snapshot-a> <snapshot-b>
    python -m bl4forge.tools.save_history restore <snapshot> -o <out.sav>

Snapshots are named by number (`3`, `0003`) or `latest`, `latest~1`, ...

Store layout (plain files; no git, no database):
    <dir>/.savehistory/store.json                format version and creation time
    <dir>/.savehistory/snapshots/NNNN.sav        the encrypted original, exactly as read
    <dir>/.savehistory/snapshots/NNNN.yaml       the normalized plaintext
    <dir>/.savehistory/snapshots/NNNN.meta.json  timestamp, message, platform, sizes, sha256s (never the key)

DISCLOSURE (what this code does)
  Reads: the save given to `snapshot`, the key file given with --key-file, and the store.
  Writes: only inside <dir>/.savehistory, plus the -o file of `restore` (an existing file is refused unless
  --force is given). Network: none. The key comes only from the user's --key-file. It is used in memory and is
  never printed, logged or written to the store. No key ships with this tool; you must supply your own.
  Note: NNNN.yaml holds the decrypted save content as plain text. Treat the store like the saves themselves.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import sys
import time
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from ..core.errors import ForgeError
from ..modules.save import _container

STORE_DIRNAME = ".savehistory"
STORE_FORMAT = 1
NORMAL_HEADER = "# bl4forge save_history normalized form v1: sorted keys, canonical scalars. Do not edit."
PLATFORMS = ("ps5", "pc")
# Fields tried, in order, as the stable id of list elements (the first one present in every element and
# unique on both sides wins). Which BL4 fields are truly stable is UNVERIFIED; extend with --id-key.
DEFAULT_ID_KEYS = ("id", "guid", "uuid", "name", "serial", "slot", "key", "type")


class HistoryError(ForgeError):
    """A store, snapshot, key-file or YAML problem; the CLI reports it and exits with code 2."""


# =================================================================================================
# 1. Reading the save's YAML (a block-style subset, stdlib only)
# =================================================================================================
# The standard library has no YAML reader. This one covers what the game's saves are seen to use:
# block mappings and sequences (including sequences written at their parent key's indent),
# plain / single-quoted / double-quoted scalars, simple one-line flow collections, and comments.
# Anything else (anchors, aliases, tags, block scalars, multi-line strings, several documents) is
# REFUSED with its line number instead of guessed, so a snapshot is never stored from a misread save.

class _Line:
    __slots__ = ("no", "indent", "text")

    def __init__(self, no: int, indent: int, text: str) -> None:
        self.no, self.indent, self.text = no, indent, text


def _err(no: int, msg: str) -> HistoryError:
    return HistoryError("YAML line %d: %s" % (no, msg))


def _lines(text: str) -> List[_Line]:
    if text.startswith("\ufeff"):
        text = text[1:]
    out: List[_Line] = []
    for no, raw in enumerate(text.split("\n"), 1):
        raw = raw.rstrip("\r")
        body = raw.lstrip(" ")
        if not body.strip() or body.startswith("#"):
            continue
        if body.startswith("\t"):
            raise _err(no, "tab indentation is not supported")
        if raw.startswith("%") or raw.rstrip() in ("---", "..."):
            if raw.rstrip() == "---" and out:
                raise _err(no, "more than one YAML document is not supported")
            continue
        out.append(_Line(no, len(raw) - len(body), body.rstrip(" \t")))
    return out


def _is_dash(text: str) -> bool:
    return text == "-" or text.startswith("- ")


def _quoted_end(s: str, start: int) -> int:
    """Index just past the quoted scalar that opens at s[start], or -1 if it does not close on this line."""
    q, i = s[start], start + 1
    while i < len(s):
        c = s[i]
        if q == "'" and c == "'":
            if s[i + 1:i + 2] == "'":
                i += 2
                continue
            return i + 1
        if q == '"':
            if c == "\\":
                i += 2
                continue
            if c == '"':
                return i + 1
        i += 1
    return -1


_ESCAPES = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f",
            "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85",
            "_": "\xa0", "L": "\u2028", "P": "\u2029"}
_HEX_ESCAPES = {"x": 2, "u": 4, "U": 8}
_HEX_DIGITS = set("0123456789abcdefABCDEF")


def _unquote(tok: str, no: int) -> str:
    if tok[0] == "'":
        return tok[1:-1].replace("''", "'")
    out: List[str] = []
    i, end = 1, len(tok) - 1
    while i < end:
        c = tok[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        e = tok[i + 1] if i + 1 < end else ""
        if e and e in _ESCAPES:
            out.append(_ESCAPES[e])
            i += 2
        elif e and e in _HEX_ESCAPES:
            width = _HEX_ESCAPES[e]
            digits = tok[i + 2:i + 2 + width]
            if len(digits) != width or not set(digits) <= _HEX_DIGITS or int(digits, 16) > 0x10FFFF:
                raise _err(no, "bad \\%s escape in a double-quoted string" % e)
            out.append(chr(int(digits, 16)))
            i += 2 + width
        else:
            raise _err(no, "unknown escape \\%s in a double-quoted string" % e)
    text = "".join(out)
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):      # join \uD83D\uDE00-style surrogate pairs
        text = text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")
    return text


_INT_RE = re.compile(r"^[-+]?[0-9]+$")
_HEXINT_RE = re.compile(r"^0x[0-9a-fA-F]+$")
_OCTINT_RE = re.compile(r"^0o[0-7]+$")
_FLOAT_RE = re.compile(r"^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?$")
_INF_RE = re.compile(r"^[-+]?\.(?:inf|Inf|INF)$")
_NAN_RE = re.compile(r"^\.(?:nan|NaN|NAN)$")


def _plain(tok: str) -> Any:
    """Resolve a plain (unquoted) scalar with the YAML 1.2 core schema."""
    if tok in ("", "~", "null", "Null", "NULL"):
        return None
    if tok in ("true", "True", "TRUE"):
        return True
    if tok in ("false", "False", "FALSE"):
        return False
    if _INT_RE.match(tok):
        return int(tok)
    if _HEXINT_RE.match(tok):
        return int(tok[2:], 16)
    if _OCTINT_RE.match(tok):
        return int(tok[2:], 8)
    if _FLOAT_RE.match(tok):
        return float(tok)
    if _INF_RE.match(tok):
        return float("-inf") if tok.startswith("-") else float("inf")
    if _NAN_RE.match(tok):
        return float("nan")
    return tok


def _only_comment(rest: str, no: int) -> None:
    rest = rest.strip(" ")
    if rest and not rest.startswith("#"):
        raise _err(no, "unexpected text after a value: %r" % rest[:20])


def _skip(s: str, i: int) -> int:
    while i < len(s) and s[i] == " ":
        i += 1
    return i


def _flow_scalar(s: str, i: int, no: int, as_key: bool = False) -> Tuple[Any, int]:
    if i < len(s) and s[i] in "'\"":
        end = _quoted_end(s, i)
        if end < 0:
            raise _err(no, "quoted string does not close on this line")
        return _unquote(s[i:end], no), end
    j = i
    while j < len(s) and s[j] not in ",[]{}" and not (
            s[j] == ":" and (j + 1 == len(s) or s[j + 1] in " ,[]{}")):
        j += 1
    tok = s[i:j].strip(" ")
    if tok[:1] in ("&", "*", "!"):
        raise _err(no, "anchors, aliases and tags are not supported")
    return (tok if as_key else _plain(tok)), j


def _flow(s: str, i: int, no: int) -> Tuple[Any, int]:
    """One flow node (`[...]`, `{...}` or a scalar) starting at s[i]; returns (value, index after it)."""
    i = _skip(s, i)
    if i >= len(s):
        raise _err(no, "flow collection does not close on this line")
    if s[i] == "[":
        items: List[Any] = []
        i = _skip(s, i + 1)
        while True:
            if i < len(s) and s[i] == "]":
                return items, i + 1
            value, i = _flow(s, i, no)
            items.append(value)
            i = _skip(s, i)
            if i < len(s) and s[i] == ",":
                i = _skip(s, i + 1)
            elif not (i < len(s) and s[i] == "]"):
                raise _err(no, "malformed flow sequence")
    if s[i] == "{":
        mapping: Dict[str, Any] = {}
        i = _skip(s, i + 1)
        while True:
            if i < len(s) and s[i] == "}":
                return mapping, i + 1
            key, i = _flow_scalar(s, i, no, as_key=True)
            i = _skip(s, i)
            value: Any = None
            if i < len(s) and s[i] == ":":
                value, i = _flow(s, i + 1, no)
                i = _skip(s, i)
            if key in mapping:
                raise _err(no, "duplicate key %r" % key)
            mapping[key] = value
            if i < len(s) and s[i] == ",":
                i = _skip(s, i + 1)
            elif not (i < len(s) and s[i] == "}"):
                raise _err(no, "malformed flow mapping")
    return _flow_scalar(s, i, no)


def _scalar(tok: str, no: int) -> Any:
    c = tok[0]
    if c in "'\"":
        end = _quoted_end(tok, 0)
        if end < 0:
            raise _err(no, "quoted string does not close on this line (multi-line strings are not supported)")
        _only_comment(tok[end:], no)
        return _unquote(tok[:end], no)
    if c in "[{":
        value, end = _flow(tok, 0, no)
        _only_comment(tok[end:], no)
        return value
    if c in "|>":
        raise _err(no, "block scalars ('|' or '>') are not supported")
    if c in "&*!":
        raise _err(no, "anchors, aliases and tags are not supported")
    return _plain(re.split(r"\s#", tok, maxsplit=1)[0].rstrip(" "))


_KEY_END = re.compile(r":(?= |$)")


def _split_key(text: str, no: int) -> Optional[Tuple[str, str]]:
    """(key, rest) when the text is a `key: rest` mapping entry, else None."""
    if text[0] in "'\"":
        end = _quoted_end(text, 0)
        if end < 0:
            return None
        after = text[end:].lstrip(" ")
        if after.startswith(":") and (len(after) == 1 or after[1] == " "):
            return _unquote(text[:end], no), after[1:].strip(" ")
        return None
    if text[0] in "[{&*!|>#":
        return None
    m = _KEY_END.search(text)
    if m is None:
        return None
    key = text[:m.start()].rstrip(" ")
    if re.search(r"\s#", key):
        return None
    return key, text[m.end():].strip(" ")


class _Parser:
    def __init__(self, text: str) -> None:
        self.lines = _lines(text)
        self.i = 0

    def parse(self) -> Any:
        if not self.lines:
            return None
        value = self.node(self.lines[0].indent)
        if self.i < len(self.lines):
            raise _err(self.lines[self.i].no, "unexpected indentation")
        return value

    def node(self, indent: int) -> Any:
        line = self.lines[self.i]
        if _is_dash(line.text):
            return self.sequence(indent)
        if _split_key(line.text, line.no) is not None:
            return self.mapping(indent)
        self.i += 1
        return _scalar(line.text, line.no)

    def child(self, indent: int, same_indent_list: bool) -> Any:
        """The value block under a `key:` or `-` with nothing after it (None when there is none)."""
        if self.i >= len(self.lines):
            return None
        nxt = self.lines[self.i]
        if nxt.indent > indent or (same_indent_list and nxt.indent == indent and _is_dash(nxt.text)):
            return self.node(nxt.indent)
        return None

    def mapping(self, indent: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise _err(line.no, "unexpected indentation")
            if _is_dash(line.text):
                raise _err(line.no, "a list item where a 'key: value' line was expected")
            entry = _split_key(line.text, line.no)
            if entry is None:
                raise _err(line.no, "expected a 'key: value' line")
            key, rest = entry
            if key in out:
                raise _err(line.no, "duplicate key %r" % key)
            self.i += 1
            if rest and not rest.startswith("#"):
                out[key] = _scalar(rest, line.no)
            else:  # the game writes lists at the key's own indent: `experience: \n  - type: ...`
                out[key] = self.child(indent, same_indent_list=True)
        return out

    def sequence(self, indent: int) -> List[Any]:
        out: List[Any] = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise _err(line.no, "unexpected indentation")
            if not _is_dash(line.text):
                break
            rest = line.text[1:].lstrip(" ")
            if not rest or rest.startswith("#"):
                self.i += 1
                out.append(self.child(indent, same_indent_list=False))
            else:  # `- key: v` / `- scalar` / `- - x`: the item starts at the column after the dash
                line.indent += len(line.text) - len(rest)
                line.text = rest
                out.append(self.node(line.indent))
        return out


def parse_yaml(text: str) -> Any:
    """Parse save YAML (the supported subset) into dict / list / str / int / float / bool / None."""
    return _Parser(text).parse()


# =================================================================================================
# 2. The canonical (normalized) form
# =================================================================================================
# Deterministic: keys sorted by code point; strings always single-quoted (double-quoted JSON-style only
# when they hold non-printable characters); ints in decimal; floats in Python's shortest round-trip repr
# (`.nan`, `.inf`, `-.inf` for specials); `null` / `true` / `false`; `{}` / `[]` for empty containers;
# lists indented two spaces under their key. parse_yaml(dump_canonical(t)) == t for every parsed tree.

_PLAIN_KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/]*$")


def _str_text(s: str) -> str:
    if s.isprintable():
        return "'" + s.replace("'", "''") + "'"
    return json.dumps(s)            # a JSON string is a valid YAML double-quoted scalar


def _key_text(key: str) -> str:
    return key if _PLAIN_KEY.match(key) else _str_text(key)


def _float_text(f: float) -> str:
    if math.isnan(f):
        return ".nan"
    if math.isinf(f):
        return ".inf" if f > 0 else "-.inf"
    return repr(f)                  # always holds '.' or 'e', so it reads back as a float


def _leaf_text(v: Any) -> str:
    if isinstance(v, dict):
        return "{}"
    if isinstance(v, list):
        return "[]"
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _float_text(v)
    if isinstance(v, str):
        return _str_text(v)
    raise TypeError("cannot normalize a %s" % type(v).__name__)


def _emit(node: Any, indent: int, out: List[str]) -> None:
    pad = " " * indent
    if isinstance(node, dict) and node:
        for key in sorted(node):
            value = node[key]
            if isinstance(value, (dict, list)) and value:
                out.append("%s%s:" % (pad, _key_text(key)))
                _emit(value, indent + 2, out)
            else:
                out.append("%s%s: %s" % (pad, _key_text(key), _leaf_text(value)))
    elif isinstance(node, list) and node:
        for item in node:
            if isinstance(item, (dict, list)) and item:
                sub: List[str] = []
                _emit(item, indent + 2, sub)
                sub[0] = pad + "- " + sub[0][indent + 2:]
                out.extend(sub)
            else:
                out.append("%s- %s" % (pad, _leaf_text(item)))
    else:
        out.append(pad + _leaf_text(node))


def dump_canonical(tree: Any) -> str:
    """The normalized text of a parsed tree (LF line endings, trailing newline)."""
    out: List[str] = [NORMAL_HEADER]
    _emit(tree, 0, out)
    return "\n".join(out) + "\n"


def normalize(yaml_text: str) -> Tuple[Any, str]:
    """Save YAML -> (parsed tree, canonical text). Raises HistoryError on YAML outside the subset."""
    tree = parse_yaml(yaml_text)
    return tree, dump_canonical(tree)


# =================================================================================================
# 3. Semantic diff
# =================================================================================================

class Change(NamedTuple):
    kind: str                 # changed | added | removed | count | reordered
    path: Tuple[str, ...]     # display segments: mapping keys, then "[name=x]" (by id), "['x']" or "[3]"
    old: Any = None           # count / reordered: old length
    new: Any = None           # count / reordered: new length

    @property
    def where(self) -> str:
        return format_path(self.path)

    @property
    def top(self) -> str:
        return self.path[0] if self.path else "(root)"


def format_path(path: Sequence[str]) -> str:
    out = ""
    for seg in path:
        out += seg if seg.startswith("[") else (("." if out else "") + seg)
    return out


class _DiffCtx(NamedTuple):
    id_keys: Tuple[str, ...]
    digits: Optional[int]
    ignore: Tuple[str, ...]
    ignore_order: bool

    def ignored(self, path: Tuple[str, ...]) -> bool:
        if not self.ignore or not path:
            return False
        where = format_path(path)
        return any(fnmatch.fnmatchcase(where, pat) or where.startswith(pat + ".") or where.startswith(pat + "[")
                   for pat in self.ignore)


def _round(x: float, digits: int) -> float:
    return float("%.*g" % (digits, x))


def _same(a: Any, b: Any, digits: Optional[int]) -> bool:
    """Leaf equality: bools only equal bools; ints and floats compare as numbers (1 == 1.0); NaN == NaN."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        a_nan = isinstance(a, float) and math.isnan(a)
        b_nan = isinstance(b, float) and math.isnan(b)
        if a_nan or b_nan:
            return a_nan and b_nan
        if digits is not None and (isinstance(a, float) or isinstance(b, float)):
            return _round(a, digits) == _round(b, digits)
        return a == b
    return type(a) is type(b) and a == b


def _ident(v: Any) -> str:
    return json.dumps(v, sort_keys=True)


def _id_text(v: Any) -> str:
    return v if isinstance(v, str) and _PLAIN_KEY.match(v) else json.dumps(v, ensure_ascii=False)


def _is_id_value(v: Any) -> bool:
    return isinstance(v, (str, int)) and not isinstance(v, bool)


def _id_key(a: List[Any], b: List[Any], id_keys: Tuple[str, ...]) -> Optional[str]:
    """The first id field present in every element of both lists, with unique values within each list."""
    items = a + b
    if not items or not all(isinstance(x, dict) for x in items):
        return None
    for key in id_keys:
        if all(key in x and _is_id_value(x[key]) for x in items) \
                and len({_ident(x[key]) for x in a}) == len(a) and len({_ident(x[key]) for x in b}) == len(b):
            return key
    return None


def _is_scalar_set(xs: List[Any]) -> bool:
    return all(_is_id_value(x) or isinstance(x, bool) for x in xs) and len({_ident(x) for x in xs}) == len(xs)


def _walk_list(a: List[Any], b: List[Any], path: Tuple[str, ...], ctx: _DiffCtx, out: List[Change]) -> None:
    key = _id_key(a, b, ctx.id_keys)
    if key is not None:                                   # elements matched by a stable id
        ka = {_ident(x[key]): x for x in a}
        kb = {_ident(y[key]): y for y in b}
        for ident, x in ka.items():
            p = path + ("[%s=%s]" % (key, _id_text(x[key])),)
            if ident not in kb:
                if not ctx.ignored(p):
                    out.append(Change("removed", p, x, None))
            else:
                _walk(x, kb[ident], p, ctx, out)
        for ident, y in kb.items():
            p = path + ("[%s=%s]" % (key, _id_text(y[key])),)
            if ident not in ka and not ctx.ignored(p):
                out.append(Change("added", p, None, y))
        if not ctx.ignore_order and [i for i in ka if i in kb] != [i for i in kb if i in ka]:
            out.append(Change("reordered", path, len(a), len(b)))
        return
    if _is_scalar_set(a) and _is_scalar_set(b):           # unique scalars: compare as a set
        ia, ib = [_ident(x) for x in a], [_ident(y) for y in b]
        sa, sb = set(ia), set(ib)
        for x, i in zip(a, ia):
            if i not in sb and not ctx.ignored(path + ("[%s]" % _id_text(x),)):
                out.append(Change("removed", path + ("[%s]" % _id_text(x),), x, None))
        for y, i in zip(b, ib):
            if i not in sa and not ctx.ignored(path + ("[%s]" % _id_text(y),)):
                out.append(Change("added", path + ("[%s]" % _id_text(y),), None, y))
        if not ctx.ignore_order and [i for i in ia if i in sb] != [i for i in ib if i in sa]:
            out.append(Change("reordered", path, len(a), len(b)))
        return
    if len(a) == len(b):                                  # no stable id, same shape: by position
        for n, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, path + ("[%d]" % n,), ctx, out)
        return
    out.append(Change("count", path, len(a), len(b)))     # no stable id, different length: counts only


def _walk(a: Any, b: Any, path: Tuple[str, ...], ctx: _DiffCtx, out: List[Change]) -> None:
    if ctx.ignored(path):
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = path + (_key_text(k),)
            if k not in b:
                if not ctx.ignored(p):
                    out.append(Change("removed", p, a[k], None))
            elif k not in a:
                if not ctx.ignored(p):
                    out.append(Change("added", p, None, b[k]))
            else:
                _walk(a[k], b[k], p, ctx, out)
    elif isinstance(a, list) and isinstance(b, list):
        _walk_list(a, b, path, ctx, out)
    elif isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        out.append(Change("changed", path, a, b))
    elif not _same(a, b, ctx.digits):
        out.append(Change("changed", path, a, b))


def diff_trees(old: Any, new: Any, id_keys: Sequence[str] = DEFAULT_ID_KEYS,
               float_digits: Optional[int] = None, ignore: Sequence[str] = (),
               ignore_order: bool = False) -> List[Change]:
    """Semantic changes from `old` to `new` (parsed trees). Empty when they hold the same values.

    Mappings: added / removed keys and changed leaf values (old -> new). Lists: elements are matched by
    the first stable id field (see DEFAULT_ID_KEYS) and diffed per element; unique scalar lists are
    compared as sets; other lists are compared by position when the length is unchanged, else only the
    counts are reported. A changed order of matched elements is one `reordered` change (off with
    ignore_order). `ignore` takes dotted-path globs (`stats`, `state.*.timestamp`); `float_digits` compares
    floats to that many significant digits.
    """
    ctx = _DiffCtx(tuple(id_keys), float_digits, tuple(ignore), ignore_order)
    out: List[Change] = []
    _walk(old, new, (), ctx, out)
    return out


def _show(v: Any, limit: int = 120) -> str:
    s = json.dumps(v, sort_keys=True, ensure_ascii=False) if isinstance(v, (dict, list)) and v else _leaf_text(v)
    return s if len(s) <= limit else s[:limit - 3] + "..."


def format_change(c: Change) -> str:
    where = c.where or "(root)"
    if c.kind == "changed":
        return "~ %s: %s -> %s" % (where, _show(c.old), _show(c.new))
    if c.kind == "added":
        return "+ %s: %s" % (where, _show(c.new))
    if c.kind == "removed":
        return "- %s: %s" % (where, _show(c.old))
    if c.kind == "count":
        return "# %s: %d -> %d elements (no stable id; per-element changes not shown)" % (where, c.old, c.new)
    return "r %s: same elements, different order" % where


# =================================================================================================
# 4. The store
# =================================================================================================

_SNAP_FILE = re.compile(r"^(\d{4,})\.(sav|yaml|meta\.json)$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _kb(n: int) -> str:
    return "%.1f KB" % (n / 1024.0)


def _write_atomic(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class Store:
    """A .savehistory directory. A snapshot exists once its NNNN.meta.json does (it is written last)."""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        self.snap_dir = os.path.join(self.root, "snapshots")

    @classmethod
    def init(cls, directory: str) -> "Store":
        if not os.path.isdir(directory):
            raise HistoryError("not a directory: %s" % directory)
        root = os.path.join(directory, STORE_DIRNAME)
        if os.path.exists(os.path.join(root, "store.json")):
            raise HistoryError("a save history already exists at %s" % os.path.abspath(root))
        os.makedirs(os.path.join(root, "snapshots"), exist_ok=True)
        info = {"format": STORE_FORMAT, "created": _now(), "tool": "bl4forge.tools.save_history"}
        _write_atomic(os.path.join(root, "store.json"), (json.dumps(info, indent=1) + "\n").encode("utf-8"))
        return cls(root)

    @classmethod
    def open(cls, path: Optional[str] = None) -> "Store":
        """`path` is a .savehistory dir or a dir holding one; None searches up from the current directory."""
        if path is not None:
            candidates = [path, os.path.join(path, STORE_DIRNAME)]
        else:
            candidates, here = [], os.path.abspath(os.getcwd())
            while True:
                candidates.append(os.path.join(here, STORE_DIRNAME))
                parent = os.path.dirname(here)
                if parent == here:
                    break
                here = parent
        for cand in candidates:
            info_path = os.path.join(cand, "store.json")
            if os.path.isfile(info_path):
                try:
                    with open(info_path, encoding="utf-8") as fh:
                        info = json.load(fh)
                except ValueError:
                    raise HistoryError("store file is not valid JSON: %s" % info_path) from None
                if info.get("format") != STORE_FORMAT:
                    raise HistoryError("unsupported store format %r in %s" % (info.get("format"), info_path))
                return cls(cand)
        raise HistoryError("no %s store found (run `init <dir>` first, or pass --store DIR)" % STORE_DIRNAME)

    def _names(self) -> List[str]:
        try:
            return os.listdir(self.snap_dir)
        except FileNotFoundError:
            return []

    def _path(self, sid: int, ext: str) -> str:
        return os.path.join(self.snap_dir, "%04d.%s" % (sid, ext))

    def ids(self) -> List[int]:
        found = (_SNAP_FILE.match(n) for n in self._names())
        return sorted(int(m.group(1)) for m in found if m and m.group(2) == "meta.json")

    def _next_id(self) -> int:
        found = [int(m.group(1)) for m in (_SNAP_FILE.match(n) for n in self._names()) if m]
        return max(found, default=0) + 1

    def meta(self, sid: int) -> Dict[str, Any]:
        try:
            with open(self._path(sid, "meta.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            raise HistoryError("no snapshot %04d" % sid) from None
        except ValueError:
            raise HistoryError("snapshot %04d: meta.json is not valid JSON" % sid) from None

    def resolve(self, ref: str) -> int:
        """'3', '0003', 'latest', 'latest~2' (also 'head') -> snapshot number."""
        ids = self.ids()
        if not ids:
            raise HistoryError("the store has no snapshots yet")
        r = str(ref).strip().lower()
        m = re.fullmatch(r"(?:latest|head)(?:~(\d+))?", r)
        if m:
            back = int(m.group(1) or 0)
            if back >= len(ids):
                raise HistoryError("%s: only %d snapshot(s) exist" % (ref, len(ids)))
            return ids[-1 - back]
        if r.isdigit() and int(r) in ids:
            return int(r)
        raise HistoryError("no snapshot %r (have %04d..%04d, %d in all)" % (ref, ids[0], ids[-1], len(ids)))

    def add(self, sav: bytes, normalized: str, meta: Dict[str, Any]) -> int:
        os.makedirs(self.snap_dir, exist_ok=True)
        for _ in range(1000):
            sid = self._next_id()
            try:
                fh = open(self._path(sid, "sav"), "xb")       # exclusive create reserves the number
            except FileExistsError:
                continue
            with fh:
                fh.write(sav)
                fh.flush()
                os.fsync(fh.fileno())
            _write_atomic(self._path(sid, "yaml"), normalized.encode("utf-8"))
            record = dict(meta, id=sid)
            _write_atomic(self._path(sid, "meta.json"),
                          (json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
            return sid
        raise HistoryError("could not allocate a snapshot number")

    def read_sav(self, sid: int) -> bytes:
        meta = self.meta(sid)
        with open(self._path(sid, "sav"), "rb") as fh:
            data = fh.read()
        if _sha(data) != meta.get("sav_sha256"):
            raise HistoryError("snapshot %04d: the stored save does not match its recorded sha256 "
                               "(the store was modified)" % sid)
        return data

    def read_normalized(self, sid: int) -> str:
        meta = self.meta(sid)
        with open(self._path(sid, "yaml"), "rb") as fh:
            data = fh.read()
        if _sha(data) != meta.get("normalized_sha256"):
            raise HistoryError("snapshot %04d: the normalized YAML does not match its recorded sha256 "
                               "(the store was modified)" % sid)
        return data.decode("utf-8")


# =================================================================================================
# 5. Operations (usable from Python; the CLI below is a thin layer)
# =================================================================================================

def load_key(path: str) -> bytes:
    """Read a 32-byte key from a file of 32 raw bytes or 64 hex digits (whitespace and 0x allowed).
    Error messages never show the file's contents."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as ex:
        raise HistoryError("cannot read key file %s: %s" % (path, ex.strerror)) from None
    if len(raw) == 32:
        return raw
    bad = HistoryError("key file %s must hold exactly 32 raw bytes or 64 hex digits (contents not shown)" % path)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise bad from None
    digits = "".join(text.split())
    if digits[:2].lower() == "0x":
        digits = digits[2:]
    if len(digits) != 64 or not set(digits) <= _HEX_DIGITS:
        raise bad
    return bytes.fromhex(digits)


def take_snapshot(store: Store, save_path: str, key: bytes, message: str = "",
                  platform: str = "ps5") -> Dict[str, Any]:
    """Decrypt + normalize one save and store it. `key` is the final AES key (for PC: already derived
    with _container.pc_key). Nothing is stored unless the save decrypts and parses. Returns the meta."""
    if platform not in PLATFORMS:
        raise HistoryError("platform must be one of %s" % ", ".join(PLATFORMS))
    with open(save_path, "rb") as fh:
        data = fh.read()
    yaml_bytes = _container.decrypt(data, key, platform)           # strict: raises SaveError on a bad key
    try:
        text = yaml_bytes.decode("utf-8")
    except UnicodeDecodeError as ex:
        raise HistoryError("the decrypted save is not UTF-8 text (%s)" % ex.reason) from None
    tree, canon = normalize(text)
    if diff_trees(tree, parse_yaml(canon)):
        raise HistoryError("internal error: the normalized form does not read back to the same values; "
                           "nothing was stored")
    norm_sha = _sha(canon.encode("utf-8"))
    same_as = None
    for sid in reversed(store.ids()):
        if store.meta(sid).get("normalized_sha256") == norm_sha:
            same_as = sid
            break
    meta = {
        "format": STORE_FORMAT,
        "timestamp": _now(),
        "message": message,
        "platform": platform,
        "source": os.path.abspath(save_path),
        "sav_bytes": len(data),
        "sav_sha256": _sha(data),
        "yaml_bytes": len(yaml_bytes),
        "yaml_sha256": _sha(yaml_bytes),
        "normalized_sha256": norm_sha,
        "same_as": same_as,
    }
    return store.meta(store.add(data, canon, meta))


def diff_snapshots(store: Store, a: int, b: int, **options: Any) -> List[Change]:
    """Semantic diff of two stored snapshots (options as for diff_trees)."""
    return diff_trees(parse_yaml(store.read_normalized(a)), parse_yaml(store.read_normalized(b)), **options)


def restore_snapshot(store: Store, sid: int, out_path: str, force: bool = False) -> bytes:
    """Write the stored ENCRYPTED original of `sid` to out_path (verified against its sha256 first)."""
    data = store.read_sav(sid)
    out = os.path.abspath(out_path)
    try:
        inside = os.path.commonpath([out, store.root]) == store.root
    except ValueError:                       # different drives on Windows
        inside = False
    if inside:
        raise HistoryError("refusing to write inside the store (%s)" % store.root)
    if os.path.exists(out) and not force:
        raise HistoryError("%s already exists; pass --force to replace it" % out_path)
    _write_atomic(out, data)
    return data


# =================================================================================================
# 6. CLI
# =================================================================================================

def cmd_init(args: argparse.Namespace) -> int:
    store = Store.init(args.dir)
    print("initialized an empty save history in %s" % store.root)
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    store = Store.open(args.store)
    key = load_key(args.key_file)
    if args.platform == "pc":
        if not args.steam_id:
            raise HistoryError("--platform pc needs --steam-id (the key file then holds the PC base key)")
        key = _container.pc_key(key, args.steam_id)
    m = take_snapshot(store, args.save, key, args.message, args.platform)
    same = "; same values as %04d" % m["same_as"] if m.get("same_as") is not None else ""
    print("snapshot %04d  %s  %s  (%s save, %s plaintext%s)" % (
        m["id"], m["timestamp"], json.dumps(m["message"], ensure_ascii=False),
        _kb(m["sav_bytes"]), _kb(m["yaml_bytes"]), same))
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    store = Store.open(args.store)
    metas = [store.meta(sid) for sid in store.ids()]
    if args.json:
        print(json.dumps(metas, indent=1, sort_keys=True, ensure_ascii=False))
        return 0
    if not metas:
        print("no snapshots yet")
        return 0
    for m in metas:
        same = "  (same values as %04d)" % m["same_as"] if m.get("same_as") is not None else ""
        print("%04d  %s  %s  %9s  %s%s" % (m["id"], m["timestamp"], m["sav_sha256"][:12], _kb(m["sav_bytes"]),
                                           m.get("message") or "", same))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    store = Store.open(args.store)
    a, b = store.resolve(args.a), store.resolve(args.b)
    changes = diff_snapshots(store, a, b, id_keys=tuple(args.id_key) + DEFAULT_ID_KEYS,
                             float_digits=args.float_digits, ignore=tuple(args.ignore),
                             ignore_order=args.ignore_order)
    tops = sorted({c.top for c in changes})
    if args.json:
        print(json.dumps({"a": a, "b": b, "top_level_keys": tops,
                          "changes": [{"kind": c.kind, "path": c.where, "old": c.old, "new": c.new}
                                      for c in changes]}, indent=1, ensure_ascii=False))
    elif not changes:
        print("%04d -> %04d: no semantic changes" % (a, b))
    else:
        print("%04d -> %04d: %d change%s under %d top-level key%s: %s" % (
            a, b, len(changes), "" if len(changes) == 1 else "s",
            len(tops), "" if len(tops) == 1 else "s", ", ".join(tops)))
        for c in changes:
            print("  " + format_change(c))
    return 1 if changes else 0


def cmd_restore(args: argparse.Namespace) -> int:
    store = Store.open(args.store)
    sid = store.resolve(args.snapshot)
    data = restore_snapshot(store, sid, args.output, args.force)
    print("restored snapshot %04d (%s, sha256 %s...) to %s" % (sid, _kb(len(data)), _sha(data)[:12], args.output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bl4forge.tools.save_history",
        description="Format-aware version control for Borderlands 4 saves: snapshots store the encrypted "
                    "original and a normalized plaintext; diffs are semantic, not byte-level. Offline.",
        epilog="Exit codes: 0 ok (diff: no changes), 1 diff found changes, 2 error. "
               "Close the game before restoring over a live save.")
    sub = p.add_subparsers(dest="command", metavar="command")
    sub.required = True
    store_opt = argparse.ArgumentParser(add_help=False)
    store_opt.add_argument("--store", metavar="DIR",
                           help="the .savehistory dir or a dir holding one (default: search up from here)")

    s = sub.add_parser("init", help="create a .savehistory store in DIR")
    s.add_argument("dir")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("snapshot", parents=[store_opt], help="decrypt, normalize and store a save")
    s.add_argument("save", help="the encrypted .sav file")
    s.add_argument("--key-file", required=True,
                   help="file with YOUR key: 32 raw bytes or 64 hex digits (never stored or printed)")
    s.add_argument("-m", "--message", default="", help="what happened since the last snapshot")
    s.add_argument("--platform", choices=PLATFORMS, default="ps5")
    s.add_argument("--steam-id", help="PC only: the Steam ID the PC key is derived with")
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("log", parents=[store_opt], help="list snapshots")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("diff", parents=[store_opt], help="semantic diff of two snapshots")
    s.add_argument("a", help="older snapshot (number, latest, latest~N)")
    s.add_argument("b", help="newer snapshot")
    s.add_argument("--json", action="store_true")
    s.add_argument("--id-key", action="append", default=[], metavar="FIELD",
                   help="extra list-element id field, tried before the defaults (repeatable)")
    s.add_argument("--ignore", action="append", default=[], metavar="PATH",
                   help="dotted path or glob to leave out, e.g. stats or 'state.*.timestamp' (repeatable)")
    s.add_argument("--float-digits", type=int, metavar="N", help="compare floats to N significant digits")
    s.add_argument("--ignore-order", action="store_true", help="do not report reordered lists")
    s.set_defaults(func=cmd_diff)

    s = sub.add_parser("restore", parents=[store_opt], help="write a snapshot's encrypted original back out")
    s.add_argument("snapshot")
    s.add_argument("-o", "--output", required=True, help="where to write the .sav")
    s.add_argument("--force", action="store_true", help="replace an existing output file")
    s.set_defaults(func=cmd_restore)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ForgeError as ex:            # HistoryError, SaveError (wrong key, corrupt save), ...
        print("error: %s" % ex, file=sys.stderr)
        return 2
    except OSError as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
