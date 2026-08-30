"""Cards for the printed reference, pytest-field-card.html.

slug -> (title, html). build_card.py measures each block against the print
stylesheet and solves the column layout, so nothing here needs to know about
pages.

Two callout classes, and the distinction is the whole editorial rule:

    <div class="rule">   operational. It changes what you type. Stays on the card.
    <div class="why">    argument. It explains the reasoning. Stripped from the
                         card at render and made properly in the deep dive.

tests/test_cards.py checks that every .why has a home in frag.html before it is
dropped from here, so cutting one from the card cannot silently lose it.
"""

CARDS = {

"what-gets-collected": ("what gets collected", '''<div class="card">
  <div class="lab">what gets collected</div>
  <table>
    <tr><td class="k">files</td><td><code>test_*.py</code> &nbsp;or&nbsp; <code>*_test.py</code></td></tr>
    <tr><td class="k">classes</td><td><code>Test*</code>, and no <code>__init__</code></td></tr>
    <tr><td class="k">functions</td><td><code>test*</code> &nbsp;<b>not</b>&nbsp; <code>test_*</code></td></tr>
  </table>
  <pre class="no"><span class="c"># a helper named tests_in() IS COLLECTED as a test.</span>
<span class="c"># if it is a generator, the whole FILE dies:</span>
<span class="r">'yield' keyword is allowed in fixtures,
 but not in tests</span>
<span class="c"># a collection error takes every other test in</span>
<span class="c"># that file with it. name helpers find_tests().</span></pre>
</div>'''),

"conftest-py": ("conftest.py", '''<div class="card">
  <div class="lab">conftest.py</div>
  <div class="p">Not a junk drawer. A <b>plugin loaded by directory</b>, with three jobs: isolate the process, supply specimens, extend pytest.</div>
  <pre><span class="c">visibility follows the DIRECTORY tree.</span>
<span class="c">nearest wins. no import needed anywhere.</span>
repo/conftest.py       <span class="c">everything below</span>
  tests/conftest.py    <span class="c">tests/ and below</span>
    tests/test_x.py    <span class="a">a fixture here SHADOWS both</span>
                       <span class="c">and nothing announces it</span></pre>
  <pre><span class="c"># where a marker becomes behaviour</span>
def pytest_addoption(parser):
    parser.addoption("--runnet", action="store_true")

def pytest_collection_modifyitems(config, items):
    if config.getoption("--runnet"): return
    skip = pytest.mark.skip(reason="needs network")
    for item in items:
        if "net" in item.keywords:
            item.add_marker(skip)</pre>
</div>'''),

"pyproject-toml-steal-this": ("pyproject.toml &middot; steal this", '''<div class="card hot">
  <div class="lab">pyproject.toml &middot; steal this</div>
  <pre>[tool.pytest.ini_options]
testpaths    = ["tests"]
pythonpath   = ["src"]     <span class="c"># run without installing</span>
addopts      = "-rs --strict-markers"
xfail_strict = true
markers = [
  "slow: takes real wall-clock time",
  "net: touches a real network",
]
filterwarnings = [
  <span class="c"># YOUR deprecations are errors. SCOPE it, or</span>
  <span class="c"># someone else's release breaks your build.</span>
  "error::DeprecationWarning:yourpkg.*",
]</pre>
  <table>
    <tr><td class="k">-rs</td><td>print every skip REASON</td></tr>
    <tr><td class="k">--strict-markers</td><td>a typo'd marker is an error</td></tr>
    <tr><td class="k">xfail_strict</td><td>an xfail that passes = failure</td></tr>
    <tr><td class="k">pythonpath</td><td>a fresh clone runs immediately</td></tr>
  </table>
</div>'''),

"flags-muscle-memory": ("flags &middot; muscle memory", '''<div class="card hot">
  <div class="lab">flags &middot; muscle memory</div>
  <table>
    <tr><td class="k">--lf &nbsp;/&nbsp; --ff</td><td>last-failed / failed-first &nbsp;<b>the debug loop</b></td></tr>
    <tr><td class="k">-x</td><td>stop at the first failure</td></tr>
    <tr><td class="k">-k 'a and not b'</td><td>select by name expression</td></tr>
    <tr><td class="k">-m 'not net'</td><td>select by marker</td></tr>
    <tr><td class="k">--collect-only</td><td>what WOULD run. first thing to try</td></tr>
    <tr><td class="k">--setup-show</td><td>every fixture setup/teardown</td></tr>
    <tr><td class="k">--tb=short|line|no</td><td>traceback size</td></tr>
    <tr><td class="k">-l</td><td>locals in tracebacks</td></tr>
    <tr><td class="k">--pdb</td><td>debugger at the failure</td></tr>
    <tr><td class="k">--durations=10</td><td>slowest ten. run monthly</td></tr>
    <tr><td class="k">-W error</td><td>every warning becomes an error</td></tr>
    <tr><td class="k">-p no:NAME</td><td>disable a plugin for one run</td></tr>
    <tr><td class="k">-n 4</td><td>xdist. also an order-dependence detector</td></tr>
    <tr><td class="k">--co -q</td><td>the flat list of every test id</td></tr>
  </table>
</div>'''),

"fixtures-scope-and-teardown": ("fixtures &middot; scope &amp; teardown", '''<div class="card hot">
  <div class="lab">fixtures &middot; scope &amp; teardown</div>
  <pre><span class="c">build order = DEPENDENCY order.</span>
<span class="c">teardown = its exact reverse.</span>

 outer:setup <span class="a">→</span> inner:setup <span class="a">→</span> <span class="y">TEST</span>
             <span class="a">→</span> inner:teardown <span class="a">→</span> outer:teardown

<span class="c">code after `yield` runs even if the test FAILS.</span>
<span class="c">it does NOT run if setup before the yield raised.</span>
<span class="a">→ put what CAN fail after what MUST be cleaned up.</span></pre>
  <table>
    <tr><th>scope</th><th>built</th></tr>
    <tr><td class="k">function</td><td>per test &nbsp;<b>default, almost always right</b></td></tr>
    <tr><td class="k">class</td><td>per test class</td></tr>
    <tr><td class="k">module</td><td>per file. only if IMMUTABLE</td></tr>
    <tr><td class="k">package</td><td>per directory</td></tr>
    <tr><td class="k">session</td><td>per run. <b>never mutable</b></td></tr>
  </table>
  <div class="rule">Never make a session-scoped fixture <b>mutable</b>. The test that corrupts it fails a <i>different</i> test, in one ordering only.</div>
</div>'''),

"fixture-shapes": ("fixture shapes", '''<div class="card">
  <div class="lab">fixture shapes</div>
  <pre><span class="c">FACTORY: the test gets the FUNCTION</span>
@pytest.fixture
def make_uf2(): return build_uf2
<span class="c">  beats forty fixtures named after defects</span>

<span class="c">PARAMETRIZED: requester runs once per case</span>
@pytest.fixture(params=["uf2","elf"], ids=[...])
def any_artifact(request): ...

<span class="c">NAMED: function name is not the fixture name</span>
@pytest.fixture(name="digest")
def _make_digest(uf2): ...

<span class="c">CONDITIONAL CLEANUP: addfinalizer still wins</span>
@pytest.fixture
def thing(request, tmp_path):
    t = tmp_path / "a"; t.write_bytes(b"")
    request.addfinalizer(t.unlink)  <span class="c"># only NOW</span>
    return t
<span class="c">  with yield, teardown runs even when setup</span>
<span class="c">  half-failed, and must defend itself.</span></pre>
  <div class="why" data-see="fixtures"><b>Assertions belong in tests. Fixtures build things.</b> An assert in a fixture reports an ERROR against every test using it, pointing at conftest.</div>
</div>'''),

"parametrize-and-ids": ("parametrize &amp; ids", '''<div class="card hot">
  <div class="lab">parametrize &amp; ids</div>
  <pre>@pytest.mark.parametrize("fam,want",
    [(RP2040,"RP2040"), (NRF,"NRF52840")],
    ids=["rp2040","nrf52840"])        <span class="c"># explicit</span>
    ids=lambda n: "block%d" % n       <span class="c"># callable</span>
    ids=repr                          <span class="c"># byte specimens</span>

<span class="c">STACKED = cartesian product. 2x2 = 4 tests,</span>
<span class="c">ids compose: [le-elf64]. multiplies FAST:</span>
<span class="c">a 4th axis of 5 is 40 tests, a 5th is 200.</span>

<span class="c">pytest.param = per-case id AND marks</span>
pytest.param(x, id="unknown",
  marks=pytest.mark.xfail(strict=True, reason="..."))

<span class="c">indirect: the param goes to a FIXTURE first,</span>
<span class="c">so each case gets setup AND teardown</span>
@parametrize("vault",[0,1,5], indirect=True)

<span class="c">pytest_generate_tests(metafunc): build the</span>
<span class="c">case list at collection, from the real source</span>
<span class="c">of truth instead of a copy of it.</span></pre>
  <div class="why" data-see="param"><code>test_family[3-2]</code> tells you nothing. <code>test_family[nrf52840]</code> tells you everything. You read these in CI, in a bisect, and in a message from someone without the repo open.</div>
</div>'''),

"property-based": ("property-based", '''<div class="card">
  <div class="lab">property-based</div>
  <table>
    <tr><th>property</th><th>strength</th></tr>
    <tr><td class="k">round-trip</td><td><code>parse(build(x))==x</code>. strongest</td></tr>
    <tr><td class="k">invariant</td><td>holds for all inputs</td></tr>
    <tr><td class="k">oracle</td><td>fast impl == obvious impl</td></tr>
    <tr><td class="k">idempotence</td><td><code>f(f(x))==f(x)</code></td></tr>
    <tr><td class="k">never-crash</td><td><b>weakest.</b> where everyone starts</td></tr>
  </table>
  <pre>@given(n=st.integers(1,12), p=st.integers(0,476))
@settings(deadline=None, max_examples=100)
def test_round_trip(n, p): ...

assume(bit64 or entry &lt; 2**32)
<span class="c">  state preconditions with assume, not by</span>
<span class="c">  narrowing the strategy: hypothesis tracks</span>
<span class="c">  rejections and complains if the filter is</span>
<span class="c">  too aggressive. a narrowed strategy just</span>
<span class="c">  searches less, silently.</span></pre>
  <div class="p"><b>Shrinking is the feature.</b> A fuzzer hands you 1,847 bytes and a traceback. Hypothesis hands you <code>b'\\x00'</code> and the same traceback.</div>
</div>'''),

"assertions": ("assertions", '''<div class="card hot">
  <div class="lab">assertions</div>
  <pre>with pytest.raises(ParseError, match=r"bad magic"):
    parse(blob)
<span class="c">  match is re.SEARCH, not fullmatch.</span>
<span class="r">  ESCAPE YOUR METACHARACTERS.</span> "offset (0x1fc)"
<span class="c">  is a group. a match that matches NOTHING still</span>
<span class="c">  passes if the exception type is right.</span>

with pytest.raises(TruncatedError) as ei: ...
assert ei.value.needed == 32     <span class="c"># the OBJECT,</span>
                                 <span class="c"># not just the class</span>
assert 0.1+0.2 == pytest.approx(0.3)
with pytest.warns(DeprecationWarning, match="..."): ...</pre>
  <pre class="no"><span class="c">tells you nothing:</span>
assert result                    <span class="r">E  assert None</span>
assert len(hits) &gt; 0             <span class="r">E  assert 0 &gt; 0</span></pre>
  <pre class="ok"><span class="c">tells you what broke:</span>
assert codes(...) == ["OVERSIZE"]
<span class="y">E  assert ['UNSIGNED'] == ['OVERSIZE']</span>
assert not bad, "undocumented: " + ", ".join(bad)
<span class="y">E  AssertionError: undocumented: ingest vault</span></pre>
</div>'''),

"capturing-output": ("capturing output", '''<div class="card">
  <div class="lab">capturing output</div>
  <table>
    <tr><td class="k">capsys</td><td>stdout/stderr at the <b>Python</b> level</td></tr>
    <tr><td class="k">capfd</td><td>at the <b>fd</b> level. C ext, subprocess</td></tr>
    <tr><td class="k">caplog</td><td>log records</td></tr>
    <tr><td class="k">tmp_path</td><td>fresh dir per test, last 3 runs kept</td></tr>
    <tr><td class="k">tmp_path_factory</td><td>the session-scoped variant</td></tr>
  </table>
  <div class="p">Output missing from <code>capsys</code>? That <b>is</b> your answer. Use <code>capfd</code>.</div>
  <pre>caplog.set_level(logging.WARNING, logger="pkg.mod")
<span class="c">1. SET THE LEVEL. default capture is WARNING, so</span>
<span class="c">   an info() you assert on never arrives and it</span>
<span class="c">   looks like the code is wrong.</span>

assert [r.getMessage() for r in caplog.records] == [...]
<span class="c">2. ASSERT ON RECORDS, NOT caplog.text. records</span>
<span class="c">   carry .levelname .name .getMessage(). text is</span>
<span class="c">   whatever the formatter felt like, and nobody</span>
<span class="c">   thinks of a format string as an interface.</span>

<span class="c">3. AND THE NEGATIVE CASE:</span>
def test_happy_path_logs_nothing(caplog):
    assert caplog.records == []</pre>
  <div class="rule">In the package: <code>log = logging.getLogger(__name__)</code>. Never <code>logging.warning(...)</code>: it configures the root handler as a side effect and steals formatting from whatever imported you.</div>
</div>'''),

"skip-xfail-the-trap": ("skip &middot; xfail &middot; the trap", '''<div class="card hot">
  <div class="lab">skip &middot; xfail &middot; the trap</div>
  <table>
    <tr><td class="k">skip</td><td>does not apply here</td></tr>
    <tr><td class="k">skipif(cond)</td><td>same, decided at collection</td></tr>
    <tr><td class="k">xfail</td><td>this is broken and we know</td></tr>
    <tr><td class="k">xfail(strict=True)</td><td><b>and tell me when it stops</b></td></tr>
    <tr><td class="k">xfail(raises=E)</td><td>fails FOR THIS REASON</td></tr>
  </table>
  <pre class="no"><span class="flag f-no">trap</span>
<span class="r">@pytest.mark.xfail(reason="bug FW-118")</span>
def test_the_bug():
    assert True        <span class="c"># someone fixed it</span>
<span class="c"># → XPASS. exit 0. GREEN.</span>
<span class="c"># marker sits there two years. the test has</span>
<span class="c"># asserted nothing that whole time.</span></pre>
  <pre class="ok"><span class="y">@pytest.mark.xfail(strict=True, reason="FW-118")</span>
<span class="c"># → FAILED: "delete this marker."</span></pre>
  <div class="rule">Without <code>raises=</code>, an xfail absorbs <b>every</b> failure, including the ImportError you added this morning.</div>
</div>'''),

"the-flaky-test": ("the flaky test", '''<div class="card">
  <div class="lab">the flaky test</div>
  <div class="p">A flaky test is a <b>bug report</b>, against the test or the code. Never noise. Something is genuinely non-deterministic and you found it.</div>
  <table>
    <tr><th>cause</th><th>fix</th></tr>
    <tr><td class="k">unseeded random</td><td>fix the seed</td></tr>
    <tr><td class="k">real clock / sleep</td><td>inject a clock</td></tr>
    <tr><td class="k">shared state</td><td>narrow the scope</td></tr>
    <tr><td class="k">fixed path + <code>-n</code></td><td>tmp_path</td></tr>
    <tr><td class="k">real network</td><td>a marker + a fake</td></tr>
    <tr><td class="k">dict / set order</td><td>sort, or compare sets</td></tr>
    <tr><td class="k">test order</td><td>run <code>-p no:randomly</code> vs seeded</td></tr>
  </table>
  <div class="rule"><b>Quarantine, do not rerun.</b> Move it behind a deselected marker with a ticket. <code>--reruns 3</code> on your own code turns a real bug into a slower green run, permanently.</div>
</div>'''),

"plugins-verdicts": ("plugins &middot; verdicts", '''<div class="card">
  <div class="lab">plugins &middot; verdicts</div>
  <table>
    <tr><td class="k">pytest-cov</td><td><span class="flag f-ok">yes</span> read it as a map, never a score</td></tr>
    <tr><td class="k">pytest-xdist</td><td><span class="flag f-ok">yes</span> cheapest order-dependence detector you own</td></tr>
    <tr><td class="k">hypothesis</td><td><span class="flag f-ok">yes</span> parsers, and anything with an inverse</td></tr>
    <tr><td class="k">anyio / asyncio</td><td><span class="flag f-wa">one</span> if you have async. not both</td></tr>
    <tr><td class="k">pytest-randomly</td><td><span class="flag f-wa">ok</span> occasionally infuriating. that is the point</td></tr>
    <tr><td class="k">freezegun</td><td><span class="flag f-wa">last</span> only where you cannot inject a clock</td></tr>
    <tr><td class="k">respx / responses</td><td><span class="flag f-wa">last</span> only if you cannot pass a transport</td></tr>
    <tr><td class="k">pytest-mock</td><td><span class="flag f-no">no</span> thin wrapper. <code>monkeypatch</code> is already there</td></tr>
    <tr><td class="k">rerunfailures</td><td><span class="flag f-no">no</span> external deps only. never your own code</td></tr>
  </table>
</div>'''),

"what-do-i-reach-for": ("what do I reach for?", '''<div class="card hot">
  <div class="lab">what do I reach for?</div>
  <pre class="tree"><span class="q">I need to replace a collaborator.</span>
 <span class="a">├</span> do I OWN the seam?
 <span class="a">│</span>  <span class="y">YES</span> <span class="a">→</span> pass a different object. <span class="y">INJECT.</span>
 <span class="a">│</span>  <span class="r">NO</span>  <span class="a">→</span> monkeypatch it.        <span class="a">B4</span>
 <span class="a">└</span> what KIND of replacement?
    needs canned answers only   <span class="a">→</span> stub
    needs to model >1 outcome   <span class="a">→</span> <span class="y">FAKE</span>
    needs to record its calls   <span class="a">→</span> spy
    needs a SEQUENCE of answers <span class="a">→</span> script
    needs to assert on itself   <span class="a">→</span> <span class="r">rethink</span>

<span class="q">I have a lot of similar cases.</span>
 <span class="a">├</span> I can name each one          <span class="a">→</span> parametrize
 <span class="a">├</span> each needs setup/teardown    <span class="a">→</span> indirect
 <span class="a">├</span> the list comes from the code <span class="a">→</span> generate_tests
 <span class="a">└</span> hundreds, unnameable         <span class="a">→</span> hypothesis

<span class="q">I cannot write down the expected output.</span>
 <span class="a">├</span> a second dumb impl exists    <span class="a">→</span> differential
 <span class="a">├</span> a trusted tool exists        <span class="a">→</span> oracle
 <span class="a">└</span> only a RELATIONSHIP holds    <span class="a">→</span> property

<span class="q">I want to know if my tests are any good.</span>
 <span class="a">└</span> break the code on purpose    <span class="a">→</span> mutation <span class="a">B11</span></pre>
</div>'''),

"seams-the-whole-game": ("seams &middot; the whole game", '''<div class="card hot">
  <div class="lab">seams &middot; the whole game</div>
  <div class="p">Feathers: <b>a place where you can alter behavior without editing in that place.</b> The <i>enabling point</i> is where you choose.</div>
  <pre>def __init__(self, url, transport=None, clock=None):
    self.transport = transport or UrllibTransport()
<span class="c">                     ▲ the enabling point</span>

<span class="c"># the class never says urllib, socket or host.</span>
<span class="c"># the test passes a different object.</span>
<span class="c"># nothing is patched.</span></pre>
  <pre><span class="y">INJECT what you DO own</span>
       your transport, clock, store, policy,
       streams, argv, the vault root
<span class="w">PATCH  what you do NOT own</span>
       urllib, datetime, os.replace, a vendor lib
<span class="c">SPLIT  when there is nothing to pass:</span>
       a generator that WALKS + a function that
       FOLDS is a seam too, and often a better one</pre>
  <div class="why" data-see="patch">Patching a seam you own <b>passes even after the code stops using that seam</b>. Injecting notices at once: the fake stops being asked anything. <b>If a test has more patching than assertion, the code has no seam.</b></div>
</div>'''),

"the-five-doubles": ("the five doubles", '''<div class="card hot">
  <div class="lab">the five doubles</div>
  <pre>DUMMY  fills a signature, never used
STUB   canned answers, no state
<span class="y">FAKE   a real, working, SIMPLIFIED impl  ← this one</span>
SPY    a stub that records its calls
<span class="r">MOCK   a spy that asserts on ITSELF      ← almost never</span></pre>
  <ul>
    <li><b>Fake</b> is the only kind that can be <i>wrong</i> in a way a test notices. A stub returning 200 forever cannot fail to model a 404. It was never modelling anything.</li>
    <li><b>Spy</b> for the negative assertion. "the cache was used" is invisible in a return value and obvious in a call log.</li>
    <li><b>Mock</b> fails <i>inside</i> the double, so the message describes a call that did not happen, not a behaviour that is wrong.</li>
    <li>A double that runs off the end of its script must <b>fail loudly</b>. One that keeps answering makes "retried 3 times" and "retried 300 times" the same passing test.</li>
  </ul>
  <pre class="no">loose = Mock()          <span class="c"># no spec=</span>
loose.method_that_does_not_exist()   <span class="c"># passes.</span>
<span class="r">spec= is not optional.</span></pre>
  <div class="why" data-see="doubles"><b>Ship your doubles</b> in the package, beside the thing they fake, the way httpx ships MockTransport. Otherwise every user writes their own and each gets a detail wrong.</div>
</div>'''),

"monkeypatch-all-of-it": ("monkeypatch &middot; all of it", '''<div class="card hot">
  <div class="lab">monkeypatch &middot; all of it</div>
  <table>
    <tr><td class="k">setattr(o,n,v)</td><td>raises if n is absent. <b>the guardrail</b></td></tr>
    <tr><td class="k">delattr(o,n)</td><td></td></tr>
    <tr><td class="k">setitem(d,k,v)</td><td>sys.modules, os.environ, any table</td></tr>
    <tr><td class="k">delitem(d,k)</td><td><code>raising=False</code> for cleanup</td></tr>
    <tr><td class="k">setenv / delenv</td><td>strings only. be explicit</td></tr>
    <tr><td class="k">syspath_prepend</td><td>+ invalidates importlib caches</td></tr>
    <tr><td class="k">chdir(p)</td><td>and puts it back</td></tr>
    <tr><td class="k">context()</td><td>undo EARLY, mid-test</td></tr>
  </table>
  <pre><span class="c">patch where the name is LOOKED UP:</span>
<span class="y">from . import families;  families.FAMILIES[x]</span>
<span class="c">  read at CALL time  → patchable</span>
<span class="r">from .families import FAMILIES;  FAMILIES[x]</span>
<span class="c">  bound at IMPORT time into a SECOND namespace</span>
<span class="c">  → patching does NOTHING, and the test PASSES</span></pre>
  <pre><span class="c">monkeypatch is FUNCTION-scoped. a session</span>
<span class="c">fixture requesting it gets ScopeMismatch:</span>
@pytest.fixture(scope="session")
def env():
    with pytest.MonkeyPatch.context() as m:
        m.setenv("HOME", "/x"); yield m</pre>
</div>'''),

"four-patching-traps": ("four patching traps", '''<div class="card">
  <div class="lab">four patching traps</div>
  <pre class="no"><span class="r">1</span> raising=False disables your only signal
  <span class="c">a patch aimed at a typo'd name is a patch</span>
  <span class="c">aimed at nothing, and it passes.</span>

<span class="r">2</span> patching a constant does not move an
  already-bound default
  <span class="c">@dataclass  x: int = CONST  ← evaluated ONCE</span>
  <span class="c">at class creation. same for def f(x=CONST)</span>
  <span class="c">and for `from mod import CONST`. to be</span>
  <span class="c">patchable it must be READ at call time.</span>

<span class="r">3</span> the string form walks getattr
  <span class="c">"pkg.mod.CONST" imports pkg, then getattrs</span>
  <span class="c">along. if pkg re-exported a FUNCTION over</span>
  <span class="c">its own submodule name, the walk dies there.</span>
  <span class="c">`import pkg.mod as m` does NOT save you.</span>
  <span class="c">importlib.import_module() reads sys.modules.</span>

<span class="r">4</span> sys.modules[n] = None makes `import n` raise
  <span class="c">delitem FIRST. if already imported, the None</span>
  <span class="c">assignment is what takes effect, and you get</span>
  <span class="c">a pass for the wrong reason.</span></pre>
</div>'''),

"asgi-and-fake-clients": ("ASGI &amp; fake clients", '''<div class="card">
  <div class="lab">ASGI &amp; fake clients</div>
  <pre>async def app(scope, receive, send)
<span class="c">  scope    dict describing the connection</span>
<span class="c">  receive  await it to pull events IN</span>
<span class="c">  send     await it to push events OUT</span>

<span class="c">that is the entire protocol. every test client</span>
<span class="c">you have used builds a scope, feeds a receive</span>
<span class="c">and collects the sends. about 20 lines.</span></pre>
  <table>
    <tr><td class="k">raw harness</td><td>chunk boundaries, disconnects, malformed scopes, visible lifespan</td></tr>
    <tr><td class="k">ASGITransport</td><td>substitutes the <b>server</b></td></tr>
    <tr><td class="k">MockTransport</td><td>substitutes what you <b>call</b></td></tr>
    <tr><td class="k">TestClient</td><td>wraps ANY asgi app, lifespan via <code>with</code></td></tr>
  </table>
  <div class="rule">Answer <code>lifespan</code>, or a test client hangs at fixture time and it looks like the framework is broken.</div><div class="why" data-see="asgi">If swapping the client changes what you <b>assert</b>, you were testing the client.</div>
</div>'''),

"hostile-input": ("hostile input", '''<div class="card hot">
  <div class="lab">hostile input</div>
  <pre><span class="c">the contract: for ANY bytes, either a result or</span>
<span class="c">YOUR declared error. never IndexError,</span>
<span class="c">struct.error, MemoryError, or a hang.</span>

<span class="y">TRUNCATION SWEEP</span>  every prefix of a valid file
  <span class="c">cheapest, finds the most. an interrupted</span>
  <span class="c">upload is the commonest corrupt file alive.</span>
<span class="y">BIT FLIPS</span>         one byte, at FIELD boundaries
  <span class="c">12 named offsets beat a million random ones</span>
<span class="y">SEEDED FUZZ</span>       a FIXED seed, always
  <span class="c">unseeded = a flake nobody can reproduce, and</span>
  <span class="c">everyone learns to just re-run CI.</span>
<span class="y">VALID PREFIX + tail</span>  gets PAST the magic check
  <span class="c">pure random spends 99.9% of its budget on</span>
  <span class="c">the same early branch.</span>

<span class="c">and check the SWEEP straddles both outcomes: a</span>
<span class="c">step that never lands on a block boundary runs</span>
<span class="c">twenty cases down one branch.</span></pre>
  <div class="rule"><b>Every never-crash test needs a positive companion.</b> All of the above passes against <code>def parse(b): raise ParseError("no")</code>. Put the companion in the same file.</div>
</div>'''),

"differential-oracle": ("differential / oracle", '''<div class="card">
  <div class="lab">differential / oracle</div>
  <div class="p">Two implementations over one corpus. The naive one is obviously correct and too slow; the real one is fast and subtle. <b>No expected values to write, ever.</b></div>
  <ul>
    <li>The reference must be <b>independent</b>. Shared helpers mean a shared bug cancels out and both agree.</li>
    <li>Compare <b>outcomes</b>, not just outputs. Agreeing on the result is not enough if one raises and the other does not.</li>
    <li>The corpus needs its own guard: if every specimen raises, both agree everything is broken and the test is vacuous.</li>
    <li>One test per specimen, <b>named by specimen</b>. Adding a corpus entry then adds a test with no assertion to write. That is the economics.</li>
    <li><b>Oracle</b> variant: the reference is an external tool. <code>readelf</code>, <code>ffmpeg</code>, the vendor's own parser.</li>
  </ul>
</div>'''),

"testing-a-cli": ("testing a CLI", '''<div class="card">
  <div class="lab">testing a CLI</div>
  <pre>def main(argv=None, stdout=None, stderr=None) -&gt; int
<span class="c">  takes argv. returns an int. writes to streams</span>
<span class="c">  it was HANDED. costs nothing, and it is the</span>
<span class="c">  highest-leverage decision in a CLI's design.</span>

<span class="y">IN-PROCESS</span>  microseconds, every branch. the
            coverage lives here.
<span class="w">SUBPROCESS</span>  four cases only, but they are the
            ones in-process CANNOT see:
  <span class="c">· imports from a CLEAN interpreter</span>
  <span class="c">· the exit code as the SHELL sees it</span>
  <span class="c">· buffering, encoding, line endings</span>
  <span class="c">· a stray print() corrupting your JSON</span></pre>
  <pre class="no"><span class="r">python -I implies -E</span> <span class="c">→ PYTHONPATH ignored.</span>
<span class="c">a cold-start import test that passes the path</span>
<span class="c">via the environment gets an empty sys.path and</span>
<span class="c">fails looking exactly like a packaging bug.</span>
<span class="c">put the path in the -c program instead.</span></pre>
  <div class="rule">Exit codes are a contract. "your input is bad" and "our infrastructure is down" must be <b>different numbers</b>, or a red build teaches nobody anything and pages the wrong team.</div>
</div>'''),

"meta-tests": ("meta-tests", '''<div class="card hot">
  <div class="lab">meta-tests</div>
  <div class="p">A suite rots <b>silently, and in the direction of passing</b>. These read the test tree as data.</div>
  <ul>
    <li>every test asserts something</li>
    <li>every skip explains itself</li>
    <li>no fixed paths, no path outside the repo</li>
    <li>nothing silently disabled: a bare <code>return</code> at the top of a test leaves no skip line at all</li>
    <li>no duplicate test names across files</li>
    <li>no <b>mutated</b> module-level state</li>
    <li><code>__all__</code>, error codes, exit codes, schema version, route table: all pinned</li>
    <li>the dependency boundary, twice: AST-walk for module-level optional imports, <i>and</i> <code>sys.modules[x]=None</code> then run it</li>
  </ul>
  <div class="rule"><b>(1)</b> every check names the file and line it objects to. <b>(2)</b> every check is shown FIRING at least once, or a broken pattern passes everything forever.</div>
  <pre><span class="c">scanning source? skip COMMENTS + DOCSTRINGS,</span>
<span class="c">keep string LITERALS. strip every string and the</span>
<span class="c">scanner cannot see the "/tmp/" it hunts; strip</span>
<span class="c">nothing and it flags the paragraph explaining</span>
<span class="c">the rule. both versions ship green.</span></pre>
</div>'''),

"coverage-mutation-ci": ("coverage &middot; mutation &middot; CI", '''<div class="card hot">
  <div class="lab">coverage &middot; mutation &middot; CI</div>
  <pre>line coverage    did this line execute
branch coverage  did BOTH sides of the `if`
                 <span class="c">--cov-branch. line coverage</span>
                 <span class="c">calls a half-tested `if` covered.</span>
<span class="y">mutation score   if I BREAK it, does anything go red</span>

<span class="c">only the third is a question about your TESTS.</span>
<span class="r">100% line coverage is compatible with ZERO</span>
<span class="r">assertions.</span></pre>
  <ul>
    <li>Tools: <code>mutmut</code>, <code>cosmic-ray</code>. Minutes to hours. Occasionally, <b>never in CI</b>.</li>
    <li><b>Equivalent mutants</b> are why the score is never 100%: an edit that changes no behaviour and so cannot be detected. Separating those from real holes is the manual cost.</li>
    <li>Cheap version that <i>does</i> belong in the suite: a few hand-written mutants, each paired with the assertion that kills it.</li>
    <li>A mutant is killed if the suite goes red, and an ERROR counts. Note <code>pytest.fail.Exception</code> derives from <code>BaseException</code>, so <code>except Exception</code> misses it.</li>
  </ul>
  <pre>jobs:
  <span class="y">bare</span>: pip install pytest   <span class="c"># and NOTHING else</span>
        <span class="c"># the only environment that can DISPROVE</span>
        <span class="c"># a no-dependencies claim.</span>
  full: matrix [ubuntu, windows] x [3.11, 3.13]
        fail-fast: <span class="w">false</span>  <span class="c"># one red cell must not</span>
                          <span class="c"># hide the others</span></pre>
  <div class="rule">No <code>--cov-fail-under</code>. A coverage threshold is a number people game, and the cheapest way to game it is a test with no assertions.</div>
</div>'''),

"smells-and-the-build-order": ("smells &amp; the build order", '''<div class="card hot">
  <div class="lab">smells &amp; the build order</div>
  <table>
    <tr><th>smell</th><th>what it means</th></tr>
    <tr><td class="k">more patch than assert</td><td>the code has no seam</td></tr>
    n    <tr><td class="k">"just re-run it"</td><td>a real bug, unquarantined</td></tr>
    <tr><td class="k">assert in a fixture</td><td>failure blames the wrong file</td></tr>
    <tr><td class="k"><code>if param ==</code> in a test</td><td>two tests in a trenchcoat</td></tr>
    n    n    <tr><td class="k">green after deleting a check</td><td>the check was never tested</td></tr>
  </table>
  <pre><span class="y">1</span> give the code SEAMS   <span class="c">every collaborator a param</span>
<span class="y">2</span> specimen BUILDERS    <span class="c">not a committed corpus</span>
<span class="y">3</span> example tests, good ids
<span class="y">4</span> a FAKE per seam      <span class="c">ship it in the package</span>
<span class="y">5</span> the NEGATIVE cases   <span class="c">the clean specimen that</span>
                       <span class="c">must NOT warn</span>
<span class="y">6</span> hostile input        <span class="c">truncation first, cheapest</span>
<span class="y">7</span> contract tests       <span class="c">before your first release</span>
<span class="y">8</span> hygiene tests        <span class="c">before 100 test files</span>

<span class="r">patching comes LAST, and only for what you do</span>
<span class="r">not own.</span></pre>
  <div class="why" data-see="running">Inject what you own, patch what you do not. Prefer a fake to a mock. Every never-crash test needs a positive companion. And <b>a check nobody has seen fire is a check nobody should trust.</b></div>
</div>'''),

}
