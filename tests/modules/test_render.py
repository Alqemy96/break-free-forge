"""render: tests named after the invariants in src/bl4forge/modules/render/CONTRACT.md."""
from __future__ import annotations

import os
import re
from html.parser import HTMLParser

import pytest

from bl4forge.core import vocab
from bl4forge.core.errors import ForgeError
from bl4forge.core.module import ModuleContext, conformance_problems
from bl4forge.core.ports import RenderPort
from bl4forge.core.types import Loadout, LoadoutItem
from bl4forge.modules.render import CSS, MODULE, RenderModule
from bl4forge.modules.render import style

SERIAL_A = "@Ugr$ZCm/&tH!t{KgK/Shxu>k"
SERIAL_B = "@Ugd_t@FkSI{$$tf{+yeEkmo"
SERIAL_C = "@Uge8;)m/)@{!tf/pN`tV-BQ?"


@pytest.fixture
def render(config):
    return RenderModule(ModuleContext("render", config, {}))


def item(name="Anarchy", serial=SERIAL_A, **kw):
    kw.setdefault("level", 60)
    return LoadoutItem(name=name, serial=serial, **kw)


def loadout(*items, title="Test Loadout", level=60, groups=(), **kw):
    return Loadout(title=title, level=level, items=tuple(items), groups=tuple(groups), **kw)


# ---- a tiny harvester for "what would a person see" -------------------------------------------
class Harvest(HTMLParser):
    """Collects the visible text of the elements the sheet cares about, plus every tag/attribute."""

    CLASSES = {"cname", "ctype", "serial", "cnote", "odds", "badge", "warn", "parts",
               "step", "tldr", "subtitle", "eyebrow"}
    TAGS = {"title", "h1", "h2", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records = []          # (key, text) in document order
        self.tags = []             # (tag, {attr: value})
        self._open = []            # [key, depth, chunks]

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        for o in self._open:
            o[1] += 1
        classes = (dict(attrs).get("class") or "").split()
        key = next((c for c in classes if c in self.CLASSES), None) or (tag if tag in self.TAGS else None)
        if key:
            self._open.append([key, 1, []])

    def handle_endtag(self, tag):
        for o in self._open:
            o[1] -= 1
        while self._open and self._open[-1][1] == 0:
            key, _, chunks = self._open.pop()
            self.records.append((key, " ".join("".join(chunks).split())))

    def handle_data(self, data):
        for o in self._open:
            o[2].append(data)


def harvest(doc):
    h = Harvest()
    h.feed(doc)
    h.close()
    return h


CARD_KEYS = ("cname", "badge", "ctype", "cnote", "odds", "parts", "serial")


def cards(h):
    """Group the harvested records into one dict per card (warnings kept apart)."""
    out, cur = [], None
    for key, text in h.records:
        if key == "cname":
            cur = {"cname": text}
            out.append(cur)
        elif key in CARD_KEYS and cur is not None:
            cur[key] = text
    return out


def chrome(h):
    return [(k, t) for k, t in h.records if k in ("title", "h1", "h2", "eyebrow", "subtitle", "tldr",
                                                   "step", "footer")]


# ============================ invariants ======================================================
PAYLOAD = '"><script>alert(1)</script><img src=x onerror=alert(1)>'
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "header", "div", "p", "h1", "h2",
                "span", "strong", "section", "code", "button", "details", "summary", "b", "em",
                "footer", "script"}


def hostile_loadout():
    it = LoadoutItem(
        name="N" + PAYLOAD, serial='@U"' + PAYLOAD, level=60, group="G" + PAYLOAD,
        display_name="D" + PAYLOAD, manufacturer="M" + PAYLOAD, label="L" + PAYLOAD,
        type="T" + PAYLOAD, weapon_type="W" + PAYLOAD, rarity="R" + PAYLOAD,
        element="E" + PAYLOAD, category="C" + PAYLOAD, legendary_name="LN" + PAYLOAD,
        parts=("P1" + PAYLOAD, "P2" + PAYLOAD), odds="O" + PAYLOAD, source="S" + PAYLOAD,
        note="note " + PAYLOAD + " <em>ok</em>", warnings=("W1" + PAYLOAD,))
    return Loadout(title="T" + PAYLOAD, level=60, items=(it,), groups=("G" + PAYLOAD, "Empty" + PAYLOAD),
                   unmatched=("U" + PAYLOAD,), warnings=("LW" + PAYLOAD,))


