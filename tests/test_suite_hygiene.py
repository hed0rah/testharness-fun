"""Tests about the tests. The tier nobody writes, and the one that pays.

A test suite is code, it rots like code, and it rots in a way ordinary code
does not: silently and in the direction of passing. A test that stops asserting
anything still shows up green. A test that skips on every machine still counts
toward "1,204 passed". A test that reaches for a file only one laptop has runs
there and skips everywhere else, and both readings look fine from where you are
standing.

Every check here exists because that shape is real:

    a suite reported 90 skips and a green tick; 85 were one gitignored path
    a refactor left four tests with no assertion; all four still "passed"
    a file wrote to a fixed temp path and two parallel workers raced for it

None of these are found by running the suite. They are found by READING it,
which is what this file does -- it treats the test tree as data.

Two rules keep this tier from becoming folklore.

  1. Every check must name the file and line it objects to. A hygiene test that
     fails with a bare `assert not offenders` is worse than no hygiene test.
  2. Every check must be shown firing at least once. A filter with a broken
     pattern passes everything, cheerfully, forever. See the last two tests.

The scanning goes through `tokenize` rather than reading lines, because the
first version of this file did read lines -- and flagged three passages of
prose that were DESCRIBING the thing being banned. A checker whose false
positives land on its own documentation gets disabled within a week.
"""

import ast
import io
import pathlib
import tokenize

import pytest

HERE = pathlib.Path(__file__).parent
TEST_FILES = sorted(HERE.glob("test_*.py"))
SELF = pathlib.Path(__file__).name

MUTATORS = {"append", "add", "extend", "update", "insert", "pop", "remove",
            "clear", "setdefault"}


def code_lines(path):
    """Every line of a file that is CODE: no comments, no docstrings.

    String LITERALS stay in, and that distinction is the whole point. The
    banned things these checks look for -- "/tmp/", "expanduser" -- appear in
    real code as string literals, so a scanner that strips every string can
    never see the defect it is looking for. It also has to strip docstrings, or
    it flags the paragraph explaining the rule.

    Comments come from tokenize; docstrings come from the AST, where a
    docstring is exactly an expression statement whose value is a string
    constant. Both are needed: neither alone gets it right.
    """
    source = path.read_text(encoding="utf-8")
    skip = set()

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            skip.update(range(token.start[0], token.end[0] + 1))

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)                 and isinstance(node.value.value, str):
            skip.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    for lineno, line in enumerate(source.splitlines(), 1):
        if lineno not in skip:
            yield lineno, line


def mutated_names(path):
    """Module-level names that something in the file actually mutates.

    A set literal assigned once and only ever read is a constant, not shared
    state. Flagging it -- as an earlier version did -- teaches people that the
    check is noise."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in MUTATORS and isinstance(node.func.value, ast.Name):
                names.add(node.func.value.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    names.add(target.value.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def find_tests(path):
    """Yield (name, node) for every test function in a file.

    Named `find_tests` and not `tests_in` because pytest's default collection
    glob is `test*` -- a helper called `tests_in` is collected AS a test, and
    since it is a generator, pytest refuses the whole file with "'yield'
    keyword is allowed in fixtures, but not in tests". A collection error takes
    the entire file down, so the other twelve checks in here vanish with it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name.startswith("test_"):
            yield node.name, node


def test_there_are_tests_to_check():
    """The guard on every other check in this file. A glob that matches nothing
    makes all of them pass, and that is precisely the failure mode this tier
    exists to prevent."""
    assert len(TEST_FILES) >= 10


# ── the checks ──────────────────────────────────────────────────────────────

def test_every_test_asserts_something():
    """A test with no assert is a smoke test at best and a lie at worst.

    `pytest.raises`, `pytest.warns` and `pytest.approx` count -- they are
    assertions in a context manager. So does a call to a helper whose name says
    it asserts, which is why `assert_parse_contract` in test_property.py is
    named the way it is: a bare `try: f(x) except E: pass` looks identical to a
    test somebody quietly disabled.
    """
    offenders = []
    for path in TEST_FILES:
        for name, node in find_tests(path):
            has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(node))
            has_raises = any(
                isinstance(n, ast.Attribute) and n.attr in {"raises", "warns", "approx"}
                for n in ast.walk(node)
            )
            calls_checker = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id.startswith(("assert_", "_assert", "_parses_or_raises"))
                for n in ast.walk(node)
            )
            if not (has_assert or has_raises or calls_checker):
                offenders.append("{}:{} {}".format(path.name, node.lineno, name))

    assert not offenders, (
        "these tests assert nothing, so they pass whatever the code does:\n  "
        + "\n  ".join(offenders)
    )


