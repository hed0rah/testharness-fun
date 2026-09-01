#!/usr/bin/env python3
"""Build pytest-console.html: the screen-first reference.

The two field cards are shaped by A4. Everything on them is a compromise with
a column height, and the layout is solved rather than chosen. This one is not
printed by default, so it can carry the things that never fit: a system map, a
seam inventory, an evidence matrix, and as many one-liners as are useful.

Layout rules, which are the whole point of the format:

  * tabs across the top, one panel visible at a time
  * inside a panel, a CSS grid with a fixed minimum column width
  * cards stretch to their row height and content sits at the top, so slack
    appears as space UNDER a card rather than as a ragged layout

That last rule is why this is comfortable to write for. A card can be three
lines or forty and the grid stays predictable, which is not true of the print
cards where every line competes with a page boundary.

Printing still works. `@media print` reveals every panel and starts each on a
new page, so a single tab can be printed from the browser's page range.

    python build_console.py            # write pytest-console.html
    python build_console.py --check    # report card counts, write nothing
"""

import sys

from console_content import TABS

NL = chr(10)

CSS = """
:root{
  --bg:#16181C; --panel:#1C1F24; --panel2:#22262C; --ink:#E8E6DF; --soft:#A8ADB4;
  --faint:#6E747C; --line:#2E333A; --hair:#262B31;
  --teal:#00F9DF; --orange:#FF6A2A; --pink:#FF3EB5; --yellow:#FFE900;
  --green:#5FD08A; --red:#FF5C6E;
  --mono:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Menlo,Consolas,monospace;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
:root[data-theme="light"]{
  --bg:#F2F1EE; --panel:#FFFFFF; --panel2:#EAE8E2; --ink:#14181A; --soft:#4A5054;
  --faint:#7C8388; --line:#C9C4B8; --hair:#DCD8CE;
  --teal:#00776C; --orange:#C24312; --pink:#A3006B; --yellow:#8A6A00;
  --green:#24713F; --red:#B01524;
}
@media (prefers-color-scheme:light){
  :root:not([data-theme="dark"]){
    --bg:#F2F1EE; --panel:#FFFFFF; --panel2:#EAE8E2; --ink:#14181A; --soft:#4A5054;
    --faint:#7C8388; --line:#C9C4B8; --hair:#DCD8CE;
    --teal:#00776C; --orange:#C24312; --pink:#A3006B; --yellow:#8A6A00;
    --green:#24713F; --red:#B01524;
  }
}

*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:var(--mono);
     font-size:13px;line-height:1.55;-webkit-font-smoothing:antialiased}
::selection{background:var(--teal);color:var(--bg)}
a{color:var(--teal);text-decoration:none;border-bottom:1px dotted currentColor}

/* ── masthead ─────────────────────────────────────────────────────────── */
header{border-bottom:1px solid var(--line);background:var(--panel);
       position:sticky;top:0;z-index:20}
.top{max-width:1900px;margin:0 auto;padding:.7rem 1.1rem .55rem;
     display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap}
h1{font-size:1.05rem;font-weight:700;letter-spacing:.04em;white-space:nowrap}
h1 em{color:var(--teal);font-style:normal}
.tag{font-size:.62rem;letter-spacing:.2em;text-transform:uppercase;color:var(--faint)}
.spacer{flex:1}
.tbtn{font-family:var(--mono);font-size:.66rem;letter-spacing:.12em;
      text-transform:uppercase;background:none;color:var(--faint);
      border:1px solid var(--line);padding:.28rem .5rem;cursor:pointer}
.tbtn:hover{color:var(--ink);border-color:var(--faint)}

/* ── tabs ─────────────────────────────────────────────────────────────── */
nav{max-width:1900px;margin:0 auto;padding:0 1.1rem;display:flex;
    gap:2px;flex-wrap:wrap;overflow-x:auto}
.tab{font-family:var(--mono);font-size:.7rem;letter-spacing:.13em;
     text-transform:uppercase;background:none;border:none;cursor:pointer;
     color:var(--faint);padding:.5rem .75rem;border-bottom:2px solid transparent;
     white-space:nowrap}
.tab:hover{color:var(--ink)}
.tab[aria-selected="true"]{color:var(--teal);border-bottom-color:var(--teal)}
.tab .n{color:var(--line);margin-right:.4rem}
.tab[aria-selected="true"] .n{color:var(--teal)}

/* ── panels and the card grid ─────────────────────────────────────────── */
main{max-width:1900px;margin:0 auto;padding:1.1rem 1.1rem 5rem}
.panel{display:none}
.panel[data-open]{display:block}
.lede{font-family:var(--sans);font-size:.92rem;line-height:1.5;color:var(--soft);
      max-width:70ch;margin:.2rem 0 1.1rem;border-left:2px solid var(--teal);
      padding-left:.8rem}
.lede b{color:var(--ink);font-weight:600}

.grid{display:grid;gap:11px;align-items:stretch;
      grid-template-columns:repeat(auto-fill,minmax(380px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);padding:.7rem .8rem .8rem;
      display:flex;flex-direction:column}
.card>*:last-child{margin-bottom:0}
.card.hot{border-left:3px solid var(--orange)}
.card.key{border-left:3px solid var(--teal)}
.card.w2{grid-column:span 2}
.card.w3{grid-column:span 3}
@media (max-width:900px){.card.w2,.card.w3{grid-column:span 1}}
@media (min-width:901px) and (max-width:1320px){.card.w3{grid-column:span 2}}

.lab{font-size:.6rem;letter-spacing:.18em;text-transform:uppercase;
     color:var(--orange);font-weight:700;margin-bottom:.55rem;
     display:flex;align-items:center;gap:.5rem}
.card.key .lab{color:var(--teal)}
.lab::after{content:"";flex:1;height:1px;background:var(--hair)}

p{font-family:var(--sans);font-size:.84rem;line-height:1.5;color:var(--soft);
  margin:0 0 .55rem}
p b{color:var(--ink);font-weight:600}
ul{margin:0 0 .55rem;padding-left:1.05rem}
li{font-family:var(--sans);font-size:.82rem;line-height:1.45;color:var(--soft);margin:.22rem 0}
li b{color:var(--ink);font-weight:600}
li code,p code{font-family:var(--mono)}

table{width:100%;border-collapse:collapse;font-size:.76rem;margin:0 0 .55rem}
th,td{text-align:left;padding:.26rem .4rem;border-bottom:1px solid var(--hair);
      vertical-align:top}
th{font-size:.58rem;letter-spacing:.11em;text-transform:uppercase;
   color:var(--faint);font-weight:700}
td.k{color:var(--teal);font-weight:700;white-space:nowrap}
td.o{color:var(--orange);font-weight:700;white-space:nowrap}
tr:last-child td{border-bottom:none}

pre{background:var(--panel2);border-left:2px solid var(--line);
    padding:.5rem .6rem;overflow-x:auto;font-size:.75rem;line-height:1.55;
    margin:0 0 .55rem;white-space:pre;color:var(--ink)}
pre.ok{border-left-color:var(--green)}
pre.no{border-left-color:var(--red)}
pre.tree{border-left-color:var(--orange)}
pre.map{border-left-color:var(--teal);font-size:.735rem;line-height:1.5}
pre .c{color:var(--faint)}
pre .t{color:var(--teal)}
pre .y{color:var(--green);font-weight:600}
pre .r{color:var(--red);font-weight:600}
pre .w{color:var(--yellow)}
pre .a{color:var(--orange);font-weight:600}
pre .q{color:var(--ink);font-weight:700}
code{background:var(--panel2);padding:0 .22rem;color:var(--teal);font-size:.94em}

.rule{font-family:var(--sans);font-size:.82rem;line-height:1.45;color:var(--ink);
      background:var(--panel2);border-left:2px solid var(--orange);
      padding:.4rem .55rem;margin:.1rem 0 .55rem}
.rule b{font-weight:700}
.rule.t{border-left-color:var(--teal)}
.rule.r{border-left-color:var(--red)}
.flag{display:inline-block;font-size:.55rem;letter-spacing:.1em;font-weight:700;
      text-transform:uppercase;padding:.02rem .25rem;border:1px solid currentColor}
.f-y{color:var(--green)} .f-n{color:var(--red)} .f-w{color:var(--yellow)}

footer{max-width:1900px;margin:0 auto;padding:1rem 1.1rem 3rem;
       font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;
       color:var(--faint);display:flex;justify-content:space-between;
       gap:1rem;flex-wrap:wrap;border-top:1px solid var(--line)}

/* ── print: every panel, one per page ─────────────────────────────────── */
@media print{
  :root, :root[data-theme="dark"], :root[data-theme="light"]{
    --bg:#fff; --panel:#fff; --panel2:#f3f2ee; --ink:#000; --soft:#1c1c1c;
    --faint:#4a4a4a; --line:#8d8d8d; --hair:#d0d0d0;
    --teal:#00625a; --orange:#9c3c0d; --green:#1c5233; --red:#7c1223;
    --yellow:#5f4a00; --pink:#7a0055;
  }
  html,body{background:#fff}
  header{position:static;border-bottom:1px solid #000}
  nav,.tbtn{display:none}
  main{padding:0;max-width:none}
  .panel{display:block;break-after:page;page-break-after:always}
  .panel:last-of-type{break-after:auto;page-break-after:auto}
  .panel::before{content:attr(data-title);display:block;font-size:.9rem;
                 font-weight:700;letter-spacing:.12em;text-transform:uppercase;
                 border-bottom:1px solid #000;padding-bottom:.25rem;margin-bottom:.6rem}
  .grid{grid-template-columns:repeat(2,1fr);gap:8px}
  .card{break-inside:avoid;page-break-inside:avoid}
  .card.w2,.card.w3{grid-column:span 2}
  a{color:inherit;border-bottom:none}
  @page{size:A4 portrait;margin:9mm}
}
""".strip()