def test_escapes_everything(render):
    doc = render.html(hostile_loadout())
    # No injected markup: only the sheet's own tags, exactly one <script> (the copy helper).
    h = harvest(doc)
    tags = [t for t, _ in h.tags]
    assert set(tags) <= ALLOWED_TAGS, set(tags) - ALLOWED_TAGS
    assert tags.count("script") == 1
    assert "img" not in tags
    # Attributes are only the sheet's own: a quote in the serial cannot break out of data-s.
    for tag, attrs in h.tags:
        assert set(attrs) <= {"class", "lang", "charset", "name", "content", "onclick", "data-s"}, attrs
        if "onclick" in attrs:
            assert tag == "button" and attrs["onclick"] == "cp(this)"
    button = [a for t, a in h.tags if t == "button"][0]
    assert button["data-s"] == '@U"' + PAYLOAD            # round-trips exactly, as inert text
    # The payload is visible as TEXT in the places it was supplied.
    texts = " ".join(t for _, t in h.records)
    for marker in ("D" + PAYLOAD, "G" + PAYLOAD, "T" + PAYLOAD, "O" + PAYLOAD):
        assert marker in texts
    assert "<script>alert(1)</script>" not in doc.replace(CSS, "")  # only entity-escaped forms remain
    # ...and the single <em> allowed in a note survives.
    assert "<em>ok</em>" in doc


@pytest.mark.parametrize("note,expected", [
    ("a <em>b</em> c", "a <em>b</em> c"),
    ("<EM>x</EM>", "<em>x</em>"),
    ("<em>unclosed", "<em>unclosed</em>"),
    ("stray </em> here", "stray &lt;/em&gt; here"),
    ("<em onclick=x>y</em>", "&lt;em onclick=x&gt;y&lt;/em&gt;"),
    ("<b>bold</b> & <i>it</i>", "&lt;b&gt;bold&lt;/b&gt; &amp; &lt;i&gt;it&lt;/i&gt;"),
    ("&lt;em&gt;sneaky&lt;/em&gt;", "&amp;lt;em&amp;gt;sneaky&amp;lt;/em&amp;gt;"),
    ('say "hi"', "say &quot;hi&quot;"),
])
def test_escapes_everything_notes_allow_only_em(render, note, expected):
    doc = render.html(loadout(item(note=note)))
    assert '<p class="cnote">%s</p>' % expected in doc


def test_self_contained(render):
    lo = loadout(item(group="A", element="shock", odds="1 in 40", parts=("x", "y"), note="n"),
                 item("Two", SERIAL_B), groups=("A",), warnings=("w",), unmatched=("u",))
    doc = render.html(lo)
    assert not re.search(r"(?i)https?://|//cdn|<link|\bsrc\s*=|@import|url\(", doc)
    assert doc.count("<style>") == 1 and doc.count("<script>") == 1
    assert CSS in doc and style.COPY_JS in doc
    assert doc.startswith("<!DOCTYPE html>") and doc.rstrip().endswith("</html>")


def test_every_serial_present(render):
    items = [item("A1", SERIAL_A, group="One"), item("B1", SERIAL_B, group="Two"),
             item("C1", SERIAL_C), item("A2", SERIAL_A, group="One"),
             item("Stray", SERIAL_B, group="Unlisted")]
    lo = loadout(*items, groups=("One", "Two"))      # 'Unlisted' and the ungrouped item must not vanish
    h = harvest(render.html(lo))
    shown = [t for k, t in h.records if k == "serial"]
    assert sorted(shown) == sorted(i.serial for i in items)
    lines = render.text(lo).split("\n")
    for s in {i.serial for i in items}:
        assert lines.count(s) == sum(1 for i in items if i.serial == s)