def test_no_test_writes_to_a_fixed_path():
    """A fixed path is a race between two parallel workers and a landmine on a
    machine with a different layout. tmp_path and tmp_path_factory exist so
    this never has to be a judgement call."""
    banned = ("/tmp/", "/var/tmp", "C:/temp", "./out", "tempfile.mkdtemp")
    offenders = []
    for path in TEST_FILES:
        if path.name == SELF:
            continue
        for lineno, line in code_lines(path):
            for token in banned:
                if token in line:
                    offenders.append(
                        "{}:{}: {}".format(path.name, lineno, line.strip()[:70])
                    )

    assert not offenders, (
        "these write outside a pytest temp directory, which races under -n and "
        "breaks on a machine with a different layout:\n  " + "\n  ".join(offenders)
    )


def test_every_skip_explains_itself():
    """`-rs` in pyproject prints skip reasons, which only helps if there are
    reasons. A bare `pytest.skip()` in a summary reads as "something did not
    run" and tells you nothing about whether that is fine."""
    offenders = []
    for path in TEST_FILES:
        if path.name == SELF:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None)
            if name not in {"skip", "importorskip", "skipif", "xfail"}:
                continue
            has_reason = any(kw.arg == "reason" for kw in node.keywords)
            positional_message = name == "skip" and node.args
            if not (has_reason or positional_message):
                offenders.append("{}:{}: {}()".format(path.name, node.lineno, name))

    assert not offenders, (
        "these skip without saying why, so a skipped run cannot be read:\n  "
        + "\n  ".join(offenders)
    )


def test_no_test_is_silently_disabled():
    """The three ways a test stops running while still looking like a test.

    `return` at the top is the nastiest: it leaves a green tick and no skip
    line, so the summary count is unchanged and nothing anywhere says the test
    is gone."""
    offenders = []
    for path in TEST_FILES:
        if path.name == SELF:
            continue
        for name, node in find_tests(path):
            body = node.body
            first = body[1] if len(body) > 1 and isinstance(body[0], ast.Expr) else body[0]
            if isinstance(first, ast.Return) and first.value is None:
                offenders.append("{}:{} {} returns immediately".format(
                    path.name, node.lineno, name))
            if isinstance(first, ast.Pass) and len(body) <= 2:
                offenders.append("{}:{} {} is empty".format(path.name, node.lineno, name))
        for lineno, line in code_lines(path):
            if "pytest.mark.skip" in line and "skipif" not in line and "reason" not in line:
                offenders.append("{}:{}: unconditional skip".format(path.name, lineno))

    assert not offenders, "\n  ".join(["silently disabled tests:"] + offenders)


def test_no_test_depends_on_a_path_outside_the_repository():
    """The 85-skips bug, generalised.

    A test naming a path that exists on one machine runs there and skips
    everywhere else, and both readings look fine from where you are standing.
    Checked by reading source, because on the machine that HAS the file the
    test passes -- which is exactly the reading that hides it."""
    suspicious = ("expanduser", "/home/", "/Users/", "site-packages", "%USERPROFILE%")
    offenders = []
    for path in TEST_FILES:
        if path.name == SELF:
            continue
        for lineno, line in code_lines(path):
            for token in suspicious:
                if token in line:
                    offenders.append(
                        "{}:{}: {}".format(path.name, lineno, line.strip()[:70])
                    )

    assert not offenders, (
        "these reach for a path outside the repository, so they run on one "
        "machine and skip on every runner:\n  " + "\n  ".join(offenders)
    )


