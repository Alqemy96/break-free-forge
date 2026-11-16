"""Tests for the `codec` module (src/bl4forge/modules/codec).

The legacy `bl4codec.py` is the parity oracle (fixture `legacy`); everything the contract promises
is compared against it over the whole community database (`all_serials`, 9,875 codes). Tests named
after CONTRACT.md "Invariants" come first; the rest pin the deliberate deviations and edge cases.
"""
import ast
import builtins
import copy
import dataclasses
import io
import os
import random
from pathlib import Path

import pytest

from bl4forge.core.errors import ForgeError, SerialError
from bl4forge.core.forge import Forge, OK
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import CodecPort
from bl4forge.core.types import (
    Block, Part, HealthReport, SUBTYPE_INT, SUBTYPE_LIST, SUBTYPE_NONE,
    TOK_PART, TOK_SEP1, TOK_SEP2, TOK_STRING, TOK_VARBIT, TOK_VARINT,
)
from bl4forge.modules import codec as codec_pkg
from bl4forge.modules.codec import MODULE, CodecModule, _known, _wire

SEED_POS = 5


# ---- fixtures -------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def codec(config):
    return CodecModule(ModuleContext("codec", config, {}))


@pytest.fixture(scope="module")
def decoded_all(codec, all_serials):
    return [codec.decode(s) for s in all_serials]


@pytest.fixture(scope="module")
def legacy_decoded(legacy, all_serials):
    return [legacy.codec.decode(s) for s in all_serials]


def shape(blocks):
    """Comparable plain-data view of either codec's blocks."""
    out = []
    for b in blocks:
        p = b.part
        out.append((b.token, b.value, b.value_str,
                    None if p is None else (p.index, p.subtype, p.value, tuple(p.values))))
    return out


def first_diff(pairs):
    """First (index, mine, theirs) where the two sequences disagree, else None."""
    for i, (a, b) in enumerate(pairs):
        if a != b:
            return i, a, b
    return None


# ---- invariants named in CONTRACT.md --------------------------------------------------------

def test_roundtrip_is_byte_identical(codec, all_serials, decoded_all):
    assert len(all_serials) == 9875
    diff = first_diff((codec.encode(b), s) for b, s in zip(decoded_all, all_serials))
    assert diff is None, "round trip differs at serial #%s: %r != %r" % diff


def test_decode_matches_legacy(legacy, codec, all_serials, decoded_all, legacy_decoded):
    mine = [codec.parts_string(b) for b in decoded_all]
    theirs = [legacy.codec.parts_string(b) for b in legacy_decoded]
    assert first_diff(zip(mine, theirs)) is None
    # and block by block, not just the printed form
    assert first_diff((shape(a), shape(b)) for a, b in zip(decoded_all, legacy_decoded)) is None
    # decode() is also what legacy's convenience wrapper returns
    for s in all_serials[::500]:
        assert codec.parts_string(codec.decode(s)) == legacy.codec.decode_to_string(s)


def test_relevel_matches_legacy(legacy, codec, all_serials, decoded_all):
    mine = [codec.relevel(s, 60) for s in all_serials]
    theirs = [legacy.codec.relevel(s, 60) for s in all_serials]
    assert first_diff(zip(mine, theirs)) is None
    assert all(codec.get_level(codec.decode(s)) == 60 for s in mine)
    # the item is otherwise untouched: only the level block differs
    for s, r, blocks in zip(all_serials[::50], mine[::50], decoded_all[::50]):
        after = codec.decode(r)
        assert len(after) == len(blocks)
        changed = [i for i, (a, b) in enumerate(zip(blocks, after)) if a != b]
        assert len(changed) <= 1
    # other levels agree with legacy too (all below the 16-bit limit legacy could represent)
    for s in all_serials[::40]:
        for lvl in (1, 30, 49, 50, 61, 255, 4095, 65535):
            assert codec.relevel(s, lvl) == legacy.codec.relevel(s, lvl)