def test_text_is_pasteable(render):
    lo = loadout(item("Anarchy", SERIAL_A, group="Guns", element="cryo"),
                 item("Evil\n@UFAKE\tname", SERIAL_B, group="Guns"),
                 item("Shield", SERIAL_C, group="Gear & <Mods>"), groups=("Guns", "Gear & <Mods>"),
                 title="My\nLoadout")
    txt = render.text(lo)
    lines = txt.split("\n")
    assert lines[:3] == ["My Loadout", "=" * len("My Loadout"), ""]
    assert "[Guns]" in lines and "[Gear & <Mods>]" in lines
    assert "Anarchy  (Cryo)" in lines
    assert "Evil @UFAKE name" in lines and "@UFAKE" not in lines   # a name can never pose as a serial
    serial_lines = [ln for ln in lines if ln.startswith("@U")]
    assert serial_lines == [SERIAL_A, SERIAL_B, SERIAL_C]
    assert not re.search(r"<(/?[a-z]+)[ >]", txt.replace("<Mods>", ""))   # no markup of our own
    assert "\r" not in txt and txt.endswith("\n")


def test_write_creates_both_files(render, tmp_path):
    lo = loadout(item(group="G"), groups=("G",))
    target = tmp_path / "deep" / "er" / "sheet.html"
    got = render.write(lo, str(target))
    assert got == (str(target), str(tmp_path / "deep" / "er" / "sheet.txt"))
    assert os.path.isfile(got[0]) and os.path.isfile(got[1])
    assert open(got[0], encoding="utf-8").read() == render.html(lo)
    assert open(got[1], encoding="utf-8").read() == render.text(lo)
    # explicit text path (also in a new directory), and pathlib input is accepted
    got2 = render.write(lo, target, tmp_path / "txt" / "codes.txt")
    assert got2 == (str(target), str(tmp_path / "txt" / "codes.txt"))
    assert os.path.isfile(got2[1])
    # a bare filename (no directory part) works and the extension-less case appends .txt
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert render.write(lo, "plain") == ("plain", "plain.txt")
    finally:
        os.chdir(cwd)
    assert (tmp_path / "plain.txt").is_file()


def test_write_refuses_to_clobber_html_with_text(render, tmp_path):
    lo = loadout(item())
    with pytest.raises(ForgeError):
        render.write(lo, str(tmp_path / "x.txt"))               # default text path would equal html path
    with pytest.raises(ForgeError):
        render.write(lo, str(tmp_path / "x.html"), str(tmp_path / "x.html"))
    assert not (tmp_path / "x.txt").exists() and not (tmp_path / "x.html").exists()


