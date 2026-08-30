#!/usr/bin/env python3
"""Lay the field card out across double-sided A4 sheets.

The layout constraint is arithmetic, so it is computed rather than eyeballed.
A column holds a fixed number of lines, every card has a measurable height, and
pack() slices the reading order into columns that fit. Two hand-layouts got
this wrong before it was automated: the first by a factor of two, the second by
one card that printed alone on a fifth page.

Two CSS facts the layout depends on:

  * CSS multi-column (`columns:2`) balances the whole flow and THEN paginates,
    so a two-page document becomes five. These are explicit flex columns, which
    break exactly where they are told to.
  * `rem` is relative to the ROOT font size, so setting `body{font-size:...}`
    scales nothing. The print knob sets `html{font-size:...}`.

    python build_card.py            # write pytest-field-card.html
    python build_card.py --check    # report column loads, write nothing
"""

import re
import sys

from card_content import CARDS as RECIPE_CARDS
from glossary_cards import CARDS as GLOSSARY_CARDS

# The glossary is the front of the card because it is the surface you hit
# first when you half-remember something. The recipes follow it.
CARDS = dict(GLOSSARY_CARDS, **RECIPE_CARDS)

NL = chr(10)

# Root font size in print. Everything else is in rem and follows it. Raising it
# makes the type bigger and adds sides; lowering it removes them. 14px puts code
# at about 6.7pt, which is the smallest that stays comfortable on paper.
PRINT_SCALE = "13.5px"

# Fill a column to this fraction of capacity. The height model is good to a few
# percent, not exact, so the slack is deliberate.
FILL = 0.95

# Reading order for the whole card. pack() slices this into columns.
# The glossary slugs come from the generated module, in its own order, so
# adding a group to terms.py cannot desync this list. Everything after is
# the recipe order, which is editorial and hand-kept.
ORDER = list(GLOSSARY_CARDS) + [
    "what-gets-collected", "conftest-py", "pyproject-toml-steal-this",
    "flags-muscle-memory", "plugins-verdicts",
    "fixtures-scope-and-teardown", "fixture-shapes",
    "parametrize-and-ids", "property-based",
    "assertions", "capturing-output", "skip-xfail-the-trap", "the-flaky-test",
    "what-do-i-reach-for", "seams-the-whole-game", "asgi-and-fake-clients",
    "the-five-doubles", "monkeypatch-all-of-it", "four-patching-traps",
    "hostile-input", "differential-oracle", "testing-a-cli",
    "meta-tests", "coverage-mutation-ci", "smells-and-the-build-order",
]

# One title, because pack() decides what lands on each side: a hand-written
# per-side heading drifts off its content the moment a card moves. The sub-line
# under it is generated from the cards actually present, so it cannot lie.
TITLE = 'pytest <span class="g">/ test harness field card</span>'


def weight(html, root=None):
    """Height of a card, in units of one <pre> line.

    Derived from the print stylesheet rather than guessed. At root size R one
    pre line is .635R * 1.4 = 0.889R px, and everything else measures against
    it:

      pre line    1.00
      pre block   1.15   padding .3rem x2 plus margins .12/.3rem
      table row   1.46   .655R x 1.5 plus .12rem padding x2 plus a 1px rule
      list item   2.36   .685R x 1.4, and they wrap: about two lines each
      paragraph   3.26   .73R x 1.38, about 2.5 lines, plus margin
      callout     3.60   .72R x 1.35 x 2.5 lines plus .26rem padding x2
      card chrome 3.03   border, .42/.48rem padding, 9px margin, label
    """
    R = float((root or PRINT_SCALE).rstrip("px"))
    unit = 0.889 * R
    blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", html, re.S)
    px = (sum(len(b.splitlines()) for b in blocks) * unit
          + len(blocks) * 1.15 * unit
          + html.count("<tr>") * (1.23 * R + 1)
          + html.count("<li>") * 2.36 * unit
          + html.count('class="p"') * 3.26 * unit
          + html.count('class="rule"') * 3.60 * unit
          + 1.9 * R + 11)
    return px / unit


def capacity(root=None):
    """Lines per column: A4 portrait at 8mm margins, less header and footer."""
    R = float((root or PRINT_SCALE).rstrip("px"))
    page = (297 - 16) / 25.4 * 96
    return (page - (5.0 * R + 22)) / (0.889 * R)


def _fits(loads, n, limit):
    """Can `loads` be cut into <= n order-preserving runs, none over `limit`?"""
    runs, cur = 1, 0.0
    for w in loads:
        if w > limit:
            return False
        if cur + w > limit:
            runs += 1
            cur = 0.0
        cur += w
    return runs <= n