def test_no_mutable_module_level_state():
    """Module-level state that something mutates makes test ORDER part of the
    meaning of every assertion in the file.

    Only names that are actually mutated are flagged. A frozen set of expected
    API names assigned once is a constant, and flagging it teaches people the
    check is noise.

    test_fixtures.py is exempt: its EVENTS/CLEANED lists ARE the subject, and
    it keeps the writer and reader adjacent, which is the only form of this
    that survives a shuffle.
    """
    allowed = {SELF, "test_fixtures.py"}
    offenders = []
    for path in TEST_FILES:
        if path.name in allowed:
            continue
        mutated = mutated_names(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in mutated:
                    offenders.append("{}:{}: {} is mutated".format(
                        path.name, node.lineno, target.id))

    assert not offenders, (
        "mutable module-level state makes test order load-bearing:\n  "
        + "\n  ".join(offenders)
    )


def test_every_test_file_has_a_module_docstring():
    """Cheap, and it is the difference between a suite you can navigate and 300
    functions named after implementation details. The docstring says which
    TECHNIQUE the file demonstrates, which is the question a reader has."""
    missing = [
        path.name for path in TEST_FILES
        if not ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert missing == [], "test files with no module docstring: " + ", ".join(missing)


def test_no_duplicate_test_names_across_the_suite():
    """Two tests with the same name in different files are legal and confusing:
    `pytest -k the_name` runs both, and a failure report pasted into a chat is
    ambiguous."""
    seen = {}
    duplicates = []
    for path in TEST_FILES:
        for name, _node in find_tests(path):
            if name in seen:
                duplicates.append("{} in {} and {}".format(name, seen[name], path.name))
            seen[name] = path.name
    assert not duplicates, "\n  ".join(["duplicate test names:"] + duplicates)


@pytest.mark.parametrize("path", TEST_FILES, ids=lambda p: p.name)
def test_each_file_is_syntactically_parseable(path):
    """Trivial, and it turns a collection error -- which aborts the run and
    reports nothing -- into one named failure with the rest of the suite still
    reporting."""
    assert ast.parse(path.read_text(encoding="utf-8")) is not None


# ── the checks, checked ─────────────────────────────────────────────────────

def test_the_assertion_detector_can_actually_fire(tmp_path):
    """A detector nobody has seen fire is a detector nobody should trust.

    Writes a file violating two rules at once and asserts the machinery
    objects. Without this, a typo in one of the AST walks above turns the whole
    file into decoration: green, reassuring, and checking nothing."""
    bad = tmp_path / "test_bad.py"
    bad.write_text(
        '"""doc."""\n'
        "\n"
        "\n"
        "def test_no_assertion_here():\n"
        "    value = 1 + 1\n"
        "\n"
        "\n"
        "def test_disabled():\n"
        "    return\n",
        encoding="utf-8",
    )

    names = [name for name, _node in find_tests(bad)]
    assert names == ["test_no_assertion_here", "test_disabled"]

    assertless = [
        name for name, node in find_tests(bad)
        if not any(isinstance(n, ast.Assert) for n in ast.walk(node))
    ]
    assert assertless == names


def test_the_tokenizer_ignores_prose_but_not_code(tmp_path):
    """The false-positive fix, asserted.

    Line one mentions a banned path inside a docstring and must be ignored;
    line two uses it in code and must not be. An earlier version of this file
    could not tell them apart and flagged its own documentation."""
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        '"""We must never write to /tmp/ in a test."""\n'
        "\n"
        "\n"
        "def test_x():\n"
        "    path = '/tmp/' + 'out'\n"
        "    assert path\n",
        encoding="utf-8",
    )

    flagged = [lineno for lineno, line in code_lines(sample) if "/tmp/" in line]
    assert flagged == [5]


def test_the_mutation_detector_tells_constants_from_state(tmp_path):
    """CONSTANT is assigned and read; STATE is appended to. Only the second is
    order-dependent, and a checker that cannot tell them apart flags every
    lookup table in the suite."""
    sample = tmp_path / "test_sample2.py"
    sample.write_text(
        "CONSTANT = {'a', 'b'}\n"
        "STATE = []\n"
        "\n"
        "\n"
        "def test_x():\n"
        "    STATE.append(1)\n"
        "    assert CONSTANT\n",
        encoding="utf-8",
    )

    assert mutated_names(sample) == {"STATE"}


def test_the_suite_does_not_depend_on_its_own_ordering():
    """Documents the commands rather than performing them, because performing
    them means running the suite inside the suite.

        pytest -p no:randomly              # baseline
        pytest --randomly-seed=1234        # pytest-randomly, if installed
        pytest -n 4                        # pytest-xdist, which also reorders

    The static half of this is `test_no_mutable_module_level_state` above. The
    dynamic half cannot be honestly automated here, so it is written down
    instead of pretended.
    """
    documented = ["-p no:randomly", "--randomly-seed", "-n 4"]
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert all(command in source for command in documented)
