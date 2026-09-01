"""Meta-tests for the documentation tier: the cards, the page, the glossary.

The suite already asserts things about itself (tests/test_suite_hygiene.py).
This does the same for the things the repo publishes, because they rot the same
way and nothing else notices: a generated file drifts from its source, a card
cites a section that was renumbered, a callout is dropped from the printed card
and turns out to exist nowhere else.

Every check here is cheap and reads a file. None of them render HTML, so none
of them can tell you the card looks right. They tell you it is consistent,
which is the part a human reviewer is worst at.
"""

import ast
import html
import io
import pathlib
import re
import sys
import tokenize
from html.parser import HTMLParser

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import build_card                                  # noqa: E402
import gen_glossary                                # noqa: E402
import terms                                       # noqa: E402

FRAG = (REPO / "frag.html").read_text(encoding="utf-8")
BUILT = (REPO / "testharness_deep-dive.html").read_text(encoding="utf-8")
CARD = (REPO / "pytest-field-card.html").read_text(encoding="utf-8")
BASICS = (REPO / "pytest-basics-card.html").read_text(encoding="utf-8")

SECTION_IDS = dict(re.findall(r'<section id="([^"]+)" data-num="(\d+)"', FRAG))


class Balance(HTMLParser):
    """Minimal well-formedness check: every open tag is closed, in order."""

    VOID = {"br", "img", "hr", "meta", "link", "input", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.errors.append("stray </%s> at %s" % (tag, self.getpos()))
            return
        top, pos = self.stack.pop()
        if top != tag:
            self.errors.append("</%s> at %s closes <%s> opened at %s"
                               % (tag, self.getpos(), top, pos))

    def report(self):
        return self.errors + ["unclosed <%s> at %s" % (t, p) for t, p in self.stack]


def balance(source):
    parser = Balance()
    parser.feed(source)
    return parser.report()


# ── generated files match their source ──────────────────────────────────────

def test_glossary_markdown_matches_terms():
    """GLOSSARY.md is generated. If someone edits it by hand the edit is lost
    on the next run, so the drift is caught here instead of silently."""
    on_disk = (REPO / "GLOSSARY.md").read_text(encoding="utf-8")
    assert on_disk == gen_glossary.render_markdown(), (
        "GLOSSARY.md is stale. Edit terms.py, then run: python gen_glossary.py")


def test_glossary_cards_match_terms():
    on_disk = (REPO / "glossary_cards.py").read_text(encoding="utf-8")
    assert on_disk == gen_glossary.render_cards(), (
        "glossary_cards.py is stale. Run: python gen_glossary.py")


def test_the_deep_dive_glossary_section_matches_terms():
    """The generated block inside frag.html carries one row per term."""
    block = re.search(re.escape(gen_glossary.START) + r"(.*?)" + re.escape(gen_glossary.END),
                      FRAG, re.S)
    assert block, "the generated glossary markers are missing from frag.html"
    assert block.group(1).count('<td class="meth">') == terms.count()


def test_the_built_page_is_newer_than_its_fragment():
    """The deep dive is generated from frag.html. A fragment edited after the
    last build means the published page is behind."""
    frag_m = (REPO / "frag.html").stat().st_mtime
    built_m = (REPO / "testharness_deep-dive.html").stat().st_mtime
    assert built_m >= frag_m, (
        "frag.html is newer than the built page. Rebuild it with the deep-dive "
        "builder before publishing.")


# ── cross-references resolve ────────────────────────────────────────────────

def test_every_glossary_reference_names_a_real_section():
    """A term pointing at a section id that no longer exists is a dead link in
    three places at once: the page, the markdown and the card."""
    bad = sorted({see for _g, _t, _m, see in terms.flat()
                  if see and see not in SECTION_IDS})
    assert not bad, "terms.py points at sections that do not exist: " + ", ".join(bad)


def test_no_dangling_anchors_in_the_built_page():
    anchors = set(re.findall(r'<section id="([^"]+)"', BUILT))
    links = set(re.findall(r'href="#([a-z0-9\-]+)"', BUILT))
    assert not links - anchors, "dangling: %s" % sorted(links - anchors)


def test_prose_section_numbers_match_the_sections_they_link_to():
    """The page cites sections by number in prose. Inserting a section
    renumbers everything after it, and the citations have to follow."""
    numbers = dict(re.findall(r'<section id="([^"]+)" data-num="(\d+)"', BUILT))
    wrong = [(m.group(1), m.group(2), numbers.get(m.group(1)))
             for m in re.finditer(r'href="#([a-z0-9\-]+)">§(\d+)</a>', BUILT)
             if numbers.get(m.group(1)) != m.group(2)]
    assert not wrong, "cross-references citing the wrong number: %s" % wrong


def test_the_toc_and_the_sections_agree():
    toc = re.findall(r'<a href="#([a-z0-9\-]+)"><span>\d+</span>', BUILT)
    sections = re.findall(r'<section id="([^"]+)" data-num=', BUILT)
    assert toc == sections, "the side nav and the sections are out of order"


# ── the .why contract ───────────────────────────────────────────────────────

STOPWORDS = {"which", "that", "there", "their", "these", "those", "would",
             "could", "should", "about", "after", "every", "other", "where",
             "because", "instead", "rather", "always", "never", "thing",
             "things", "something", "anything"}


def why_blocks():
    """(slug, section it defers to, its text) for every stripped argument."""
    for slug, (_title, card) in build_card.RECIPE_CARDS.items():
        for see, body in re.findall(
                r'<div class="why" data-see="([^"]+)">(.*?)</div>', card, re.S):
            yield slug, see, html.unescape(re.sub(r"<[^>]+>", "", body)).strip()


def section_text(section_id):
    """The prose of one deep-dive section, tags stripped."""
    start = FRAG.index('<section id="%s"' % section_id)
    end = FRAG.index("</section>", start)
    text = re.sub(r"<[^>]+>", " ", FRAG[start:end])
    return re.sub(r"\s+", " ", html.unescape(text)).lower()


def test_every_dropped_argument_names_a_real_section():
    """A .why callout is removed from the printed card, so it has to say where
    the argument survives. An id that does not exist means it survives nowhere.
    """
    bad = [(slug, see) for slug, see, _t in why_blocks() if see not in SECTION_IDS]
    assert not bad, "these defer to sections that do not exist: %s" % bad


def test_the_section_a_dropped_argument_defers_to_is_about_it():
    """Weaker than checking the argument is made, which no test can do, and
    stronger than checking an id exists.

    Requires two distinctive words from the callout to appear in the section it
    names. Tolerant of the page making the point in its own words, which it
    does, while still catching a callout pointed at the wrong section.
    """
    thin = []
    for slug, see, text in why_blocks():
        words = {w for w in re.findall(r"[a-z]{5,}", text.lower())
                 if w not in STOPWORDS}
        prose = section_text(see)
        hits = {w for w in words if w in prose}
        if len(hits) < 2:
            thin.append("%s -> #%s (matched %s of %d)"
                        % (slug, see, sorted(hits), len(words)))
    assert not thin, (
        "these callouts defer to a section that does not discuss them:\n  "
        + "\n  ".join(thin))


def test_why_blocks_are_absent_from_the_printed_card():
    assert 'class="why"' not in CARD, (
        "a .why block reached the printed card; build_card.strip_why did not run")


def test_there_are_why_blocks_to_strip():
    """Guards the test above: it passes trivially if nothing is ever tagged."""
    assert len(list(why_blocks())) >= 5


# ── the cards themselves ────────────────────────────────────────────────────

@pytest.mark.parametrize("name,source",
                         [("field card", CARD), ("basics card", BASICS),
                          ("deep dive", BUILT)],
                         ids=["field-card", "basics-card", "deep-dive"])
def test_published_html_is_balanced(name, source):
    assert balance(source) == [], "%s: %s" % (name, balance(source)[:3])


@pytest.mark.parametrize("name,source",
                         [("field card", CARD), ("basics card", BASICS),
                          ("deep dive", BUILT)],
                         ids=["field-card", "basics-card", "deep-dive"])
def test_published_html_is_self_contained(name, source):
    """No external scripts, images or stylesheets. A card that needs the
    network is a card that fails in a meeting room."""
    external = [u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', source)
                if "fonts.googleapis" not in u]
    assert not external or name == "deep dive", "%s loads %s" % (name, external)


@pytest.mark.parametrize("name,source",
                         [("field card", CARD), ("basics card", BASICS),
                          ("deep dive", BUILT), ("glossary", (REPO / "GLOSSARY.md").read_text(encoding="utf-8"))],
                         ids=["field-card", "basics-card", "deep-dive", "glossary"])
def test_no_em_dashes_or_emoji(name, source):
    """House style. Checked on the published artifact rather than the source,
    because the generators concatenate from several places."""
    assert "—" not in source and "–" not in source, "%s: em dash" % name
    emoji = re.findall("[\U0001F300-\U0001FAFF☀-➿]", source)
    assert not emoji, "%s: emoji %s" % (name, emoji[:3])


def test_every_card_span_class_is_defined_in_the_stylesheet():
    """A span class with no rule renders as unstyled text, which on a printed
    card usually means invisible rather than wrong."""
    style = CARD[:CARD.index("</style>")]
    defined = set(re.findall(r"\.([a-z0-9]+)[\s,{:]", style))
    used = {c for group in re.findall(r'<span class="([a-z0-9 ]+)"', CARD)
            for c in group.split()}
    assert not used - defined, "undefined span classes: %s" % sorted(used - defined)


def test_the_print_override_beats_dark_mode():
    """The dark-mode rule is more specific than a bare :root, so the print
    block has to match it selector for selector or a dark-themed browser
    prints a black page."""
    print_block = CARD[CARD.index("@media print{"):]
    assert ':root:not([data-theme="light"])' in print_block
    assert "background:#fff !important" in print_block


def test_every_card_is_placed_exactly_once():
    placed = [s for col in build_card.pack() for s in col]
    assert sorted(placed) == sorted(build_card.CARDS), "ORDER and CARDS disagree"
    assert len(placed) == len(set(placed))


def test_no_column_overflows_its_page():
    """The layout is solved, not eyeballed. This is the assertion that stopped
    a card printing alone on a fifth page."""
    cap = build_card.capacity()
    over = [(i, load) for i, load in
            enumerate(sum(build_card.weight(build_card.CARDS[s][1]) for s in col)
                      for col in build_card.pack())
            if load > cap]
    assert not over, "columns over capacity %.1f: %s" % (cap, over)


def test_the_layout_fills_whole_sheets():
    """An odd number of sides leaves a blank back, which reads as a printing
    mistake rather than a choice."""
    sides = -(-len(build_card.pack()) // 2)
    assert sides % 2 == 0, "%d sides leaves a blank back" % sides


# ── the source modules stay readable ────────────────────────────────────────

def test_card_content_is_not_one_long_line():
    """It was, once: a repr from the original extraction. Every edit became a
    substring hunt and every diff was the whole file."""
    source = (REPO / "card_content.py").read_text(encoding="utf-8")
    longest = max(len(line) for line in source.splitlines())
    assert longest < 400, "longest line is %d characters" % longest


@pytest.mark.parametrize(
    "module",
    ["terms.py", "card_content.py", "card_content_basics.py",
     "build_card.py", "build_basics.py", "gen_glossary.py"],
)
def test_generator_modules_parse_and_are_documented(module):
    source = (REPO / module).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert ast.get_docstring(tree), "%s has no module docstring" % module
    # tokenize as well: catches a stray null byte or bad encoding that ast
    # would accept through a different code path
    list(tokenize.generate_tokens(io.StringIO(source).readline))


# ── the console ─────────────────────────────────────────────────────────────

CONSOLE = (REPO / "pytest-console.html").read_text(encoding="utf-8")

import build_console                               # noqa: E402
import console_content                             # noqa: E402


def test_console_html_is_balanced():
    assert balance(CONSOLE) == [], balance(CONSOLE)[:3]


def test_console_is_self_contained():
    """It is a reference you open on a plane. No CDN, no webfont, no image."""
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', CONSOLE)
    assert not external, external


def test_every_tab_has_a_panel_and_every_panel_a_tab():
    tabs = set(re.findall(r'<button class="tab" data-for="([^"]+)"', CONSOLE))
    panels = set(re.findall(r'<section class="panel" id="([^"]+)"', CONSOLE))
    assert tabs == panels, "orphaned: %s" % sorted(tabs ^ panels)
    assert len(tabs) == len(console_content.TABS)


def test_every_card_carries_a_label():
    """A card with no label strip is a wall of text in a grid cell."""
    cards = re.findall(r'<div class="card[^"]*">(.*?)(?=<div class="card|</div>\s*</section>)',
                       CONSOLE, re.S)
    missing = [c[:60] for c in cards if 'class="lab"' not in c]
    assert not missing, "%d cards without a label: %s" % (len(missing), missing[:2])


def test_no_long_prose_in_a_nowrap_key_cell():
    """The bug that broke the deep dive's AI section.

    `td.k` and `td.o` are `white-space: nowrap`, which is right for a short key
    and catastrophic for a sentence: the row becomes one unwrappable line that
    runs off the page, taking the other columns with it. Nothing else in the
    suite can see that, because the HTML is perfectly valid.
    """
    cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
             for c in re.findall(r'<td class="[ko]">(.*?)</td>', CONSOLE, re.S)]
    over = [c for c in cells if len(c) > 40]
    assert not over, "nowrap cells holding prose: %s" % over[:3]


def test_the_console_glossary_matches_terms():
    """The console is the fourth surface generated from terms.py."""
    tab = next(t for t in console_content.TABS if t["id"] == "glossary")
    assert len(tab["cards"]) == len(terms.GROUPS)
    rendered = "".join(tab["cards"])
    assert rendered.count('<td class="k">') == terms.count()


def test_the_console_layout_is_declared_not_measured():
    """Unlike the print cards, nothing here has to fit a page, so the builder
    has no solver and no scale knob. Asserted so that if one appears, this test
    is the reminder to give it a --check like the others have."""
    assert not hasattr(build_console, "capacity")
    assert hasattr(build_console, "check")