def test_level_and_category_match_legacy(legacy, codec, decoded_all, legacy_decoded):
    lv = [(codec.get_level(a), legacy.codec.get_level(b)) for a, b in zip(decoded_all, legacy_decoded)]
    cat = [(codec.get_category_id(a), legacy.codec.get_manufacturer_index(b))
           for a, b in zip(decoded_all, legacy_decoded)]
    assert first_diff(lv) is None
    assert first_diff(cat) is None
    assert all(a is not None for a, _ in lv) and all(a is not None for a, _ in cat)


def test_seed_behaviour_matches_legacy(legacy, codec, all_serials, decoded_all, legacy_decoded):
    P = legacy.partsdb
    # reading: int_at agrees with legacy for every serial and every position (incl. past the end)
    for blocks, lb, s in zip(decoded_all, legacy_decoded, all_serials):
        assert codec.int_at(blocks, SEED_POS) == legacy.codec._int_at_pos(lb, SEED_POS)
    for blocks, lb in zip(decoded_all[::25], legacy_decoded[::25]):
        for pos in range(0, 40):
            assert codec.int_at(blocks, pos) == legacy.codec._int_at_pos(lb, pos)
    assert [codec.int_at(b, SEED_POS) for b in decoded_all[:50]] == [P.get_seed(s) for s in all_serials[:50]]
    # writing: with_int_at(5) + encode == legacy set_seed, for every serial
    mine = [codec.encode(codec.with_int_at(b, SEED_POS, 777)) for b in decoded_all]
    theirs = [P.set_seed(s, 777) for s in all_serials]
    assert first_diff(zip(mine, theirs)) is None
    # more values on a sample (all within what legacy can represent without wrapping)
    for s, b in zip(all_serials[::60], decoded_all[::60]):
        for v in (0, 1, 300, 4095, 4096, 12345, 65535):
            got = codec.encode(codec.with_int_at(b, SEED_POS, v))
            assert got == P.set_seed(s, v)
            assert codec.int_at(codec.decode(got), SEED_POS) == v
    # other positions: same as legacy's token re-selection
    for s, b in zip(all_serials[::200], decoded_all[::200]):
        for pos in (0, 1, 3, 6):
            lb = legacy.codec.decode(s)
            ints = [x for x in lb if x.token in (legacy.codec.TOK_VARINT, legacy.codec.TOK_VARBIT)]
            if pos >= len(ints):                 # legacy set_seed raises ValueError here; we raise SerialError
                with pytest.raises(SerialError):
                    codec.with_int_at(b, pos, 9)
                continue
            blk = ints[pos]
            blk.value = 9
            blk.token = legacy.codec._best_type_for_value(9)
            assert codec.encode(codec.with_int_at(b, pos, 9)) == legacy.codec.encode(lb)


def test_from_string_parity_and_roundtrip(legacy, codec, all_serials, decoded_all):
    texts = [codec.parts_string(b) for b in decoded_all]
    # text -> blocks -> serial reproduces every database serial
    assert first_diff((codec.encode(codec.from_string(t)), s) for t, s in zip(texts, all_serials)) is None
    # and agrees with legacy's own text parser
    for t, s in zip(texts[::3], all_serials[::3]):
        assert shape(codec.from_string(t)) == shape(legacy.codec.from_string(t))
        assert codec.encode(codec.from_string(t)) == legacy.codec.encode_from_string(t)