JS = """
(function () {
  const tabs = [...document.querySelectorAll('.tab')];
  const panels = [...document.querySelectorAll('.panel')];

  function show(id, push) {
    tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.for === id)));
    panels.forEach(p => p.id === id ? p.setAttribute('data-open', '')
                                    : p.removeAttribute('data-open'));
    if (push) history.replaceState(null, '', '#' + id);
    window.scrollTo({ top: 0 });
  }

  tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.for, true)));

  // arrow keys move between tabs, the way the deep dive's sections do
  addEventListener('keydown', e => {
    if (e.target.matches('input,textarea')) return;
    const i = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
    if (e.key === 'ArrowRight') show(tabs[(i + 1) % tabs.length].dataset.for, true);
    if (e.key === 'ArrowLeft') show(tabs[(i - 1 + tabs.length) % tabs.length].dataset.for, true);
    if (/^[1-9]$/.test(e.key) && tabs[+e.key - 1]) show(tabs[+e.key - 1].dataset.for, true);
  });

  const wanted = location.hash.slice(1);
  show(panels.some(p => p.id === wanted) ? wanted : panels[0].id, false);

  const toggle = document.querySelector('.tbtn');
  toggle.addEventListener('click', () => {
    const dark = document.documentElement.getAttribute('data-theme') !== 'light';
    document.documentElement.setAttribute('data-theme', dark ? 'light' : 'dark');
    localStorage.setItem('console-theme', dark ? 'light' : 'dark');
  });
})();
""".strip()

