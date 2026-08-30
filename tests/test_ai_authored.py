"""What an AI-authored test suite looks like, and what catches it.

Ask a model to write tests for a parser and you get a predictable shape: a
sweep of inputs, each asserting that nothing blew up. It reads as thorough, it
executes most of the code, and it is worth almost nothing, because "does not
crash" is satisfied by a parser that refuses every input.

That is not a hypothetical. tests/test_hostile.py carries the same trap by
construction, and tests/test_mutation.py already proves the whole file survives
`def parse(b): raise ParseError("no")`. This file makes the point measurable
rather than rhetorical: two suites over the same specimens, one written in the
never-crash shape and one written with positive assertions, scored on

    line coverage of the parser        what a coverage report would show
    mutants killed                     whether breaking the code goes red

The AI-shaped suite wins on the first and scores zero on the second.

Coverage is measured here rather than asserted from memory: `sys.settrace`
counts the distinct lines of fwvault/parse.py each suite executes. It is a
crude tracer, deliberately, so that the number owes nothing to a plugin.

Reading list for the argument this file supports is in the deep dive; the
numbers are cited there with sources.
"""

import pathlib
import sys

import pytest

from fwvault.errors import ParseError
from fwvault.parse import UF2_BLOCK_SIZE, parse
from fwvault.testing import RP2040, build_elf, build_uf2

PARSE_SRC = str(pathlib.Path(parse.__code__.co_filename).resolve())


# ── the specimens both suites see ───────────────────────────────────────────

def specimens():
    """The inputs a generated suite would plausibly produce: a valid file, some
    truncations, some corruptions, some noise."""
    valid = build_uf2(blocks=3, family=RP2040)
    return [
        valid,
        build_uf2(blocks=1, family=RP2040),
        build_uf2(blocks=2, bad_end_magic=1),
        build_uf2(blocks=2, wrong_num_blocks=99),
        build_uf2(blocks=2, oversized_payload=9999),
        build_elf(),
        valid[:512],
        valid[:100],
        valid[:0],
        b"",
        b"\x00" * 64,
        b"not firmware at all",
    ]


# ── suite A: the shape a model produces ─────────────────────────────────────

def ai_authored_suite(parse_fn):
    """Every specimen, asserting only that the contract was not escaped.

    This is written the way generated tests are written, not as a strawman.
    It sweeps the input space, it names its cases, it catches the declared
    exception and lets everything else through as a failure. The only thing
    missing is a claim about what the parser should have said.
    """
    for blob in specimens():
        try:
            parse_fn(blob)
        except ParseError:
            pass


# ── suite B: the same specimens, with positive assertions ───────────────────

def asserting_suite(parse_fn):
    """The same sweep, plus what each specimen should actually produce."""
    valid = build_uf2(blocks=3, family=RP2040)

    image = parse_fn(valid)
    assert image.kind == "uf2"
    assert image.block_count == 3
    assert image.size == 3 * UF2_BLOCK_SIZE
    assert image.family == "RP2040"
    assert image.warnings == ()

    one = parse_fn(build_uf2(blocks=1, family=RP2040))
    assert one.block_count == 1

    with pytest.raises(ParseError) as excinfo:
        parse_fn(build_uf2(blocks=2, bad_end_magic=1))
    assert excinfo.value.offset == UF2_BLOCK_SIZE + 508

    noisy = parse_fn(build_uf2(blocks=2, wrong_num_blocks=99))
    assert noisy.block_count == 2
    assert any("declares 99" in w for w in noisy.warnings)

    clamped = parse_fn(build_uf2(blocks=2, oversized_payload=9999))
    assert any("exceeds 476" in w for w in clamped.warnings)

    assert parse_fn(build_elf()).kind == "elf"

    for bad in (valid[:100], b"", b"\x00" * 64, b"not firmware at all"):
        with pytest.raises(ParseError):
            parse_fn(bad)


# ── the mutants ─────────────────────────────────────────────────────────────

def refuses_everything(blob):
    """The mutant an entire never-crash suite cannot see."""
    raise ParseError("no")


def drops_the_clamp_warning(blob):
    from dataclasses import replace

    image = parse(blob)
    return replace(image, warnings=tuple(w for w in image.warnings
                                         if "exceeds" not in w))


def loses_the_block_count(blob):
    from dataclasses import replace

    return replace(parse(blob), block_count=1)


def forgets_the_family(blob):
    from dataclasses import replace

    return replace(parse(blob), family=None)


def swallows_malformed_input(blob):
    """The most dangerous shape: returns something plausible instead of
    raising. A never-crash suite actively rewards this."""
    try:
        return parse(blob)
    except ParseError:
        from fwvault.parse import Image

        return Image(kind="uf2", size=len(blob), payload_bytes=0, block_count=0)


MUTANTS = {
    "refuses everything": refuses_everything,
    "drops the clamp warning": drops_the_clamp_warning,
    "loses the block count": loses_the_block_count,
    "forgets the family": forgets_the_family,
    "swallows malformed input": swallows_malformed_input,
}

SUITES = {"ai-authored": ai_authored_suite, "asserting": asserting_suite}


# ── measurement ─────────────────────────────────────────────────────────────

