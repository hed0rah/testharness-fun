"""The term list, once.

GLOSSARY.md, the glossary cards on the printed reference, and the deep dive's
lookup section are all generated from this file. They had already drifted apart
once when each held its own copy.

Each entry is (term, one-line meaning, deep-dive section id). The section id is
an anchor in testharness_deep-dive.html, so a term can always be traced to the
place that explains it properly. `None` means the deep dive does not cover it
and the one-liner is all there is.

Meanings are one line. Anything needing two lines is an argument, and arguments
belong in the deep dive, not in a lookup table.
"""

GROUPS = [

("the basics", [
    ("test", "a function whose name starts with <code>test</code>. It passes if it does not raise", "collect"),
    ("assertion", "a line stating what must be true. <code>assert x == y</code>", "assert"),
    ("test suite", "all your tests together", None),
    ("test runner", "the tool that finds and runs them. pytest is one", "collect"),
    ("collection", "pytest finding your tests, before running any", "collect"),
    ("fail vs error", "<i>fail</i> = an assertion was false. <i>error</i> = it blew up before reaching one", "assert"),
    ("AAA", "arrange, act, assert. The three parts of most tests, in that order", None),
    ("TDD", "write the failing test first, then the code that makes it pass", None),
]),

("fixtures", [
    ("fixture", "named setup a test asks for by putting its name in the arguments", "fixtures"),
    ("factory fixture", "a fixture returning a <b>function</b>, so a test can make several things", "fixtures"),
    ("setup / teardown", "before and after. In pytest, teardown is whatever follows <code>yield</code>", "fixtures"),
    ("scope", "how often a fixture is rebuilt: function, class, module, package, session", "fixtures"),
    ("autouse", "a fixture applied to every test without being asked for", "fixtures"),
    ("conftest.py", "shared fixtures for a folder and everything under it. No import needed", "collect"),
    ("override", "a fixture in a test file shadowing one of the same name from conftest", "fixtures"),
    ("tmp_path", "built in: an empty folder, new per test, cleaned up for you", "fixtures"),
    ("capsys / capfd", "built in: captured output. capfd when the write bypasses Python", "assert"),
    ("caplog", "built in: log records. Set the level or you capture nothing", "assert"),
    ("monkeypatch", "built in: change something temporarily, put back automatically", "patch"),
]),

("running and selecting", [
    ("test id", "the name in the report, e.g. <code>test_naming[2-many]</code>", "param"),
    ("parametrize", "run one test many times with different inputs, each reported separately", "param"),
    ("indirect", "send a parametrize value to a fixture, so each case gets setup and teardown", "param"),
    ("marker", "a label on a test: <code>@pytest.mark.slow</code>. Select with <code>-m</code>", "markers"),
    ("skip / skipif", "does not apply here. skipif decides at collection", "markers"),
    ("xfail", "known broken. Needs <code>strict=True</code> or it stays green once fixed", "markers"),
    ("xpass", "an xfail that unexpectedly passed. Usually means delete the marker", "markers"),
    ("deselect", "excluded from this run by <code>-k</code> or <code>-m</code>. Not the same as skipped", "collect"),
]),

("test doubles", [
    ("test double", "any stand-in used instead of the real thing", "doubles"),
    ("dummy", "passed only to fill a signature. Never actually used", "doubles"),
    ("stub", "always returns the same canned answer", "doubles"),
    ("fake", "a real but simplified implementation. A dict instead of a database", "doubles"),
    ("spy", "works, and records how it was called", "doubles"),
    ("mock", "a spy that also asserts it was called correctly", "doubles"),
    ("patching", "replacing something in place, by name", "patch"),
    ("injection", "passing the collaborator in, rather than the code fetching it itself", "patch"),
    ("seam", "a place you can change behaviour without editing there. An argument is one", "orient"),
    ("mock transport", "a fake put in the place where code would talk to the network", "transport"),
]),

("kinds of test", [
    ("unit", "one function or class, nothing real underneath it", None),
    ("integration", "several pieces together, often with a real file or database", None),
    ("end-to-end", "the whole system as a user meets it. Slow, valuable, few", None),
    ("regression test", "written to pin a bug you just fixed, so it cannot come back", None),
    ("smoke test", "does it start at all", None),
    ("property-based", "assert a rule for all inputs and let a tool hunt counterexamples", "hostile"),
    ("fuzzing", "throw generated input at it and check nothing escapes the contract", "hostile"),
    ("differential", "run two implementations over one input; whichever disagrees is wrong", "differential"),
    ("oracle", "differential testing where the reference is a trusted external tool", "differential"),
    ("golden / snapshot", "compare output against a stored known-good file", None),
    ("contract test", "pin the shape you publish: names, codes, status codes, schema version", "meta"),
    ("meta-test", "a test about the test suite, e.g. does every test still assert", "meta"),
]),

("test quality", [
    ("coverage", "which lines ran. <b>Not</b> whether anything checked them", "mutation"),
    ("branch coverage", "did both sides of each <code>if</code> run", "mutation"),
    ("mutation testing", "break the code deliberately and see whether the suite notices", "mutation"),
    ("equivalent mutant", "a deliberate break that changes no behaviour, so nothing can catch it", "mutation"),
    ("mutation gate", "admit a generated suite only if it kills a threshold of mutants", "ai"),
    ("flaky", "passes and fails without the code changing. Always a bug, never noise", "markers"),
    ("quarantine", "move a flaky test behind a deselected marker with a ticket", "markers"),
    ("test smell", "a sign the test or code is wrong. More patching than assertion is one", "meta"),
]),

("an AI author", [
    ("apparatus", "the machinery that makes reading generated output unnecessary: tests, types, sanitizers, canaries", "ai"),
    ("provenance separation", "whatever wrote the code does not grade it, and ideally is not the same family", "ai"),
    ("self-preference bias", "an evaluator scoring its own generations higher than a human would", "ai"),
    ("intrinsic self-correction", "a model revising its own output with no external signal. Does not reliably work", "ai"),
    ("external feedback", "a signal from outside the model. A test run is one, which is the point", "ai"),
    ("characterization test", "assertions transcribed from what the code currently does. Pins change, not correctness", "ai"),
    ("the oracle problem", "knowing what the right answer is, independently of the thing being tested", "differential"),
    ("metamorphic relation", "a property linking two runs when you cannot state the answer for either", "ai"),
    ("translation validation", "proving one output matches its input for this run, rather than proving the tool", "ai"),
    ("the intent gap", "tests cannot check that they encode what was actually wanted. No technical fix", "ai"),
]),

]


def flat():
    """(group, term, meaning, section) for every entry."""
    for group, items in GROUPS:
        for term, meaning, see in items:
            yield group, term, meaning, see


def count():
    return sum(len(items) for _g, items in GROUPS)
