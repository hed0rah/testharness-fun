# pytest glossary

Generated from `terms.py`. Edit that, then run `gen_glossary.py`.

Short meanings, grouped by when you meet them. The `see` column is a
section of `testharness_deep-dive.html`, which is where the long
version of each idea lives.

## Explaining it in forty-five seconds

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

## the basics

| term | meaning | see |
|---|---|---|
| **test** | a function whose name starts with `test`. It passes if it does not raise | `collect` |
| **assertion** | a line stating what must be true. `assert x == y` | `assert` |
| **test suite** | all your tests together |  |
| **test runner** | the tool that finds and runs them. pytest is one | `collect` |
| **collection** | pytest finding your tests, before running any | `collect` |
| **fail vs error** | *fail* = an assertion was false. *error* = it blew up before reaching one | `assert` |
| **AAA** | arrange, act, assert. The three parts of most tests, in that order |  |
| **TDD** | write the failing test first, then the code that makes it pass |  |

## fixtures

| term | meaning | see |
|---|---|---|
| **fixture** | named setup a test asks for by putting its name in the arguments | `fixtures` |
| **factory fixture** | a fixture returning a **function**, so a test can make several things | `fixtures` |
| **setup / teardown** | before and after. In pytest, teardown is whatever follows `yield` | `fixtures` |
| **scope** | how often a fixture is rebuilt: function, class, module, package, session | `fixtures` |
| **autouse** | a fixture applied to every test without being asked for | `fixtures` |
| **conftest.py** | shared fixtures for a folder and everything under it. No import needed | `collect` |
| **override** | a fixture in a test file shadowing one of the same name from conftest | `fixtures` |
| **tmp_path** | built in: an empty folder, new per test, cleaned up for you | `fixtures` |
| **capsys / capfd** | built in: captured output. capfd when the write bypasses Python | `assert` |
| **caplog** | built in: log records. Set the level or you capture nothing | `assert` |
| **monkeypatch** | built in: change something temporarily, put back automatically | `patch` |

## running and selecting

| term | meaning | see |
|---|---|---|
| **test id** | the name in the report, e.g. `test_naming[2-many]` | `param` |
| **parametrize** | run one test many times with different inputs, each reported separately | `param` |
| **indirect** | send a parametrize value to a fixture, so each case gets setup and teardown | `param` |
| **marker** | a label on a test: `@pytest.mark.slow`. Select with `-m` | `markers` |
| **skip / skipif** | does not apply here. skipif decides at collection | `markers` |
| **xfail** | known broken. Needs `strict=True` or it stays green once fixed | `markers` |
| **xpass** | an xfail that unexpectedly passed. Usually means delete the marker | `markers` |
| **deselect** | excluded from this run by `-k` or `-m`. Not the same as skipped | `collect` |

## test doubles

| term | meaning | see |
|---|---|---|
| **test double** | any stand-in used instead of the real thing | `doubles` |
| **dummy** | passed only to fill a signature. Never actually used | `doubles` |
| **stub** | always returns the same canned answer | `doubles` |
| **fake** | a real but simplified implementation. A dict instead of a database | `doubles` |
| **spy** | works, and records how it was called | `doubles` |
| **mock** | a spy that also asserts it was called correctly | `doubles` |
| **patching** | replacing something in place, by name | `patch` |
| **injection** | passing the collaborator in, rather than the code fetching it itself | `patch` |
| **seam** | a place you can change behaviour without editing there. An argument is one | `orient` |
| **mock transport** | a fake put in the place where code would talk to the network | `transport` |

## kinds of test

| term | meaning | see |
|---|---|---|
| **unit** | one function or class, nothing real underneath it |  |
| **integration** | several pieces together, often with a real file or database |  |
| **end-to-end** | the whole system as a user meets it. Slow, valuable, few |  |
| **regression test** | written to pin a bug you just fixed, so it cannot come back |  |
| **smoke test** | does it start at all |  |
| **property-based** | assert a rule for all inputs and let a tool hunt counterexamples | `hostile` |
| **fuzzing** | throw generated input at it and check nothing escapes the contract | `hostile` |
| **differential** | run two implementations over one input; whichever disagrees is wrong | `differential` |
| **oracle** | differential testing where the reference is a trusted external tool | `differential` |
| **golden / snapshot** | compare output against a stored known-good file |  |
| **contract test** | pin the shape you publish: names, codes, status codes, schema version | `meta` |
| **meta-test** | a test about the test suite, e.g. does every test still assert | `meta` |

## test quality

| term | meaning | see |
|---|---|---|
| **coverage** | which lines ran. **Not** whether anything checked them | `mutation` |
| **branch coverage** | did both sides of each `if` run | `mutation` |
| **mutation testing** | break the code deliberately and see whether the suite notices | `mutation` |
| **equivalent mutant** | a deliberate break that changes no behaviour, so nothing can catch it | `mutation` |
| **mutation gate** | admit a generated suite only if it kills a threshold of mutants | `ai` |
| **flaky** | passes and fails without the code changing. Always a bug, never noise | `markers` |
| **quarantine** | move a flaky test behind a deselected marker with a ticket | `markers` |
| **test smell** | a sign the test or code is wrong. More patching than assertion is one | `meta` |

## an AI author

| term | meaning | see |
|---|---|---|
| **apparatus** | the machinery that makes reading generated output unnecessary: tests, types, sanitizers, canaries | `ai` |
| **provenance separation** | whatever wrote the code does not grade it, and ideally is not the same family | `ai` |
| **self-preference bias** | an evaluator scoring its own generations higher than a human would | `ai` |
| **intrinsic self-correction** | a model revising its own output with no external signal. Does not reliably work | `ai` |
| **external feedback** | a signal from outside the model. A test run is one, which is the point | `ai` |
| **characterization test** | assertions transcribed from what the code currently does. Pins change, not correctness | `ai` |
| **the oracle problem** | knowing what the right answer is, independently of the thing being tested | `differential` |
| **metamorphic relation** | a property linking two runs when you cannot state the answer for either | `ai` |
| **translation validation** | proving one output matches its input for this run, rather than proving the tool | `ai` |
| **the intent gap** | tests cannot check that they encode what was actually wanted. No technical fix | `ai` |

---

67 terms in 7 groups.