def test_pure(codec, all_serials, decoded_all, monkeypatch):
    blocks = decoded_all[0]
    # immutable values: tuples of frozen dataclasses, all the way down
    assert isinstance(blocks, tuple)
    for b in decoded_all[:300]:
        assert isinstance(b, tuple)
        for blk in b:
            assert isinstance(blk, Block) and dataclasses.is_dataclass(blk)
            with pytest.raises(dataclasses.FrozenInstanceError):
                blk.value = 1
            if blk.part is not None:
                assert isinstance(blk.part, Part) and isinstance(blk.part.values, tuple)
                with pytest.raises(dataclasses.FrozenInstanceError):
                    blk.part.index = 1
    with pytest.raises(TypeError):
        blocks[0] = Block(TOK_SEP1)            # type: ignore[index]

    # inputs are never modified; transforms return new tuples
    for s, b in list(zip(all_serials, decoded_all))[::97]:
        snap = copy.deepcopy(b)
        again = codec.decode(s)
        assert again == b and again is not b
        codec.encode(b)
        codec.parts_string(b)
        codec.get_level(b)
        codec.get_category_id(b)
        codec.int_at(b, SEED_POS)
        out = codec.with_int_at(b, SEED_POS, 1)
        assert isinstance(out, tuple) and out is not b
        assert b == snap and shape(b) == shape(snap)
        assert codec.int_at(out, SEED_POS) == 1
        as_list = list(b)
        codec.encode(as_list)
        codec.with_int_at(as_list, SEED_POS, 2)
        assert as_list == list(snap)           # a list passed in is left alone too
        codec.relevel(s, 60)

    # no file access at all, health() included
    def boom(*a, **k):
        raise AssertionError("codec touched the filesystem")
    with monkeypatch.context() as m:
        for mod, attr in ((builtins, "open"), (io, "open"), (os, "open"), (os, "stat"),
                          (os, "listdir"), (os, "scandir")):
            m.setattr(mod, attr, boom)
        s = all_serials[10]
        b = codec.decode(s)
        codec.from_string(codec.parts_string(b))
        codec.encode(b)
        codec.relevel(s, 60)
        codec.with_int_at(b, SEED_POS, 3)
        assert codec.health().ok

    # no per-instance state beyond the framework's, so two instances cannot interfere
    other = CodecModule(codec.ctx)
    assert set(vars(codec)) <= {"ctx", "config"}
    assert codec.decode(all_serials[1]) == other.decode(all_serials[1])


def test_pure_no_module_level_mutable_state():
    import bl4forge.modules.codec._known as known_mod
    import bl4forge.modules.codec._wire as wire_mod
    for mod in (codec_pkg, wire_mod, known_mod):
        for name, val in vars(mod).items():
            if name.startswith("__"):
                continue
            assert not isinstance(val, (list, dict, set, bytearray)), "%s.%s is mutable" % (mod.__name__, name)
    for name, val in vars(CodecModule).items():
        if not name.startswith("__"):
            assert not isinstance(val, (list, dict, set, bytearray)), "CodecModule.%s is mutable" % name


