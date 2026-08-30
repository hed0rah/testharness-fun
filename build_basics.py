#!/usr/bin/env python3
"""Lay out the beginner card: one sheet, front and back, larger type.

Reuses build_card's layout engine. Only three things differ: the content, a
bigger root font size, and a target of exactly four columns so it lands on one
double-sided sheet. If the content grows past what four columns hold at this
size, check() says so rather than silently printing a third page.

    python build_basics.py            # write pytest-basics-card.html
    python build_basics.py --check    # report column loads, write nothing
"""

import sys

import build_card as engine
from card_content_basics import CARDS

NL = chr(10)

# Bigger than the reference card's 14px: this one is read by someone who has
# not used pytest, not scanned by someone who has. Code lands near 7.6pt.
PRINT_SCALE = "16px"

ORDER = [
    # side 1: what a test is and how to run one
    "your-first-test", "running-it", "what-pytest-looks-for",
    "reading-a-failure",
    "fixtures", "teardown", "conftest",
    # side 2: the words, and the ideas behind them
    "factories", "free-fixtures",
    "parametrize",
    "glossary", "glossary-doubles",
    "good-habits", "when-stuck",
]

TITLE = 'pytest <span class="g">/ starting out</span>'


def configure():
    """Point the engine at this card's content and scale."""
    engine.CARDS = CARDS
    engine.ORDER = ORDER
    engine.TITLE = TITLE
    engine.PRINT_SCALE = PRINT_SCALE


def main():
    configure()
    cap = engine.capacity()
    cols = engine.balance(4)
    loads = [sum(engine.weight(CARDS[s][1]) for s in c) for c in cols]

    print("root %s   column capacity %.1f lines" % (PRINT_SCALE, cap))
    for i, (col, load) in enumerate(zip(cols, loads)):
        side, face = i // 2 + 1, "left" if i % 2 == 0 else "right"
        print("  side %d %-5s  %5.1f  (%3.0f%%)  %s"
              % (side, face, load, load / cap * 100, ", ".join(col)))

    print(NL + "%d cards, %d columns, 2 sides, 1 sheet double-sided"
          % (len(ORDER), len(cols)))
    print("heaviest column %.1f of %.1f (%.0f%%)"
          % (max(loads), cap, max(loads) / cap * 100))

    over = [i for i, l in enumerate(loads) if l > cap]
    if over or len(cols) != 4:
        print("DOES NOT FIT on one sheet at %s." % PRINT_SCALE)
        print("Lower PRINT_SCALE, or move a card out of ORDER.")
        return 1

    seen = [s for c in cols for s in c]
    assert set(seen) == set(CARDS), "unplaced: %s" % (set(CARDS) - set(seen))
    print("all %d cards placed exactly once" % len(seen))

    if "--check" not in sys.argv:
        # engine.pack() picks its own column count; this card is pinned to
        # four, so hand the balanced split straight to the renderer.
        engine.pack = lambda: cols
        open("pytest-basics-card.html", "w", encoding="utf-8").write(engine.render())
        print(NL + "wrote pytest-basics-card.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