def test_write_failure_is_a_forge_error(render, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(ForgeError):
        render.write(loadout(item()), str(blocker / "sub" / "a.html"))   # parent is a file


# ============================ legacy parity ===================================================
ELEMENT_FROM_LEGACY = {"electric": "shock", "N/A": None}     # legacy bulletType -> vocab name


def vocab_element(legacy_key):
    return ELEMENT_FROM_LEGACY.get(legacy_key, legacy_key)


def to_item(d, group=None, note=""):
    """Legacy enriched dict -> LoadoutItem. The only intended difference is the element spelling."""
    el = vocab_element(d["element"])
    assert el is None or el in vocab.ELEMENTS, el
    return LoadoutItem(
        name=d["name"], serial=d["serial"], level=d["level"], group=group,
        display_name=d.get("display_name"), manufacturer=d["manufacturer"], label=d["label"],
        type=d["type"], weapon_type=d["weaponType"], rarity=d.get("true_rarity") or d["rarity"],
        element=el, category=d.get("category"), legendary_name=d.get("legendary_name"),
        parts=tuple(d.get("parts") or ()), odds=d.get("odds") or "", source=d["source"], note=note,
        warnings=tuple(d["warnings"]))


GROUPS = ("Weapons & Mods", "Shields <and> Gear", 'The "Rest"')
TITLE = 'Parity "Test" & <Co>'


def grouped(n_items, i):
    return GROUPS[min(i * len(GROUPS) // n_items, len(GROUPS) - 1)]    # contiguous chunks


def spread(legacy, per_type=5):
    by_type = {}
    for e in legacy.forge.load_db():
        by_type.setdefault(e["type"], []).append(e)
    out = []
    for t in sorted(by_type):
        rows = by_type[t]
        out += rows[::max(1, len(rows) // per_type)][:per_type]
    return out


def test_legacy_content_parity(legacy, render):
    entries = spread(legacy)
    assert len(entries) >= 30
    legacy_items = []
    for i, entry in enumerate(entries):
        d = legacy.forge.enrich(entry, 60)
        d["group"] = grouped(len(entries), i)
        if i % 4 == 0:
            d["display_name"] = "Custom & <Name> %d" % i
        legacy_items.append(d)
    items = [to_item(d, d["group"]) for d in legacy_items]
    lo = Loadout(title=TITLE, level=60, items=tuple(items), groups=GROUPS)

    old = harvest(legacy.forge.render_html(legacy_items, TITLE, 60, list(GROUPS)))
    new = harvest(render.html(lo))
    # every card: name, element badge, sub line (label/rarity/level), odds, parts, serial
    assert cards(new) == cards(old)
    # page chrome: title, h1, subtitle, import instructions, group headings, checklist, footer
    assert chrome(new) == chrome(old)
    assert [t for k, t in new.records if k == "h2"][:3] == list(GROUPS)
    # plain text is byte-identical for contiguous groups
    assert render.text(lo) == legacy.forge.plain_text(legacy_items, TITLE, 60)
    # sanity: the sample really contains levels, odds and several elements
    assert any(c["ctype"].endswith("Lv 60") for c in cards(new))
    assert len({c.get("badge") for c in cards(new)}) >= 4


def test_legacy_content_parity_whole_database(legacy, render):
    """All 9,875 catalog rows through both renderers (legacy dicts built without decoding)."""
    rows = legacy.forge.load_db()
    assert len(rows) == 9875
    legacy_items = []
    for i, e in enumerate(rows):
        d = {"name": e.get("itemName", "?"), "manufacturer": e.get("manufacturer", ""),
             "label": e.get("manufacturerWeaponType") or e.get("type", ""), "rarity": e.get("rarity", ""),
             "element": e.get("bulletType", "N/A"), "type": e.get("type", ""),
             "weaponType": e.get("weaponType", ""), "source": e.get("source", ""),
             "level": 60, "serial": e["serial"], "warnings": [], "group": grouped(len(rows), i)}
        if i % 7 == 0:
            d["display_name"] = "Shown %d & co" % i
        legacy_items.append(d)
    items = [to_item(d, d["group"]) for d in legacy_items]
    lo = Loadout(title=TITLE, level=60, items=tuple(items), groups=GROUPS)

    old = harvest(legacy.forge.render_html(legacy_items, TITLE, 60, list(GROUPS)))
    new = harvest(render.html(lo))
    assert cards(new) == cards(old)
    assert chrome(new) == chrome(old)
    assert render.text(lo) == legacy.forge.plain_text(legacy_items, TITLE, 60)
    # every element value in the database maps to a rendered badge or none, as the explicit table says
    assert {vocab_element(d["element"]) for d in legacy_items} <= set(vocab.ELEMENTS) | {None}


# ============================ behaviour beyond the invariants =================================
@pytest.mark.parametrize("el,css,label", [
    ("cryo", "cryo", "Cryo"), ("fire", "fire", "Fire"), ("radiation", "rad", "Radiation"),
    ("shock", "shock", "Shock"), ("corrosive", "corr", "Corrosive"), ("impact", "impact", "Impact"),
    ("Shock", "shock", "Shock"),
])
def test_element_badges_use_vocab_labels(render, el, css, label):
    h = harvest(render.html(loadout(item(element=el))))
    badge_tags = [a for t, a in h.tags if t == "span" and "badge" in (a.get("class") or "")]
    assert badge_tags == [{"class": "badge " + css}]
    assert ("badge", label) in h.records
    assert label == vocab.ELEMENT_LABELS[el.lower()]
    assert "%s  (%s)" % ("Anarchy", label) in render.text(loadout(item(element=el))).split("\n")


@pytest.mark.parametrize("el", [None, "", "N/A"])
def test_no_element_means_no_badge(render, el):
    lo = loadout(item(element=el))
    assert "badge" not in {c for k, _ in harvest(render.html(lo)).records for c in [k]}
    assert "Anarchy" in render.text(lo).split("\n")


def test_unknown_element_is_shown_escaped_not_hidden(render):
    doc = render.html(loadout(item(element="<b>plasma</b>")))
    assert '<span class="badge none">&lt;b&gt;plasma&lt;/b&gt;</span>' in doc


def test_every_vocab_element_has_a_css_class():
    assert set(style.ELEMENT_CSS_CLASS) == set(vocab.ELEMENTS)
    for cls in style.ELEMENT_CSS_CLASS.values():
        assert ".badge.%s{" % cls in CSS


def test_card_fields(render):
    it = item("Plain", SERIAL_A, display_name="Shown", legendary_name="Legend", category="Pistol",
              label="Jakobs Pistol", rarity="Legendary", level=60, odds="1 in 40",
              parts=("a", "b", "c"), warnings=("careful",))
    h = harvest(render.html(loadout(it)))
    c = cards(h)[0]
    assert c["cname"] == "Shown"
    assert c["ctype"] == "Pistol · Legendary · Lv 60"          # decoded category beats the catalog label
    assert c["odds"] == "1 in 40" and c["parts"].startswith("3 parts") and c["parts"].endswith("a · b · c")
    assert ("warn", "Warning · careful") in h.records
    # name falls back: display_name > legendary_name > name
    assert harvest(render.html(loadout(item(legendary_name="Legend")))).records.count(("cname", "Legend")) == 1
    assert harvest(render.html(loadout(item(label="Jakobs Pistol", level=None, rarity="")))).records.count(
        ("ctype", "Jakobs Pistol")) == 1
    assert "1 part<" in render.html(loadout(item(parts=("only",))))


def test_groups(render):
    lo = loadout(item("a", SERIAL_A, group="Second"), item("b", SERIAL_B, group="First"),
                 item("c", SERIAL_C, group="Second"), item("d", "@Uxx", group="OnlyOnItem"),
                 groups=("First", "Second", "NoItems"))
    h = harvest(render.html(lo))
    heads = [t for k, t in h.records if k == "h2"]
    assert heads[:3] == ["First", "Second", "OnlyOnItem"]            # listed order, then item-only groups
    assert "NoItems" not in heads                                     # empty groups are skipped
    lines = render.text(lo).split("\n")
    assert [ln for ln in lines if ln.startswith("[")] == ["[First]", "[Second]", "[OnlyOnItem]"]
    assert lines.index("[Second]") < lines.index(SERIAL_A) < lines.index(SERIAL_C) < lines.index("[OnlyOnItem]")


def test_ungrouped_items_are_never_dropped(render):
    plain = loadout(item("a"), item("b", SERIAL_B))
    heads = [t for k, t in harvest(render.html(plain)).records if k == "h2"]
    assert heads == ["Loadout", "Quick Checklist"]
    assert not any(ln.startswith("[") for ln in render.text(plain).split("\n"))
    mixed = loadout(item("a", group="G"), item("b", SERIAL_B), groups=("G",))
    heads = [t for k, t in harvest(render.html(mixed)).records if k == "h2"]
    assert heads == ["G", "Other", "Quick Checklist"]
    lines = render.text(mixed).split("\n")
    assert lines.index("[G]") < lines.index(SERIAL_A) < lines.index("[Other]") < lines.index(SERIAL_B)


def test_level_line_and_subtitle(render):
    h = harvest(render.html(loadout(item(), level=60)))
    assert ("subtitle", "1 import-ready code, re-leveled to 60. Paste each into the Item Builder's "
            "decoder box, Decode & Validate, then Add to Backpack.") in h.records
    h = harvest(render.html(loadout(item(), item("b", SERIAL_B), level=None)))
    assert [t for k, t in h.records if k == "subtitle"][0].startswith("2 import-ready codes, re-leveled to their saved level.")
    assert "All codes re-leveled" in render.text(loadout(item(), level=55))
    assert "55" in render.text(loadout(item(), level=55))
    assert "All codes re-leveled" not in render.text(loadout(item(), level=None))


def test_import_instructions_survive(render):
    h = harvest(render.html(loadout(item())))
    tldr = [t for k, t in h.records if k == "tldr"][0]
    for must in ("Item Builder", "decoder box", "Decode & Validate", "Add to Backpack",
                 "Nothing touches your real save until you hit Overwrite Existing Save"):
        assert must in tldr
    steps = [t for k, t in h.records if k == "step"]
    assert len(steps) == 4 and "Overwrite Existing Save" in steps[-1]


def test_warnings_and_unmatched_are_shown_not_dropped(render):
    lo = loadout(item(), warnings=("level did not take",), unmatched=("cryo bazooka",))
    h = harvest(render.html(lo))
    heads = [t for k, t in h.records if k == "h2"]
    assert "Not matched" in heads and "Warnings" in heads
    assert ("warn", "cryo bazooka") in h.records and ("warn", "level did not take") in h.records
    clean = [t for k, t in harvest(render.html(loadout(item()))).records if k == "h2"]
    assert "Warnings" not in clean and "Not matched" not in clean


def test_empty_loadout(render):
    lo = loadout(title="Nothing")
    assert "No items in this loadout." in render.html(lo)
    assert "0 import-ready codes" in render.html(lo)
    assert render.text(lo) == "Nothing\n=======\n\nAll codes re-leveled to 60.\n"


def test_output_is_deterministic_and_instances_do_not_interfere(config):
    a = RenderModule(ModuleContext("render", config, {}))
    b = RenderModule(ModuleContext("render", config, {}))
    lo = loadout(item(group="G", note="n"), groups=("G",))
    assert a.html(lo) == b.html(lo) == a.html(lo)
    assert a.text(lo) == b.text(lo)


def test_tags_are_balanced(render):
    h = harvest(render.html(hostile_loadout()))        # also exercises unbalanced <em> in notes
    stack = []
    class Check(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in ("meta",):
                stack.append(tag)
        def handle_endtag(self, tag):
            assert stack and stack.pop() == tag, tag
    c = Check()
    c.feed(render.html(loadout(item(note="<em>never closed"))))
    c.close()
    assert stack == []
    assert h.tags


# ============================ module plumbing =================================================
def test_conforms_to_port(render):
    assert MODULE is RenderModule
    assert conformance_problems(render, RenderPort) == []
    assert (RenderModule.name, RenderModule.requires, RenderModule.port) == ("render", (), RenderPort)


def test_health_is_honest_and_never_raises(render, monkeypatch):
    rep = render.health()
    assert rep.ok and {c.name for c in rep.checks} == {"html_renders", "text_renders", "self_contained"}
    assert all(c.ok for c in rep.checks)

    def boom(self, loadout):
        raise RuntimeError("broken")
    monkeypatch.setattr(RenderModule, "html", boom)
    rep = render.health()                                  # must not raise
    assert not rep.ok and any("RuntimeError" in c.detail for c in rep.checks)


def test_forge_starts_render_alone(config):
    from bl4forge.core.forge import Forge
    f = Forge.build(config, only=["render"])
    assert f.summary() == {"render": "ok"}
    assert "Anarchy" in f.render.text(loadout(item()))
