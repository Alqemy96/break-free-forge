"""Wire format of Borderlands 4 item serials: base85 <-> bytes <-> bit stream <-> blocks.

Private to the codec module (nothing outside this package imports it). A faithful, bit-exact port of
the legacy `bl4codec.py` (itself a port of Nicnl/borderlands4-serials, AGPL-3.0 - see LICENSING.md and NOTICE),
reshaped to the immutable `core.types.Block/Part`, with every failure raised as `SerialError`.

Everything here is a pure function over its arguments. Module-level names are immutable constants
(tuples, bytes, str, mapping proxies) - there is no mutable global state.

Where behaviour intentionally differs from legacy it is listed in CONTRACT.md "Deviations".
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Optional, Sequence, Tuple

from ...core.errors import SerialError
from ...core.types import (
    Block, Part, SUBTYPE_INT, SUBTYPE_LIST, SUBTYPE_NONE,
    TOK_PART, TOK_SEP1, TOK_SEP2, TOK_STRING, TOK_VARBIT, TOK_VARINT,
)

MASK32 = 0xFFFFFFFF
MAX_VARINT = 0xFFFF        # nibble varint carries at most 4 nibbles
MAX_VARBIT = 0x7FFFFFFF    # length-prefixed varint: 5-bit length, so at most 31 bits
MAX_STRING_LEN = 0xFFFF    # string length is itself a nibble varint

_INT_TOKENS = (TOK_VARINT, TOK_VARBIT)


def show(value: object) -> str:
    """A short, safe repr for error messages (never raises, never huge)."""
    if isinstance(value, int) and not isinstance(value, bool) and value.bit_length() > 64:
        return "<%d-bit integer>" % value.bit_length()
    try:
        r = repr(value)
    except Exception:
        r = "<%s>" % type(value).__name__
    return r if len(r) <= 60 else r[:57] + "..."


# ---------------------------------------------------------------------------
# Bit mirroring tables (immutable)
# ---------------------------------------------------------------------------
def _mirror(v: int, n: int) -> int:
    out = 0
    for i in range(n):
        if v & (1 << i):
            out |= 1 << (n - 1 - i)
    return out


_M4 = tuple(_mirror(i, 4) for i in range(16))
_M5 = tuple(_mirror(i, 5) for i in range(32))
_M7 = tuple(_mirror(i, 7) for i in range(128))
_M8_TABLE = bytes(_mirror(i, 8) for i in range(256))    # for bytes.translate
_BYTE_BITS = tuple(format(i, "08b") for i in range(256))
_LSB4 = tuple(format(_M4[i], "04b") for i in range(16))  # nibble written least-significant bit first
_LSB5 = tuple(format(_M5[i], "05b") for i in range(32))  # 5-bit length written LSB first
_CHAR7 = tuple(format(_M7[i], "07b") for i in range(128))

# ---------------------------------------------------------------------------
# Base85 (custom alphabet; bytes are bit-mirrored)
# ---------------------------------------------------------------------------
B85_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{/}~"
_B85_REV = MappingProxyType({c: i for i, c in enumerate(B85_CHARSET)})
_B85_PAD = ord("~")   # 126: the legacy/Go constant used to pad a short final group
_POW = (1, 85, 85 ** 2, 85 ** 3, 85 ** 4)


def b85_decode(serial: str) -> bytes:
    if not isinstance(serial, str):
        raise SerialError("a serial must be a string, got %s" % type(serial).__name__)
    if serial[:2] != "@U":
        raise SerialError("not a Borderlands 4 item serial (it must start with '@U')")
    body = serial[2:]
    rev = _B85_REV
    out = bytearray()
    for start in range(0, len(body), 5):
        chunk = body[start:start + 5]
        v = 0
        for k, ch in enumerate(chunk):
            d = rev.get(ch)
            if d is None:
                raise SerialError("invalid base85 character %s at position %d" % (show(ch), 2 + start + k))
            v = v * 85 + d
        count = len(chunk)
        if count == 5:
            if v > MASK32:
                raise SerialError("base85 group at position %d overflows 32 bits" % (2 + start))
            nbytes = 4
        elif count == 1:
            raise SerialError("dangling base85 character at the end of the serial (truncated?)")
        else:
            for _ in range(5 - count):
                v = (v * 85 + _B85_PAD) & MASK32
            nbytes = count - 1
        out += v.to_bytes(4, "big")[:nbytes]
    return bytes(out).translate(_M8_TABLE)


def _digits(v: int) -> str:
    cs = B85_CHARSET
    out = []
    for p in (_POW[4], _POW[3], _POW[2], _POW[1]):
        d, v = divmod(v, p)
        out.append(cs[d])
    out.append(cs[v])
    return "".join(out)


def b85_encode(data: bytes) -> str:
    b = data.translate(_M8_TABLE)
    full = len(b) // 4 * 4
    out = [_digits(int.from_bytes(b[i:i + 4], "big")) for i in range(0, full, 4)]
    extra = len(b) - full
    if extra:
        v = int.from_bytes(b[full:] + b"\x00" * (4 - extra), "big")
        out.append(_digits(v)[:extra + 1])
    return "@U" + "".join(out)


# ---------------------------------------------------------------------------
# Bit reader (MSB-first within each byte). Holds the stream as a '0'/'1' string.
# ---------------------------------------------------------------------------
class _Reader:
    __slots__ = ("bits", "pos")

    def __init__(self, data: bytes):
        self.bits = "".join([_BYTE_BITS[b] for b in data])
        self.pos = 0

    def take(self, n: int) -> str:
        end = self.pos + n
        if end > len(self.bits):
            raise SerialError("serial is truncated or corrupt: ran out of data")
        s = self.bits[self.pos:end]
        self.pos = end
        return s

    def uint(self, n: int) -> int:
        return int(self.take(n), 2)


def _varint_read(r: _Reader) -> int:
    out = 0
    shift = 0
    for _ in range(4):
        out |= _M4[r.uint(4)] << shift
        shift += 4
        if r.take(1) == "0":
            break
    return out


def _varbit_read(r: _Reader) -> int:
    length = _M5[r.uint(5)]
    if length == 0:
        return 0
    return int(r.take(length)[::-1], 2)


def _string_read(r: _Reader) -> str:
    length = _varint_read(r)
    raw = r.take(7 * length)
    return "".join([chr(_M7[int(raw[i:i + 7], 2)]) for i in range(0, len(raw), 7)])


_TOKEN_BY_BITS = MappingProxyType({"100": TOK_VARINT, "110": TOK_VARBIT, "101": TOK_PART, "111": TOK_STRING})


def _next_token(r: _Reader) -> Optional[int]:
    """The next token, or None when the stream has ended (fewer than a whole token's bits remain)."""
    bits, pos = r.bits, r.pos
    if pos + 2 > len(bits):
        return None
    two = bits[pos:pos + 2]
    if two == "00":
        r.pos = pos + 2
        return TOK_SEP1
    if two == "01":
        r.pos = pos + 2
        return TOK_SEP2
    if pos + 3 > len(bits):
        return None
    r.pos = pos + 3
    return _TOKEN_BY_BITS[bits[pos:pos + 3]]


def _part_read(r: _Reader) -> Part:
    index = _varint_read(r)
    if r.take(1) == "1":
        value = _varint_read(r)
        if r.take(3) != "000":
            raise SerialError("malformed serial: bad terminator after an integer part")
        return Part(index, SUBTYPE_INT, value)
    flag = r.take(2)
    if flag == "10":
        return Part(index)
    if flag == "01":
        if _next_token(r) != TOK_SEP2:
            raise SerialError("malformed serial: part list does not start with ','")
        values = []
        while True:
            tok = _next_token(r)
            if tok == TOK_SEP1:
                return Part(index, SUBTYPE_LIST, 0, tuple(values))
            if tok == TOK_VARINT:
                values.append(_varint_read(r))
            elif tok == TOK_VARBIT:
                values.append(_varbit_read(r))
            else:
                raise SerialError("malformed serial: unexpected token inside a part list")
    raise SerialError("malformed serial: unknown part flag %s" % flag)


_MAGIC_BITS = "0010000"


def decode_blocks(serial: str) -> Tuple[Block, ...]:
    """'@U...' -> blocks. Raises SerialError for anything that is not a complete serial.

    Strictness beyond legacy (never triggers on a well-formed serial): foreign characters are
    rejected rather than skipped, bits left over after the last token must be zero padding, and the
    block list must end with the '|' terminator (a serial cut off mid-stream is an error).
    """
    r = _Reader(b85_decode(serial))
    if r.take(7) != _MAGIC_BITS:
        raise SerialError("not a Borderlands 4 item serial (bad header bits)")
    blocks = []
    trailing = 0
    while True:
        start = r.pos
        tok = _next_token(r)
        if tok is None:
            if "1" in r.bits[start:]:
                raise SerialError("serial is truncated: incomplete token at the end")
            break
        if tok == TOK_SEP1:
            trailing += 1
            blocks.append(Block(TOK_SEP1))
            continue
        trailing = 0
        if tok == TOK_SEP2:
            blocks.append(Block(TOK_SEP2))
        elif tok == TOK_VARINT:
            blocks.append(Block(TOK_VARINT, _varint_read(r)))
        elif tok == TOK_VARBIT:
            blocks.append(Block(TOK_VARBIT, _varbit_read(r)))
        elif tok == TOK_PART:
            blocks.append(Block(TOK_PART, part=_part_read(r)))
        else:  # TOK_STRING
            blocks.append(Block(TOK_STRING, value_str=_string_read(r)))
    # Zero padding at the end of the last byte reads as extra '|' tokens; keep exactly one.
    if trailing > 1:
        del blocks[len(blocks) - (trailing - 1):]
    if not blocks or blocks[-1].token != TOK_SEP1:
        raise SerialError("serial is truncated: the final '|' terminator is missing")
    return tuple(blocks)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _varint_bits(value: int) -> str:
    groups = max(1, (value.bit_length() + 3) // 4)
    out = []
    for g in range(groups):
        out.append(_LSB4[(value >> (4 * g)) & 15])
        out.append("1" if g < groups - 1 else "0")
    return "".join(out)


def _varbit_bits(value: int) -> str:
    n = value.bit_length()
    return _LSB5[n] + (format(value, "b")[::-1] if n else "")


def best_int_token(value: int) -> int:
    """VARBIT only when strictly shorter than VARINT (or when VARINT cannot hold the value)."""
    if value > MAX_VARINT:
        return TOK_VARBIT
    n = value.bit_length()
    return TOK_VARBIT if 5 * max(1, (n + 3) // 4) > 5 + n else TOK_VARINT


def int_block(value: object, what: str = "value") -> Block:
    """A fresh integer block holding `value` in whichever token encodes it shortest."""
    if not is_int(value) or value < 0 or value > MAX_VARBIT:
        raise SerialError("%s must be an integer in 0..%d, got %s" % (what, MAX_VARBIT, show(value)))
    return Block(best_int_token(value), value)


def _check_range(value: object, hi: int, what: str) -> None:
    if not is_int(value) or value < 0 or value > hi:
        raise SerialError("%s must be an integer in 0..%d, got %s" % (what, hi, show(value)))


def _validate_block(blk: object, where: str) -> None:
    if not isinstance(blk, Block):
        raise SerialError("%s is not a Block (got %s)" % (where, type(blk).__name__))
    tok = blk.token
    if tok in (TOK_SEP1, TOK_SEP2):
        return
    if tok == TOK_VARINT:
        _check_range(blk.value, MAX_VARINT, where + " (nibble varint)")
    elif tok == TOK_VARBIT:
        _check_range(blk.value, MAX_VARBIT, where + " (varbit)")
    elif tok == TOK_STRING:
        s = blk.value_str
        if not isinstance(s, str):
            raise SerialError("%s: string block needs a str value_str" % where)
        if len(s) > MAX_STRING_LEN:
            raise SerialError("%s: string is longer than %d characters" % (where, MAX_STRING_LEN))
        if any(ord(c) > 127 for c in s):
            raise SerialError("%s: serial strings are 7-bit ASCII only" % where)
    elif tok == TOK_PART:
        p = blk.part
        if not isinstance(p, Part):
            raise SerialError("%s: part block has no Part" % where)
        _check_range(p.index, MAX_VARINT, where + " part index")
        if p.subtype == SUBTYPE_NONE:
            return
        if p.subtype == SUBTYPE_INT:
            _check_range(p.value, MAX_VARINT, where + " part value")
        elif p.subtype == SUBTYPE_LIST:
            if not isinstance(p.values, (tuple, list)):
                raise SerialError("%s: part list values must be a tuple of integers" % where)
            for v in p.values:
                _check_range(v, MAX_VARBIT, where + " part list value")
        else:
            raise SerialError("%s: unknown part subtype %s" % (where, show(p.subtype)))
    else:
        raise SerialError("%s: unknown token %s" % (where, show(tok)))


def _as_block_seq(blocks: object) -> Sequence[Block]:
    if not isinstance(blocks, (tuple, list)):
        raise SerialError("expected Blocks (a tuple of Block), got %s" % type(blocks).__name__)
    return blocks


def encode_blocks(blocks: Sequence[Block]) -> str:
    """blocks -> '@U...'. Refuses blocks that could not be read back (see CONTRACT.md)."""
    seq = _as_block_seq(blocks)
    if not seq:
        raise SerialError("cannot encode an empty block list")
    out = [_MAGIC_BITS]
    for i, blk in enumerate(seq):
        _validate_block(blk, "blocks[%d]" % i)
        tok = blk.token
        if tok == TOK_SEP1:
            out.append("00")
        elif tok == TOK_SEP2:
            out.append("01")
        elif tok == TOK_VARINT:
            out.append("100" + _varint_bits(blk.value))
        elif tok == TOK_VARBIT:
            out.append("110" + _varbit_bits(blk.value))
        elif tok == TOK_STRING:
            s = blk.value_str
            out.append("111" + _varint_bits(len(s)) + "".join([_CHAR7[ord(c)] for c in s]))
        else:  # TOK_PART
            p = blk.part
            out.append("101" + _varint_bits(p.index))
            if p.subtype == SUBTYPE_NONE:
                out.append("010")
            elif p.subtype == SUBTYPE_INT:
                out.append("1" + _varint_bits(p.value) + "000")
            else:
                out.append("001" + "01")
                for v in p.values:
                    if best_int_token(v) == TOK_VARBIT:
                        out.append("110" + _varbit_bits(v))
                    else:
                        out.append("100" + _varint_bits(v))
                out.append("00")
    if seq[-1].token != TOK_SEP1:
        raise SerialError("blocks must end with the '|' terminator (TOK_SEP1); a serial without one "
                          "cannot be read back")
    bits = "".join(out)
    bits += "0" * (-len(bits) % 8)
    return b85_encode(int(bits, 2).to_bytes(len(bits) // 8, "big"))


# ---------------------------------------------------------------------------
# Text form:  "3, 0, 1, 50| 2, 1348|| {78} {2:5} {234:[7 67]} "NAME"|"
# ---------------------------------------------------------------------------
def parts_string(blocks: Sequence[Block]) -> str:
    seq = _as_block_seq(blocks)
    out = []
    for i, b in enumerate(seq):
        if not isinstance(b, Block):
            raise SerialError("blocks[%d] is not a Block (got %s)" % (i, type(b).__name__))
        tok = b.token
        if tok == TOK_SEP1:
            out.append("|")
            continue
        if tok == TOK_SEP2:
            out.append(",")
            continue
        if i > 0:
            out.append(" ")
        if tok in _INT_TOKENS:
            _check_range(b.value, MAX_VARBIT, "blocks[%d] value" % i)
            out.append(str(b.value))
        elif tok == TOK_PART:
            p = b.part
            if not isinstance(p, Part):
                raise SerialError("blocks[%d]: part block has no Part" % i)
            _check_range(p.index, MAX_VARBIT, "blocks[%d] part index" % i)
            if p.subtype == SUBTYPE_NONE:
                out.append("{%d}" % p.index)
            elif p.subtype == SUBTYPE_INT:
                _check_range(p.value, MAX_VARBIT, "blocks[%d] part value" % i)
                out.append("{%d:%d}" % (p.index, p.value))
            elif p.subtype == SUBTYPE_LIST:
                if not isinstance(p.values, (tuple, list)):
                    raise SerialError("blocks[%d]: part list values must be a tuple of integers" % i)
                for v in p.values:
                    _check_range(v, MAX_VARBIT, "blocks[%d] part list value" % i)
                out.append("{%d:[%s]}" % (p.index, " ".join([str(v) for v in p.values])))
            else:
                raise SerialError("blocks[%d]: unknown part subtype %s" % (i, show(p.subtype)))
        elif tok == TOK_STRING:
            if not isinstance(b.value_str, str):
                raise SerialError("blocks[%d]: string block needs a str value_str" % i)
            out.append('"' + b.value_str.replace("\\", "\\\\").replace('"', '\\"') + '"')
        else:
            raise SerialError("blocks[%d]: unknown token %s" % (i, show(tok)))
    return "".join(out)


def _digits_only(s: str) -> Optional[int]:
    s = s.strip()
    if not s or len(s) > 10 or any(c < "0" or c > "9" for c in s):
        return None
    return int(s)


def _parse_part(part_str: str) -> Part:
    inner = part_str[1:-1].strip()
    if ":" in inner:
        idx_str, rest = inner.split(":", 1)
        idx = _digits_only(idx_str)
        if idx is None:
            raise SerialError("invalid part index in %s" % show(part_str))
        rest = rest.strip()
        if rest.startswith("[") and rest.endswith("]"):
            vals = []
            for x in rest[1:-1].split():
                v = _digits_only(x)
                if v is None:
                    raise SerialError("invalid part list value %s in %s" % (show(x), show(part_str)))
                vals.append(v)
            return Part(idx, SUBTYPE_LIST, 0, tuple(vals))
        v = _digits_only(rest)
        if v is None:
            raise SerialError("invalid part value in %s" % show(part_str))
        return Part(idx, SUBTYPE_INT, v)
    idx = _digits_only(inner)
    if idx is None:
        raise SerialError("invalid part %s" % show(part_str))
    return Part(idx)


def from_string(text: str) -> Tuple[Block, ...]:
    if not isinstance(text, str):
        raise SerialError("part string must be a str, got %s" % type(text).__name__)
    blocks = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\n\r":
            i += 1
        elif c == "|":
            blocks.append(Block(TOK_SEP1))
            i += 1
        elif c == ",":
            blocks.append(Block(TOK_SEP2))
            i += 1
        elif c == "{":
            end = text.find("}", i)
            if end == -1:
                raise SerialError("unmatched '{' at position %d" % i)
            blocks.append(Block(TOK_PART, part=_parse_part(text[i:end + 1])))
            i = end + 1
        elif "0" <= c <= "9":
            start = i
            while i < n and "0" <= text[i] <= "9":
                i += 1
            if i - start > 10:
                raise SerialError("number at position %d is too large" % start)
            blocks.append(int_block(int(text[start:i]), "number at position %d" % start))
        elif c == '"':
            chars = []
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n and text[j + 1] in '\\"':
                    chars.append(text[j + 1])
                    j += 2
                else:
                    chars.append(text[j])
                    j += 1
            if j >= n:
                raise SerialError("unmatched '\"' at position %d" % i)
            blocks.append(Block(TOK_STRING, value_str="".join(chars)))
            i = j + 1
        else:
            raise SerialError("invalid character %s at position %d" % (show(c), i))
    for k, blk in enumerate(blocks):
        _validate_block(blk, "block %d" % k)
    return tuple(blocks)
