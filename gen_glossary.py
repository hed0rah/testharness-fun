#!/usr/bin/env python3
"""Generate every glossary surface from terms.py.

Three outputs, one source:

    GLOSSARY.md                    the markdown reference
    glossary_cards.py              cards for the printed reference card
    frag.html  (section "terms")   the deep dive's lookup section

Run it after editing terms.py, then rebuild the card and the page:

    python gen_glossary.py
    python build_card.py
    build.py frag.html testharness_deep-dive.html "<title>"

The deep dive section is rewritten between two markers, so hand-written prose
elsewhere in the fragment is left alone.
"""

import html
import pathlib
import re

import terms

NL = chr(10)

OPENING = '''## Explaining it in forty-five seconds

> pytest is a test runner. You write a normal Python function whose name starts
> with `test`, put an `assert` in it, and run `pytest`. That is the whole
> contract. No class to inherit, no `self`, no `assertEqual`, no imports.
>
> The reason it is worth twenty minutes is the failure output. pytest rewrites
> your test file as it loads it, so a bare `assert x == y` prints both values
> and a diff. You never learn an assertion API, and you never write your own
> failure messages.
>
> Past that it is two ideas. **Fixtures** are named setup that a test asks for
> by argument name, and they clean up after themselves even when the test
> fails. **Test doubles** are stand-ins for things you do not want to touch in
> a test, like a network call or a database.
>
> And one habit: if a test is painful to write, that is usually the code
> talking, not the test. The fix is normally in the code.

Fifteen-second version, if they would rather just see it run:

> A test is a function starting with `test` that contains an `assert`. Run
> `pytest` and it finds them. Everything else is convenience. Let me show you
> one, then break it so you can see what a failure looks like.

If they ask why not just unittest: pytest runs unittest tests unchanged, so it
is not a migration. You get plain `assert` with real diffs, fixtures instead of
`setUp`, and `--lf`. You can adopt it on a Tuesday and rewrite nothing.

## The two worth saying out loud

**Coverage is a map, not a score.** 100% line coverage is compatible with zero
assertions. Use it to find the branch nobody exercises, then go and write a
real assertion about it.

**A flaky test is a bug report.** Something is genuinely non-deterministic and
you have found it. The usual causes are unseeded randomness, a real clock,
shared state, or a fixed file path. Quarantine it behind a marker with a
ticket; do not add a retry.
'''


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def to_markdown(s):
    """HTML inline markup to markdown, for the .md output."""
    s = re.sub(r"<code>(.*?)</code>", r"`\1`", s)
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s)
    s = re.sub(r"<i>(.*?)</i>", r"*\1*", s)
    return html.unescape(s)


# ── GLOSSARY.md ─────────────────────────────────────────────────────────────

def render_markdown():
    """The GLOSSARY.md text. Pure, so tests/test_cards.py can check the file on
    disk still matches terms.py without writing anything."""
    out = ["# pytest glossary", "",
           "Generated from `terms.py`. Edit that, then run `gen_glossary.py`.",
           "",
           "Short meanings, grouped by when you meet them. The `see` column is a",
           "section of `testharness_deep-dive.html`, which is where the long",
           "version of each idea lives.", "",
           OPENING.strip(), ""]

    for group, items in terms.GROUPS:
        out += ["## " + group, "", "| term | meaning | see |", "|---|---|---|"]
        for term, meaning, see in items:
            out.append("| **%s** | %s | %s |"
                       % (term, to_markdown(meaning), "`%s`" % see if see else ""))
        out.append("")

    out += ["---", "",
            "%d terms in %d groups." % (terms.count(), len(terms.GROUPS)), ""]
    return NL.join(out)


def write_markdown():
    text = render_markdown()
    pathlib.Path("GLOSSARY.md").write_text(text, encoding="utf-8")
    return len(text)


# ── glossary cards for the printed reference ────────────────────────────────

def render_cards():
    """One card per group, in the card_content.py format.

    Split across cards by group rather than packed evenly: a glossary you scan
    wants its headings where you expect them, not wherever a column ended.
    """
    body = ['"""Glossary cards for the printed reference. GENERATED, do not edit.',
            "",
            "Written by gen_glossary.py from terms.py. Edit those.",
            '"""',
            "",
            "CARDS = {",
            ""]

    for group, items in terms.GROUPS:
        slug = "glossary-" + re.sub(r"[^a-z]+", "-", group.lower()).strip("-")
        rows = "".join(
            '    <tr><td class="k">%s</td><td>%s</td></tr>%s' % (term, meaning, NL)
            for term, meaning, _see in items)
        card = ('<div class="card hot">' + NL
                + '  <div class="lab">glossary: %s</div>' % group + NL
                + '  <table>' + NL + rows + '  </table>' + NL
                + '</div>')
        body.append('"%s": ("glossary: %s", %s%s%s),'
                    % (slug, group, "'''", card, "'''"))
        body.append("")

    body += ["}", ""]
    return NL.join(body)


def write_cards():
    pathlib.Path("glossary_cards.py").write_text(render_cards(), encoding="utf-8")
    return len(terms.GROUPS)


# ── the deep dive's lookup section ──────────────────────────────────────────

START = "<!-- GENERATED glossary section: gen_glossary.py -->"
END = "<!-- END generated glossary section -->"


def write_deep_dive_section():
    frag = pathlib.Path("frag.html").read_text(encoding="utf-8")
    if START not in frag:
        return None                      # section not wired in yet

    rows = []
    for group, items in terms.GROUPS:
        rows.append('  <h3>%s</h3>' % group)
        rows.append('  <table>')
        rows.append('    <tr><th>term</th><th>meaning</th><th>section</th></tr>')
        for term, meaning, see in items:
            link = ('<a href="#%s">%s</a>' % (see, see)) if see else '<span class="dim">-</span>'
            rows.append('    <tr><td class="meth">%s</td><td>%s</td><td>%s</td></tr>'
                        % (term, meaning, link))
        rows.append('  </table>')

    block = START + NL + NL.join(rows) + NL + "  " + END
    out = re.sub(re.escape(START) + r".*?" + re.escape(END), block, frag, flags=re.S)
    pathlib.Path("frag.html").write_text(out, encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    n = terms.count()
    size = write_markdown()
    cards = write_cards()
    sect = write_deep_dive_section()
    print("terms          : %d in %d groups" % (n, len(terms.GROUPS)))
    print("GLOSSARY.md    : %d bytes" % size)
    print("glossary_cards : %d cards" % cards)
    print("deep dive      : %s"
          % ("%d rows written" % sect if sect else "marker not present, skipped"))
