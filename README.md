# testharness-fun

Test harnesses and frameworks, worked all the way through in pytest -- fixtures,
the five test doubles, monkeypatching and its traps, mock transports, ASGI apps
driven with and without a client, parser corpora, hostile input, property-based
testing, differential testing, guardrail proofs, and the meta-test tier that
stops a suite rotting in the direction of passing.

Every technique runs against a real specimen project in this repo. Nothing here
is a snippet.

    python -m pytest -q          # 547 passed, 3 skipped, 1 xfailed  (no install, no deps)
    pip install -e .[test]       # + hypothesis, httpx, starlette
    python -m pytest -q          # 557 passed, 2 skipped, 1 xfailed

Hosted: https://hed0rah.github.io/testharness/testharness_deep-dive.html
(field card: https://hed0rah.github.io/testharness/pytest-field-card.html)

This repo is the source of truth. The two HTML pages are mirrored into
[hed0rah.github.io](https://github.com/hed0rah/hed0rah.github.io)'s own
`testharness/` directory so they sit alongside the other deep dives, the same
pattern already used for esp32, lora, routeros and protocols-fun.

Sibling repos: [protocols-fun](https://github.com/hed0rah/protocols-fun),
[ipv6-fun](https://github.com/hed0rah/ipv6-fun).

## What's here

```
terms.py                     the term list, once. everything glossary is generated from it
card_content.py              recipe cards for the reference card
card_content_basics.py       cards for the beginner card
frag.html                    deep dive body; the built page is generated from it

gen_glossary.py              terms.py -> GLOSSARY.md, glossary_cards.py, frag.html section
build_card.py                lays out either card; solves the column fit against A4
build_basics.py              the beginner card, pinned to one sheet

GLOSSARY.md                  67 terms, generated
testharness_deep-dive.html   20 sections, generated from frag.html
pytest-field-card.html       glossary + 25 recipes, 3 sheets double-sided
pytest-basics-card.html      14 cards, 1 sheet, larger type

src/fwvault/                 the specimen: a firmware artifact intake service
tests/                       one file per technique family
```

Three surfaces, three jobs, and they are kept separate on purpose:

| surface | job | shape |
|---|---|---|
| `GLOSSARY.md`, card side 1, deep dive §02 | **look it up** | one line per term, grouped |
| the field cards | **do it** | command, snippet, table. No argument |
| the deep dive | **learn it** | narrative, worked examples, the reasoning |

The editorial rule that keeps them apart: a callout stays on a printed card if
it changes what you type, and becomes `<div class="why">` if it argues why.
`.why` blocks are stripped at render and carry a `data-see` naming the deep dive
section that makes the case. `tests/test_cards.py` checks that section exists and
actually discusses it, so cutting an argument from the card cannot lose it.

### Regenerating

```sh
python gen_glossary.py     # after editing terms.py
python build_card.py       # after editing card_content.py
python build_basics.py
build.py frag.html testharness_deep-dive.html "<title>"
```

`tests/test_cards.py` fails if any generated file is stale, if a cross-reference
cites a section number that moved, or if a column would overflow its page.

## The test files, and what each one is for

| file | technique |
|---|---|
| `conftest.py` | the three jobs of a conftest: isolate, supply, extend pytest |
| `test_parse.py` | the assertion vocabulary; parametrize and IDs |
| `test_parametrize.py` | indirect, `pytest_generate_tests`, stacking |
| `test_markers.py` | skip vs xfail, `strict=True`, `pytest.param`, flaky policy |
| `test_hostile.py` | truncation sweeps, bit flips, seeded fuzz |
| `test_property.py` | hypothesis: round-trip, invariant, never-crash |
| `test_policy.py` | proving a refusal happens, and for the right reason |
| `test_doubles.py` | dummy / stub / fake / spy / mock, with a working example of each |
| `test_monkeypatch.py` | every method, four real traps, and when not to patch at all |
| `test_transport.py` | retry schedules, cache staleness, the `net`-marked gap |
| `test_asgi_raw.py` | a 20-line ASGI test client, and what only it can do |
| `test_asgi_clients.py` | the same app through httpx.ASGITransport and TestClient |
| `test_store.py` | tmp_path, atomicity, path traversal done by regeneration |
| `test_cli.py` | in-process with capsys, and the four cases needing a real process |
| `test_time.py` | inject a clock, do not freeze one, never sleep in a test |
| `test_fixtures.py` | scope, teardown order, factories, and the anti-pattern |
| `test_differential.py` | two independent implementations, compared over a corpus |
| `test_contract.py` | `__all__`, codes, schema version, the route table |
| `test_lean_install.py` | the dependency boundary, statically and behaviourally |
| `test_suite_hygiene.py` | the suite as data: does every test still assert anything |
| `test_cards.py` | the published artifacts as data: generated files, cross-refs, page fit |
| `test_ai_authored.py` | a generated-shaped suite vs an asserting one, scored on coverage and mutants |
| `test_oracle_independence.py` | why the author cannot grade its own homework, demonstrated without a model |
| `test_metamorphic.py` | round trip, invariance, equivariance, idempotence: assertions with no oracle |
| `test_mutation.py` | hand-written mutants, each paired with its catcher |

## Four things this repo argues

**Inject what you own, patch what you do not.** Patching a seam you control
passes even after the code stops using that seam. Passing a fake notices
immediately. `test_monkeypatch.py` demonstrates exactly that, both ways.

**Prefer a fake to a mock.** A mock fails inside the double, so the message
describes a call that did not happen rather than a behaviour that is wrong. A
fake can be wrong in a way a test notices; a stub returning 200 forever cannot
fail to model a 404, because it was never modelling anything.

**A never-crash test needs a positive companion.** Every hostile-input
assertion in `test_hostile.py` passes against `def parse(b): raise
ParseError("no")`. The companion lives in the same file so the pairing is
visible.

**Coverage cannot tell you whether your tests assert anything.** Mutation
testing can: break the code on purpose and see whether the suite notices.
`test_mutation.py` does the cheap version, and the most useful row in it is
that every assertion in `test_hostile.py` passes against a parser that raises
unconditionally.

**A suite that only checks for crashes is worth nothing, and looks identical
to one that works.** `test_ai_authored.py` puts two suites over the same twelve
specimens: the never-crash shape a model produces, and the same specimens with
positive assertions. They execute **the same 93 lines** of the parser, so no
coverage gate can tell them apart. One kills 0 of 5 mutants; the other kills 5.

**Some assertions need no oracle at all.** A metamorphic relation says how two
runs must relate, never what either produces: `serialize_uf2(walk_uf2(b)) == b`
is checkable without anyone knowing the right answer. That makes it the
technique a generated suite cannot fake, because a relation is a claim about the
problem rather than about the code.

**A check nobody has seen fire is a check nobody should trust.** Every
meta-check here has a test that proves it can fail. Two of them were wrong when
first written. One scanner flagged its own documentation; its replacement could
no longer see the string literals it was hunting. Both shipped green.

## Things that were found by writing this

Kept because they are the point, not despite it.

- a truncation sweep stepping by 97 never lands on a multiple of 512, so all
  twenty cases took the same early branch and none reached the walker. The
  meta-test that checks the sweep caught it.
- `from fwvault import parse` gives you the re-exported **function**, which has
  shadowed the **module** of the same name. `import fwvault.parse as m` does not
  save you; `importlib.import_module` does.
- `monkeypatch.setattr("pkg.mod.CONST", x)` does not move a dataclass field
  default. That default was evaluated once, at class-creation time.
- `python -I` implies `-E`, so a cold-start import test that passes `PYTHONPATH`
  gets an empty `sys.path` and fails looking exactly like a packaging bug.
- pytest's collection glob is `test*`, not `test_*`. A helper named `tests_in`
  is collected as a test, and if it is a generator the whole file fails to
  collect.
- `pytest.fail.Exception` derives from `BaseException`, not `Exception`, so a
  failing `pytest.raises(...)` is invisible to `except Exception` and to an
  enclosing `pytest.raises(AssertionError)`.
- the first "PRECEDENCE gets alphabetised" mutant survived, and it was not a
  hole in the suite: alphabetical order happens to keep `OVERSIZE` first for
  the specimen that was chosen, so the mutation changed nothing observable.
  That is an *equivalent mutant*, and telling them apart from real holes is the
  manual cost of mutation testing.

## Rebuilding the page

`testharness_deep-dive.html` is generated: a local build script splices
`frag.html` into a shared site template, so the page keeps the same shell,
stylesheet and section-dial script as the other deep dives.

    build.py frag.html testharness_deep-dive.html "<title>"

**Edit `frag.html`, never the built page.** A hand edit to the output is lost
on the next build. The builder regenerates the section labels from the table
of contents and asserts that the section ids match it, in order, so a
mismatch fails the build instead of producing a page whose navigation lies.

Fonts load from Google Fonts, so preview in a real browser.

The field card has no builder and no external assets. Open
`pytest-field-card.html` and print it: the `@media print` rules force two
columns on A4 portrait, drop the panel fills, and take it to black on white.

## Requirements

Python 3.11+. pytest to run the suite. Everything else is optional and skips
with a reason that prints, because `addopts = "-rs"`.