def balance(n):
    """Cut ORDER into exactly n columns, minimising the fullest one.

    Binary search on the column limit with an order-preserving feasibility
    check: the standard linear-partition method. Greedy packing was the first
    attempt and it wasted a third of every column, because it fills each one to
    the brim and then strands whatever comes next.
    """
    loads = [weight(CARDS[s][1]) for s in ORDER]
    lo, hi = max(loads), sum(loads)
    for _ in range(60):
        mid = (lo + hi) / 2
        if _fits(loads, n, mid):
            hi = mid
        else:
            lo = mid
    limit = hi

    cols, cur, load = [], [], 0.0
    for slug, w in zip(ORDER, loads):
        if cur and load + w > limit:
            cols.append(cur)
            cur, load = [], 0.0
        cur.append(slug)
        load += w
    if cur:
        cols.append(cur)
    while len(cols) < n:                      # split the fullest to hit n
        i = max(range(len(cols)),
                key=lambda j: sum(weight(CARDS[s][1]) for s in cols[j]))
        if len(cols[i]) < 2:
            break
        cols[i:i + 1] = [cols[i][:-1], cols[i][-1:]]
    return cols


def pack():
    """Choose the column count, then balance into it.

    Sides are two columns and sheets are two sides, so a column count divisible
    by four fills every sheet with no blank back. The smallest such count that
    fits is the one used.
    """
    cap = capacity() * FILL
    n = 4
    while n <= 40:
        cols = balance(n)
        if len(cols) == n and all(
                sum(weight(CARDS[s][1]) for s in c) <= cap for c in cols):
            return cols
        n += 4
    raise SystemExit("no column count fits; lower PRINT_SCALE")