def lines_covered(suite, parse_fn):
    """Distinct lines of fwvault/parse.py executed by one run of `suite`.

    A twenty-line tracer instead of a coverage plugin, so the number in the
    assertion below is produced by this file and can be read in this file.
    """
    seen = set()

    def trace(frame, event, arg):
        if frame.f_code.co_filename == PARSE_SRC:
            if event == "line":
                seen.add(frame.f_lineno)
            return trace
        return None

    old = sys.gettrace()
    sys.settrace(trace)
    try:
        suite(parse_fn)
    except BaseException:
        pass
    finally:
        sys.settrace(old)
    return seen


def kills(suite, mutant):
    """Did the suite go red against this mutant?"""
    try:
        suite(mutant)
    except BaseException:
        return True
    return False


# ── both suites pass against the real parser ────────────────────────────────

@pytest.mark.parametrize("name", sorted(SUITES), ids=sorted(SUITES))
def test_both_suites_pass_against_the_real_parser(name):
    """Neither suite is broken. That is the premise: on a green build they are
    indistinguishable, which is exactly the problem."""
    assert not kills(SUITES[name], parse), (
        '%s does not pass against the real parser, so the comparison below '
        'measures a broken suite' % name)


# ── the coverage they would report ──────────────────────────────────────────

def test_the_ai_suite_covers_most_of_what_the_asserting_one_does():
    """The number a coverage gate would see.

    The generated suite sweeps the same inputs, so it executes nearly the same
    lines. A coverage report cannot tell these two files apart, and a
    `--cov-fail-under` gate would pass both.
    """
    ai = lines_covered(ai_authored_suite, parse)
    human = lines_covered(asserting_suite, parse)

    assert len(ai) > 40, "the sweep should reach most of the parser"
    ratio = len(ai) / len(human)
    assert ratio > 0.85, (
        "expected the generated suite to look comparable on coverage; "
        "got %d lines vs %d (%.0f%%)" % (len(ai), len(human), ratio * 100))


# ── the score that tells them apart ─────────────────────────────────────────

@pytest.mark.parametrize("mutant", sorted(MUTANTS), ids=lambda s: s.replace(" ", "-"))
def test_the_ai_authored_suite_kills_nothing(mutant):
    """Zero out of five. Every mutant survives a suite whose every assertion is
    "it did not raise something undeclared".

    Note which mutants these are. Three of them return a plausible Image with
    the wrong contents, which is the failure a firmware intake service would
    ship: not a crash, an answer that is quietly false.
    """
    assert not kills(ai_authored_suite, MUTANTS[mutant]), (
        "unexpected: the never-crash suite caught %r. If this fails the "
        "demonstration has drifted, not improved." % mutant)


@pytest.mark.parametrize("mutant", sorted(MUTANTS), ids=lambda s: s.replace(" ", "-"))
def test_the_asserting_suite_kills_all_of_them(mutant):
    """Five out of five, from the same specimens. The difference is not
    coverage, effort or input diversity. It is that each specimen carries a
    claim about what the answer should be."""
    assert kills(asserting_suite, MUTANTS[mutant])


def test_the_scoreboard():
    """The two numbers side by side, as one assertion.

    This is the shape of the finding reported for MUTGEN, where a suite reached
    100% coverage at a 4% mutation score. The mechanism is visible here: the
    generated tests execute the code without constraining it.
    """
    ai_kills = sum(kills(ai_authored_suite, m) for m in MUTANTS.values())
    human_kills = sum(kills(asserting_suite, m) for m in MUTANTS.values())
    ai_cov = len(lines_covered(ai_authored_suite, parse))
    human_cov = len(lines_covered(asserting_suite, parse))

    assert (ai_kills, human_kills) == (0, len(MUTANTS))
    assert ai_cov / human_cov > 0.85, (
        "coverage %d/%d, mutants killed %d/%d"
        % (ai_cov, human_cov, ai_kills, len(MUTANTS)))


# ── the gate that would have caught it ──────────────────────────────────────

def test_a_mutation_gate_rejects_the_generated_suite():
    """The acceptance criterion this file argues for.

    A generated suite is admitted only if it kills a threshold of mutants. The
    threshold is a policy decision; that there must be one is not. Coverage
    cannot serve, because both suites clear any coverage bar you would set.
    """
    def mutation_score(suite):
        return sum(kills(suite, m) for m in MUTANTS.values()) / len(MUTANTS)

    THRESHOLD = 0.8
    assert mutation_score(asserting_suite) >= THRESHOLD
    assert mutation_score(ai_authored_suite) < THRESHOLD


def test_the_demonstration_is_not_rigged():
    """A guard on this whole file.

    Every assertion above holds if `specimens()` returned nothing, or if the
    mutants were not really different from the parser. Both are checked, so the
    file cannot pass by being empty.
    """
    assert len(specimens()) >= 10

    for name, mutant in MUTANTS.items():
        differs = False
        for blob in specimens():
            try:
                mine = parse(blob)
            except ParseError:
                mine = "raised"
            try:
                theirs = mutant(blob)
            except ParseError:
                theirs = "raised"
            if mine != theirs:
                differs = True
                break
        assert differs, "%s produces identical output on every specimen" % name