def test_pure_stdlib_only_and_leaf_imports():
    """Static check: nothing but typing helpers from the stdlib, and only `core` from the framework."""
    pkg_dir = Path(codec_pkg.__file__).parent
    for path in pkg_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] in {"types", "typing"}, (path.name, a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    assert node.module.split(".")[0] in {"__future__", "types", "typing"}, (path.name, node.module)
                elif node.level == 1:
                    pass                                    # sibling file inside this package
                else:
                    assert node.level == 3 and (node.module or "").split(".")[0] == "core", (path.name, node.module)


GARBAGE = [
    "", " ", "@", "@U", "U", "@u", "hello", "not a serial at all", "@Uhello", "@U!!!!!", "@Uzzzz", "@U ",
    "@U\n", "@U~~~~~~~~", "@U\"\"\"\"", "\x00\x01\x02", "@U\u00e9\u00e9\u00e9", "\u2603" * 20,
    "@U" + "0" * 200, "@U" + "~" * 200, " @U" + "0" * 20,
]
NOT_STRINGS = [None, 5, 5.5, b"@Uabc", ["@U"], ("@U",), object()]


@pytest.mark.parametrize("bad", GARBAGE)
def test_errors_are_serialerror(codec, bad):
    with pytest.raises(SerialError):
        codec.decode(bad)
    with pytest.raises(SerialError):
        codec.relevel(bad, 60)


@pytest.mark.parametrize("bad", NOT_STRINGS)
def test_errors_are_serialerror_for_non_strings(codec, bad):
    for call in (lambda: codec.decode(bad), lambda: codec.relevel(bad, 60), lambda: codec.from_string(bad)):
        with pytest.raises(SerialError):
            call()
    for call in (lambda: codec.encode(bad), lambda: codec.parts_string(bad), lambda: codec.get_level(bad),
                 lambda: codec.get_category_id(bad), lambda: codec.int_at(bad, 0),
                 lambda: codec.with_int_at(bad, 0, 1)):
        with pytest.raises(SerialError):
            call()


def test_errors_are_serialerror_truncated(codec, all_serials):
    unique = sorted(set(all_serials))
    for s in unique[::3]:
        for k in (1, 2, 3):                      # cutting the tail always loses the '|' terminator
            with pytest.raises(SerialError):
                codec.decode(s[:-k])
        with pytest.raises(SerialError):
            codec.decode(s[:len(s) // 2 | 1])    # cut in the middle (odd length keeps a stray group)
    # every possible prefix of a few serials: SerialError or a complete serial, never anything else
    for s in unique[::900]:
        for n in range(len(s)):
            try:
                blocks = codec.decode(s[:n])
            except SerialError:
                continue
            assert blocks[-1].token == TOK_SEP1
            assert codec.decode(codec.encode(blocks)) == blocks


def test_errors_are_serialerror_fuzz(codec, all_serials):
    rnd = random.Random(20260110)
    unique = sorted(set(all_serials))
    charset = _wire.B85_CHARSET
    raised = decoded = 0

    def check(text):
        nonlocal raised, decoded
        try:
            blocks = codec.decode(text)
        except SerialError:
            raised += 1
            return
        decoded += 1
        again = codec.encode(blocks)                 # anything decodable must re-encode...
        assert codec.decode(again) == blocks         # ...and read back identically
        codec.parts_string(blocks)
        codec.get_level(blocks)
        codec.get_category_id(blocks)

    for _ in range(1500):                            # random text, with and without the right prefix
        n = rnd.randrange(0, 80)
        check("".join(rnd.choice(charset) for _ in range(n)))
        check("@U" + "".join(rnd.choice(charset) for _ in range(n)))
        check("".join(chr(rnd.randrange(0, 0x250)) for _ in range(n)))
    for _ in range(2500):                            # mutated real serials
        s = rnd.choice(unique)
        i = rnd.randrange(2, len(s))
        kind = rnd.randrange(5)
        if kind == 0:
            s = s[:i] + rnd.choice(charset) + s[i + 1:]
        elif kind == 1:
            s = s[:i] + s[i + 1:]
        elif kind == 2:
            s = s[:i] + rnd.choice(charset) + s[i:]
        elif kind == 3:
            s = s[:i]
        else:
            s = s + "".join(rnd.choice(charset) for _ in range(rnd.randrange(1, 9)))
        check(s)
    assert raised > 1000 and decoded > 100           # the fuzz exercised both outcomes


BAD_BLOCKS = [
    (),                                                   # empty
    (Block(TOK_VARINT, 5),),                              # no terminator
    (Block(TOK_SEP1), Block(TOK_SEP2)),                   # ends on ','
    (Block(99), Block(TOK_SEP1)),                         # unknown token
    (Block(TOK_PART), Block(TOK_SEP1)),                   # part token without a Part
    (Block(TOK_PART, part=Part(1, 7)), Block(TOK_SEP1)),  # unknown part subtype
    (Block(TOK_VARINT, -1), Block(TOK_SEP1)),
    (Block(TOK_VARINT, 65536), Block(TOK_SEP1)),          # does not fit a nibble varint
    (Block(TOK_VARBIT, 2 ** 31), Block(TOK_SEP1)),        # does not fit a 31-bit varbit
    (Block(TOK_VARINT, "5"), Block(TOK_SEP1)),
    (Block(TOK_VARINT, True), Block(TOK_SEP1)),
    (Block(TOK_VARINT, 1.5), Block(TOK_SEP1)),
    (Block(TOK_VARINT, 10 ** 5000), Block(TOK_SEP1)),       # huge: error text must not blow up either
    (Block(TOK_VARBIT, -10 ** 5000), Block(TOK_SEP1)),
    (Block(TOK_STRING, value_str="caf\u00e9"), Block(TOK_SEP1)),   # not 7-bit
    (Block(TOK_STRING, value_str=None), Block(TOK_SEP1)),
    (Block(TOK_PART, part=Part(70000)), Block(TOK_SEP1)),
    (Block(TOK_PART, part=Part(1, SUBTYPE_INT, 70000)), Block(TOK_SEP1)),
    (Block(TOK_PART, part=Part(1, SUBTYPE_LIST, 0, (1, -2))), Block(TOK_SEP1)),
    (Block(TOK_PART, part=Part(1, SUBTYPE_LIST, 0, (2 ** 31,))), Block(TOK_SEP1)),
    (Block(TOK_PART, part=Part(1, SUBTYPE_LIST, 0, 5)), Block(TOK_SEP1)),
    ("not a block", Block(TOK_SEP1)),
    (None, Block(TOK_SEP1)),
]


@pytest.mark.parametrize("bad", BAD_BLOCKS)
def test_errors_are_serialerror_for_bad_blocks(codec, bad):
    with pytest.raises(SerialError):
        codec.encode(bad)


@pytest.mark.parametrize("text", [
    "{", "{1", "{1:}", "{:1}", "{a}", "{1:[a b]}", "{1:[1,2]}", "{1:2:3}", "{-1}", "{1:-2}", '"abc', "abc", "1.5",
    "9" * 5000, "{" + "1" * 5000 + "}", "{1:[" + "1" * 5000 + "]}", "99999999999", "2147483648", "123456789012345", "{70000}", "{1:70000}", "{1:[2147483648]}", "#", "1 2 @",
    '"caf\u00e9"', "\u0661\u0662", "-5", "{\u0661}",
])
def test_errors_are_serialerror_for_bad_text(codec, text):
    with pytest.raises(SerialError):
        codec.from_string(text)


@pytest.mark.parametrize("bad", BAD_BLOCKS[3:6] + BAD_BLOCKS[8:9] + BAD_BLOCKS[10:14])
def test_errors_are_serialerror_for_parts_string(codec, bad):
    with pytest.raises(SerialError):
        codec.parts_string(bad)


def test_serialerror_is_a_forgeerror(codec):
    with pytest.raises(ForgeError):
        codec.decode("")


def test_only_serialerror_escapes_any_method(codec, all_serials):
    """Throw every kind of argument at every method: nothing but SerialError may come out."""
    s = all_serials[0]
    blocks = codec.decode(s)
    args = [None, 0, -1, 7, 2 ** 31, 2 ** 40, 10 ** 5000, -10 ** 5000, True, 1.5, "x", "", b"b", [], (), {}, blocks, list(blocks), s,
            Block(TOK_SEP1), object()]
    methods = {
        "decode": 1, "encode": 1, "parts_string": 1, "from_string": 1, "get_level": 1, "get_category_id": 1,
        "relevel": 2, "int_at": 2, "with_int_at": 3,
    }
    import itertools
    for name, arity in methods.items():
        fn = getattr(codec, name)
        for combo in itertools.product(args, repeat=arity):
            try:
                fn(*combo)
            except SerialError:
                pass


# ---- conformance, doctor, health ------------------------------------------------------------

def test_conforms_to_port(codec):
    assert MODULE is CodecModule
    assert isinstance(codec, CodecPort)
    assert conformance_problems(codec, CodecPort) == []
    assert (CodecModule.name, CodecModule.requires, CodecModule.port) == ("codec", (), CodecPort)
    assert CodecModule.purpose == "Turn '@U...' serials into bitstream blocks and back, bit-exactly."


def test_forge_marks_codec_ok(config):
    f = Forge.build(config, only=["codec"])
    st = f.states["codec"]
    assert st.state == OK, st.detail
    assert len(st.health.checks) >= 3 and all(c.ok for c in st.health.checks)
    assert f.module("codec").decode(_known.KNOWN_SERIALS[0][1])


def test_health_known_answers_are_real_database_serials(legacy, codec, all_serials):
    assert len(_known.KNOWN_SERIALS) >= 3
    db = set(all_serials)
    for label, serial, level, category, seed, text in _known.KNOWN_SERIALS:
        assert serial in db, label
        lb = legacy.codec.decode(serial)
        assert (level, category, seed, text) == (
            legacy.codec.get_level(lb), legacy.codec.get_manufacturer_index(lb),
            legacy.codec._int_at_pos(lb, SEED_POS), legacy.codec.parts_string(lb)), label
    h = codec.health()
    assert isinstance(h, HealthReport) and h.ok
    assert sum(1 for c in h.checks if c.name.startswith("known-answer")) >= 3


def test_health_reports_a_sick_codec_instead_of_raising(config):
    class Broken(CodecModule):
        def decode(self, serial):
            raise RuntimeError("boom")

    class WrongAnswers(CodecModule):
        def get_level(self, blocks):
            return 1

    rep = Broken(ModuleContext("codec", config, {})).health()
    assert rep.ok is False and any(not c.ok for c in rep.checks)
    rep = WrongAnswers(ModuleContext("codec", config, {})).health()
    assert rep.ok is False and "failed" in rep.summary


def test_health_is_fast(codec):
    import time
    t = time.perf_counter()
    for _ in range(5):
        assert codec.health().ok
    assert (time.perf_counter() - t) / 5 < 0.5


# ---- writer parity on synthetic streams (features the database may not exercise) ------------

def _rand_int(rnd, hi):
    return rnd.getrandbits(rnd.randint(0, hi.bit_length())) % (hi + 1)


def _random_blocks(rnd, legacy_limit=True):
    """A random valid block stream: (my blocks, legacy blocks). List values stay within 16 bits when
    `legacy_limit` because legacy silently truncates larger ones (see test_large_values...)."""
    mine = []
    for _ in range(rnd.randint(0, 25)):
        kind = rnd.choice("ssvbbpppt")
        if kind == "s":
            mine.append(Block(rnd.choice((TOK_SEP1, TOK_SEP2))))
        elif kind == "v":
            mine.append(Block(TOK_VARINT, _rand_int(rnd, 0xFFFF)))
        elif kind == "b":
            mine.append(Block(TOK_VARBIT, _rand_int(rnd, 0x7FFFFFFF)))
        elif kind == "t":
            n = rnd.randint(0, 20)
            mine.append(Block(TOK_STRING, value_str="".join(chr(rnd.randrange(0, 128)) for _ in range(n))))
        else:
            sub = rnd.choice((SUBTYPE_NONE, SUBTYPE_INT, SUBTYPE_LIST))
            idx = _rand_int(rnd, 0xFFFF)
            if sub == SUBTYPE_NONE:
                part = Part(idx)
            elif sub == SUBTYPE_INT:
                part = Part(idx, SUBTYPE_INT, _rand_int(rnd, 0xFFFF))
            else:
                hi = 0xFFFF if legacy_limit else 0x7FFFFFFF
                part = Part(idx, SUBTYPE_LIST, 0, tuple(_rand_int(rnd, hi) for _ in range(rnd.randint(0, 6))))
            mine.append(Block(TOK_PART, part=part))
    mine.append(Block(TOK_SEP2))                 # never end on two terminators (decode trims them)
    mine.append(Block(TOK_SEP1))
    return tuple(mine)


def _to_legacy(C, blocks):
    out = []
    for b in blocks:
        p = b.part
        lp = None if p is None else C.Part(p.index, p.subtype, p.value, list(p.values))
        out.append(C.Block(b.token, b.value, b.value_str, lp))
    return out


def test_encode_matches_legacy_on_random_streams(legacy, codec):
    rnd = random.Random(424242)
    for _ in range(600):
        blocks = _random_blocks(rnd)
        serial = codec.encode(blocks)
        assert serial == legacy.codec.encode(_to_legacy(legacy.codec, blocks))
        assert codec.decode(serial) == blocks
        assert shape(legacy.codec.decode(serial)) == shape(blocks)
        assert codec.parts_string(blocks) == legacy.codec.parts_string(_to_legacy(legacy.codec, blocks))
        canon = tuple(Block(_wire.best_int_token(b.value), b.value) if b.token in (TOK_VARINT, TOK_VARBIT) else b
                      for b in blocks)            # text carries no token type: it re-picks the shortest
        assert codec.encode(codec.from_string(codec.parts_string(canon))) == codec.encode(canon)


def test_every_token_and_subtype_roundtrips(codec):
    text = ('7, 0, 1, 50| 2, 100|| {1} {2:3} {4:[5 6 300 70000]} "Some.String_1" 5000 {9:[]} 255 256 511 '
            '16383 16384 65535 70000 2147483647|')
    blocks = codec.from_string(text)
    tokens = [b.token for b in blocks]
    assert {TOK_SEP1, TOK_SEP2, TOK_VARINT, TOK_VARBIT, TOK_PART, TOK_STRING} <= set(tokens)
    again = codec.decode(codec.encode(blocks))
    assert again == blocks
    assert codec.parts_string(again) == codec.parts_string(blocks)
    assert [b.value for b in again if b.token in (TOK_VARINT, TOK_VARBIT)][-4:] == [16384, 65535, 70000, 2147483647]


# ---- level / seed helpers: edge cases -------------------------------------------------------

def test_level_location_rules_match_legacy_on_odd_headers(legacy, codec):
    # [category, 0, MARKER(1), LEVEL ...]: the marker may sit at a later even position, may be absent,
    # or may be the last integer (no level after it).
    for text in ["5, 0, 1, 33| 2, 9|", "5, 0, 7, 8, 1, 44| 2, 1|", "5, 0, 7| 2, 3|", "1, 0, 1|", "|", "",
                 "1, 1, 1, 1, 1, 1|", "5, 0, 1, 33, 1, 12|", "5, 0, 6, 0, 1, 9|", "9 8|"]:
        blocks = codec.from_string(text)
        lb = legacy.codec.from_string(text)
        assert codec.get_level(blocks) == legacy.codec.get_level(lb), text
        assert codec.get_category_id(blocks) == legacy.codec.get_manufacturer_index(lb), text
        for pos in range(-1, 9):
            assert codec.int_at(blocks, pos) == legacy.codec._int_at_pos(lb, pos if pos >= 0 else pos), text


def test_relevel_without_a_level_raises(codec):
    for text in ["5, 0, 7| 2, 3|", "1, 0, 1|", "|"]:
        s = codec.encode(codec.from_string(text))
        assert codec.get_level(codec.decode(s)) is None
        with pytest.raises(SerialError):
            codec.relevel(s, 60)


def test_int_at_and_with_int_at_edges(codec, all_serials):
    blocks = codec.decode(all_serials[0])
    n_ints = sum(1 for b in blocks if b.token in (TOK_VARINT, TOK_VARBIT))
    assert codec.int_at(blocks, n_ints) is None and codec.int_at(blocks, -1) is None
    assert codec.int_at((), 0) is None
    for bad in (n_ints, n_ints + 5, -1):
        with pytest.raises(SerialError):
            codec.with_int_at(blocks, bad, 1)
    for bad_pos in ("5", 5.0, None, True):
        with pytest.raises(SerialError):
            codec.int_at(blocks, bad_pos)
        with pytest.raises(SerialError):
            codec.with_int_at(blocks, bad_pos, 1)
    for bad_val in (-1, 2 ** 31, "7", 7.0, None, True):
        with pytest.raises(SerialError):
            codec.with_int_at(blocks, SEED_POS, bad_val)
    # only the one block changes, everything else (and the length) is identical
    out = codec.with_int_at(blocks, SEED_POS, 321)
    assert len(out) == len(blocks)
    assert [i for i, (a, b) in enumerate(zip(blocks, out)) if a != b] == [
        [i for i, b in enumerate(blocks) if b.token in (TOK_VARINT, TOK_VARBIT)][SEED_POS]]


# ---- deliberate deviations from legacy (each is listed in CONTRACT.md) ----------------------

def test_large_values_are_lossless_where_legacy_wraps(legacy, codec, all_serials):
    s = all_serials[0]
    for v in (65536, 100000, 2 ** 24 + 5, 2 ** 31 - 1):
        out = codec.relevel(s, v)
        assert codec.get_level(codec.decode(out)) == v
        assert codec.encode(codec.decode(out)) == out
        seeded = codec.encode(codec.with_int_at(codec.decode(s), SEED_POS, v))
        assert codec.int_at(codec.decode(seeded), SEED_POS) == v
        # legacy silently keeps only the low 16 bits (a corrupted level / seed)
        lb = legacy.codec.decode(legacy.codec.relevel(s, v))
        assert legacy.codec.get_level(lb) == v & 0xFFFF != v
    assert codec.decode(codec.relevel(s, 65536))[0] == codec.decode(s)[0]
    # list-part values above 16 bits are also kept (legacy truncates them)
    blocks = codec.from_string("1, 0, 1, 50| {7:[70000 5]}|")
    assert codec.decode(codec.encode(blocks)) == blocks


@pytest.mark.parametrize("bad", [-1, 2 ** 31, 2 ** 32, 2 ** 40, True, False, 60.0, "60", None, [60]])
def test_relevel_rejects_unrepresentable_levels(codec, all_serials, bad):
    with pytest.raises(SerialError):
        codec.relevel(all_serials[0], bad)


def test_relevel_zero_and_max_work(codec, all_serials):
    for lvl in (0, 1, 2 ** 31 - 1):
        assert codec.get_level(codec.decode(codec.relevel(all_serials[3], lvl))) == lvl


def test_foreign_characters_are_rejected_where_legacy_skipped_them(legacy, codec, all_serials):
    s = all_serials[0]
    for junk in (" ", "\n", '"', "'", ".", "\\", "\t", "\u00e9"):
        dirty = s[:12] + junk + s[12:]
        if junk != "\u00e9":                                                # (legacy crashes on that one)
            assert legacy.codec.encode(legacy.codec.decode(dirty)) == s    # legacy: shrugs it off
        with pytest.raises(SerialError):
            codec.decode(dirty)
    with pytest.raises(SerialError):
        codec.decode(s[:12] + "\u200b" + s[12:])
    for dirty in (s + "\n", s + " ", " " + s):
        with pytest.raises(SerialError):
            codec.decode(dirty)
    assert codec.decode(s.strip()) == codec.decode(s)


def test_incomplete_serials_are_rejected_where_legacy_returned_a_prefix(legacy, codec, all_serials):
    # Cutting the last base85 group short: legacy hands back whatever blocks parsed so far.
    found = 0
    for s in all_serials[:200]:
        for k in range(1, 9):
            cut = s[:-k]
            try:
                legacy_blocks = legacy.codec.decode(cut)
            except ValueError:
                continue
            if legacy_blocks and legacy_blocks[-1].token != TOK_SEP1:
                found += 1
                with pytest.raises(SerialError):
                    codec.decode(cut)
    assert found > 50                           # the oracle really does accept plenty of cut-off serials


def test_encode_requires_the_terminator(legacy, codec):
    text = "5, 0, 1, 40| 2, 9"
    assert legacy.codec.encode_from_string(text)            # legacy convenience appends '|' silently
    blocks = codec.from_string(text)
    with pytest.raises(SerialError):
        codec.encode(blocks)
    assert codec.encode(codec.from_string(text + "|")) == legacy.codec.encode_from_string(text)


def test_strings_with_quotes_and_backslashes_roundtrip(codec):
    for value in ['plain', 'with "quotes"', 'back\\slash', 'ends with backslash\\', '\\"', '\\\\', '"', '', 'a b']:
        blocks = (Block(TOK_STRING, value_str=value), Block(TOK_SEP1))
        text = codec.parts_string(blocks)
        assert codec.from_string(text) == blocks, value
        assert codec.decode(codec.encode(blocks)) == blocks, value


def test_part_text_is_forgiving_about_whitespace_like_legacy(legacy, codec):
    for text in ["{ 12 }", "{12 :[ 1  2 ]}", "{ 3 : 4 }", "1,2 |\n\t3|", "  {7}  |  "]:
        assert shape(codec.from_string(text)) == shape(legacy.codec.from_string(text)), text