CSS = """
/* Print scale: root font size, which every rem-based size below follows.
   Raise for bigger type and more sides; lower for fewer. */
@media print { html { font-size: %(scale)s; } }

:root{
  --paper:#F4F1EA; --panel:#FBF9F4; --panel2:#EAE5D9; --ink:#14181A; --soft:#474D51;
  --faint:#7C8388; --line:#C2BAA8; --hair:#DED8C9;
  --accent:#A83208; --accent-soft:#F1DED4;
  --ok:#2A6B4C; --no:#96182C; --warn:#7E5A00;
  --mono:ui-monospace,"SF Mono","SFMono-Regular","Cascadia Code","JetBrains Mono",Menlo,Consolas,monospace;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#111310; --panel:#191c17; --panel2:#22261f; --ink:#e7e4d9; --soft:#a3a79c;
  --faint:#6e736a; --line:#2f342c; --hair:#252921;
  --accent:#E5703A; --accent-soft:#33201a;
  --ok:#6FBF95; --no:#E06070; --warn:#D6A93C;
}}
:root[data-theme="dark"]{
  --paper:#111310; --panel:#191c17; --panel2:#22261f; --ink:#e7e4d9; --soft:#a3a79c;
  --faint:#6e736a; --line:#2f342c; --hair:#252921;
  --accent:#E5703A; --accent-soft:#33201a;
  --ok:#6FBF95; --no:#E06070; --warn:#D6A93C;
}

*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:var(--mono);
     font-size:.82rem;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:1.2rem 1rem 3rem}
a{color:var(--accent);text-decoration:none;border-bottom:1px dotted currentColor}

.sheet{margin-bottom:2rem}
.sheethead{border:1px solid var(--ink);margin-bottom:.6rem;display:flex;align-items:stretch}
.side-badge{background:var(--ink);color:var(--paper);font-family:var(--sans);
            font-weight:700;font-size:1.35rem;line-height:1;padding:.5rem .65rem;
            display:flex;align-items:center;
            -webkit-print-color-adjust:exact;print-color-adjust:exact}
.sheettitle{padding:.4rem .65rem;flex:1;min-width:0}
.sheettitle h1{font-size:.9rem;font-weight:700}
.sheettitle h1 .g{color:var(--faint);font-weight:400}
.sheettitle .sub{font-family:var(--sans);font-size:.72rem;color:var(--soft);
                 line-height:1.35;margin-top:.1rem}
.sheettitle .sub b{color:var(--ink);font-weight:600}
.pageno{border-left:1px solid var(--line);padding:.4rem .55rem;display:flex;
        flex-direction:column;justify-content:center;align-items:flex-end;
        font-size:.52rem;letter-spacing:.13em;text-transform:uppercase;
        color:var(--faint);white-space:nowrap}
.pageno b{color:var(--accent);font-size:.7rem;letter-spacing:.05em}

/* Explicit columns. NOT CSS multicol: multicol balances across the whole flow
   and then paginates wherever it lands, which is how two pages became five. */
.cols{display:flex;gap:9px;align-items:flex-start}
.col{flex:1 1 0;min-width:0}

.card{background:var(--panel);border:1px solid var(--line);
      margin:0 0 9px;padding:.42rem .5rem .48rem;
      break-inside:avoid;page-break-inside:avoid}
.card.hot{border-left:3px solid var(--accent)}
.lab{font-size:.53rem;letter-spacing:.15em;text-transform:uppercase;
     color:var(--accent);font-weight:700;margin-bottom:.32rem;
     display:flex;align-items:center;gap:.38rem}
/* Outlined, not filled: survives a printer with background graphics off. */
.lab .n{border:1px solid currentColor;padding:0 .2rem;letter-spacing:.03em;font-size:.53rem}
.lab::after{content:"";flex:1;height:1px;background:var(--hair)}

.p{font-family:var(--sans);font-size:.73rem;line-height:1.38;color:var(--soft);margin:.08rem 0 .32rem}
.p b{color:var(--ink);font-weight:600}
.p:last-child{margin-bottom:0}

table{width:100%%;border-collapse:collapse;font-size:.655rem}
th,td{text-align:left;padding:.12rem .28rem;border-bottom:1px solid var(--hair);vertical-align:top}
th{font-size:.5rem;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);font-weight:700}
td.k{color:var(--accent);font-weight:700;white-space:nowrap}
tr:last-child td{border-bottom:none}

pre{background:var(--panel2);border-left:2px solid var(--line);
    padding:.3rem .4rem;overflow-x:auto;font-size:.635rem;line-height:1.4;
    margin:.12rem 0 .3rem;white-space:pre;color:var(--ink);
    -webkit-print-color-adjust:exact;print-color-adjust:exact}
pre.tree{border-left-color:var(--accent);border-left-width:3px;
         background:var(--accent-soft);font-size:.65rem;line-height:1.45}
pre.tree .q{color:var(--ink);font-weight:700}
pre.ok{border-left-color:var(--ok)}
pre.no{border-left-color:var(--no)}
pre .c{color:var(--faint)}
pre .y{color:var(--ok);font-weight:700}
pre .r{color:var(--no);font-weight:700}
pre .w{color:var(--warn);font-weight:700}
pre .a{color:var(--accent);font-weight:700}
code{background:var(--panel2);padding:0 .16rem;font-size:.93em;color:var(--accent)}

ul{margin:.08rem 0 .28rem;padding-left:.8rem}
li{margin:.1rem 0;font-size:.685rem;font-family:var(--sans);color:var(--soft)}
li b{color:var(--ink);font-weight:600}
li code{font-family:var(--mono)}

.rule{font-family:var(--sans);font-size:.72rem;line-height:1.35;color:var(--ink);
      background:var(--accent-soft);border-left:2px solid var(--accent);
      padding:.26rem .4rem;margin:.24rem 0 .08rem;
      -webkit-print-color-adjust:exact;print-color-adjust:exact}
.rule b{font-weight:700}
.flag{display:inline-block;font-size:.48rem;letter-spacing:.09em;font-weight:700;
      text-transform:uppercase;padding:0 .18rem;vertical-align:.08em;border:1px solid currentColor}
.f-ok{color:var(--ok)} .f-no{color:var(--no)} .f-wa{color:var(--warn)}

.fold{display:flex;align-items:center;gap:.6rem;margin:0 0 1.4rem;color:var(--faint);
      font-size:.52rem;letter-spacing:.2em;text-transform:uppercase}
.fold::before,.fold::after{content:"";flex:1;border-top:1px dashed var(--line)}
footer{margin-top:.4rem;font-size:.52rem;letter-spacing:.09em;text-transform:uppercase;
       color:var(--faint);display:flex;justify-content:space-between;gap:1rem}

@media print{
  /* Every selector the dark rules use, so this wins on specificity as well as
     source order. `:root` alone is (0,1,0) and loses to the dark-mode
     `:root:not([data-theme="light"])` at (0,2,0) -- which, on any browser that
     keeps prefers-color-scheme:dark active while printing, prints a black
     page and empties a toner cartridge. */
  :root,
  :root:not([data-theme="light"]),
  :root[data-theme="dark"],
  :root[data-theme="light"]{
    --paper:#fff; --panel:#fff; --panel2:#f2f0ea; --accent-soft:#f5e9e3;
    --line:#8d8d8d; --hair:#cfcfcf; --ink:#000; --soft:#1b1b1b; --faint:#474747;
    --accent:#8f2a06; --ok:#1a4d33; --no:#78101f; --warn:#5a4100;
  }
  html,body{background:#fff !important;color:#000}
  .card{background:#fff !important}
  .wrap{padding:0;max-width:none}
  .sheet{margin:0;break-after:page;page-break-after:always}
  .sheet:last-of-type{break-after:auto;page-break-after:auto}
  .fold{display:none}
  a{color:inherit;border-bottom:none}
  @page{size:A4 portrait;margin:8mm}
}
""".strip()




WHY = re.compile(r'<div class="why"[^>]*>.*?</div>', re.S)