BOOT = ("<script>(function(){var t=localStorage.getItem('console-theme');"
        "if(t)document.documentElement.setAttribute('data-theme',t);})();</script>")


def render():
    tabbar, panels = [], []
    for i, tab in enumerate(TABS):
        tabbar.append(
            '  <button class="tab" data-for="%s" aria-selected="false">'
            '<span class="n">%02d</span>%s</button>' % (tab["id"], i + 1, tab["name"]))
        cards = NL.join(tab["cards"])
        panels.append(
            '<section class="panel" id="%s" data-title="%s">' % (tab["id"], tab["name"]) + NL
            + '  <div class="lede">%s</div>' % tab["lede"] + NL
            + '<div class="grid">' + NL + cards + NL + '</div>' + NL
            + '</section>')

    return (
        '<!DOCTYPE html>' + NL + '<html lang="en">' + NL + '<head>' + NL
        + '<meta charset="UTF-8">' + NL
        + '<meta name="viewport" content="width=device-width, initial-scale=1.0">' + NL
        + '<title>pytest console / testharness-fun</title>' + NL
        + '<style>' + NL + CSS + NL + '</style>' + NL + '</head>' + NL
        + '<body>' + NL + BOOT + NL
        + '<header>' + NL
        + '  <div class="top">' + NL
        + '    <h1>pytest <em>console</em></h1>' + NL
        + '    <span class="tag">testharness-fun // screen reference</span>' + NL
        + '    <span class="spacer"></span>' + NL
        + '    <button class="tbtn" title="toggle theme">theme</button>' + NL
        + '  </div>' + NL
        + '  <nav role="tablist">' + NL + NL.join(tabbar) + NL + '  </nav>' + NL
        + '</header>' + NL + NL
        + '<main>' + NL + (NL + NL).join(panels) + NL + '</main>' + NL + NL
        + '<footer>' + NL
        + '  <span>hed0rah &middot; testharness-fun</span>' + NL
        + '  <span>arrow keys or 1-9 switch tabs &middot; print gives one page per tab</span>' + NL
        + '  <span>github.com/hed0rah/testharness-fun</span>' + NL
        + '</footer>' + NL
        + '<script>' + NL + JS + NL + '</script>' + NL
        + '</body>' + NL + '</html>' + NL)


def check():
    total = 0
    print("%-14s %6s  %s" % ("tab", "cards", "name"))
    print("-" * 60)
    for tab in TABS:
        total += len(tab["cards"])
        print("%-14s %6d  %s" % (tab["id"], len(tab["cards"]), tab["name"]))
    print("-" * 60)
    print("%-14s %6d  across %d tabs" % ("", total, len(TABS)))
    ids = [t["id"] for t in TABS]
    assert len(ids) == len(set(ids)), "duplicate tab id"
    assert all(t["cards"] for t in TABS), "a tab has no cards"
    return total


if __name__ == "__main__":
    check()
    if "--check" not in sys.argv:
        open("pytest-console.html", "w", encoding="utf-8").write(render())
        print(NL + "wrote pytest-console.html")