def strip_why(html):
    """Remove the .why blocks before printing.

    A callout earns space on a card if it changes what you type. One that
    argues why is tagged .why and lives on the page instead, where there is
    room to make the case. tests/test_cards.py checks each one has a home
    there before it is dropped from here.
    """
    return WHY.sub("", html)


def clean(title):
    """Card title as plain text for the header line."""
    t = title.replace("&middot;", " ").replace("&amp;", "and")
    t = re.sub(r"&[a-z]+;", "", t)
    return re.sub(r"\s+", " ", t).strip()


def render():
    cols = pack()
    sides = [cols[i:i + 2] for i in range(0, len(cols), 2)]
    total = len(sides)
    out, n = [], 0

    for si, side_cols in enumerate(sides):
        col_html, names = [], []
        for col in side_cols:
            body = []
            for slug in col:
                title, html = CARDS[slug]
                html = strip_why(html)
                n += 1
                names.append(clean(title))
                html = html.replace(
                    '<div class="lab">',
                    '<div class="lab"><span class="n">%02d</span> ' % n, 1)
                body.append(html)
            col_html.append('<div class="col">' + NL + NL.join(body) + NL + "</div>")

        sheet = si // 2 + 1
        face = "front" if si % 2 == 0 else "back"
        out.append(
            '<div class="sheet">' + NL
            + '  <div class="sheethead">' + NL
            + '    <div class="side-badge">%d</div>' % (si + 1) + NL
            + '    <div class="sheettitle">' + NL
            + '      <h1>%s</h1>' % TITLE + NL
            + '      <div class="sub">%s</div>' % " &middot; ".join(names) + NL
            + '    </div>' + NL
            + '    <div class="pageno"><b>%d / %d</b><span>sheet %d %s</span></div>'
              % (si + 1, total, sheet, face) + NL
            + '  </div>' + NL
            + '<div class="cols">' + NL + NL.join(col_html) + NL + '</div>' + NL
            + '  <footer>' + NL
            + '    <span>hed0rah &middot; pytest field card &middot; side %d of %d</span>'
              % (si + 1, total) + NL
            + '    <span>%s</span>' % ("github.com/hed0rah/testharness-fun"
                                       if si == total - 1
                                       else "hed0rah.github.io/testharness") + NL
            + '  </footer>' + NL
            + '</div>')
        if si < total - 1:
            out.append('<div class="fold">%s</div>'
                       % ("turn over" if si % 2 == 0 else "next sheet"))

    return ('<!DOCTYPE html>' + NL + '<html lang="en">' + NL + '<head>' + NL
            + '<meta charset="UTF-8">' + NL
            + '<meta name="viewport" content="width=device-width, initial-scale=1.0">' + NL
            + '<title>pytest field card</title>' + NL
            + '<style>' + NL + CSS % {"scale": PRINT_SCALE} + NL + '</style>' + NL
            + '</head>' + NL + '<body>' + NL + '<div class="wrap">' + NL + NL
            + (NL + NL).join(out) + NL + NL
            + '</div>' + NL + '</body>' + NL + '</html>' + NL)


def check():
    cap = capacity()
    cols = pack()
    sides = [cols[i:i + 2] for i in range(0, len(cols), 2)]
    print("root %s   column capacity %.1f lines   fill target %.0f%%"
          % (PRINT_SCALE, cap, FILL * 100))
    print("(one unit = one line of a <pre> block)" + NL)
    worst = 0.0
    for si, side_cols in enumerate(sides):
        print("side %d of %d   sheet %d %s"
              % (si + 1, len(sides), si // 2 + 1,
                 "front" if si % 2 == 0 else "back"))
        for ci, col in enumerate(side_cols):
            w = sum(weight(CARDS[s][1]) for s in col)
            worst = max(worst, w)
            print("   col%d  %5.1f  (%3.0f%%)  %s"
                  % (ci + 1, w, w / cap * 100, ", ".join(col)))
    print(NL + "%d cards, %d columns, %d sides, %d sheets double-sided"
          % (len(ORDER), len(cols), len(sides), -(-len(sides) // 2)))
    print("heaviest column %.1f of %.1f (%.0f%%)" % (worst, cap, worst / cap * 100))
    if worst > cap:
        print("OVERFLOWS: lower PRINT_SCALE.")
    if len(sides) % 2:
        print("NOTE: odd number of sides, so the last sheet has a blank back.")
    seen = [s for c in cols for s in c]
    assert set(seen) == set(CARDS), "cards missing: %s" % (set(CARDS) - set(seen))
    assert len(seen) == len(set(seen)), "a card is placed twice"
    print("all %d cards placed exactly once" % len(seen))


if __name__ == "__main__":
    check()
    if "--check" not in sys.argv:
        open("pytest-field-card.html", "w", encoding="utf-8").write(render())
        print(NL + "wrote pytest-field-card.html")
