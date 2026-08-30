"""Content for the beginner card: pytest-basics-card.html.

Separate from card_content.py because the audience is different. The field card
assumes you already write tests and wants to be dense. This one assumes you
have never run pytest, so it defines every term before using it, and it is
sized for larger type on one sheet.

Same shape as card_content.py: slug -> (title, html). build_basics.py lays it
out with the same engine, at a bigger root font size.
"""

CARDS = {

"your-first-test": ("your first test", '''<div class="card hot">
  <div class="lab">your first test</div>
  <pre><span class="c"># test_math.py</span>
def <span class="y">test_two_plus_two</span>():
    assert 2 + 2 == 4</pre>
  <pre><span class="a">$ pytest</span>
1 passed in 0.01s</pre>
  <div class="p">That is a complete test. <b>No class, no <code>self</code>, no
  <code>assertEqual</code>, no imports.</b> A test is a function whose name
  starts with <code>test</code>, and it passes if it does not raise.</div>
  <div class="rule">The word <b>assert</b> is plain Python, not a pytest
  feature. It means "stop here if this is not true".</div>
</div>'''),

"running-it": ("running it", '''<div class="card">
  <div class="lab">running it</div>
  <table>
    <tr><td class="k">pytest</td><td>run everything it can find</td></tr>
    <tr><td class="k">pytest -q</td><td>quieter: one dot per test</td></tr>
        <tr><td class="k">pytest test_math.py</td><td>just one file</td></tr>
    <tr><td class="k">pytest -k adds</td><td>only tests with "adds" in the name</td></tr>
    <tr><td class="k">pytest -x</td><td>stop at the first failure</td></tr>
    <tr><td class="k">pytest --lf</td><td>only what failed last time</td></tr>
    <tr><td class="k">pytest --collect-only</td><td>list what WOULD run, run nothing</td></tr>
  </table>
  <div class="rule"><b>Learn <code>--lf</code> early.</b> Fix one thing, rerun
  only the failures, repeat. It changes how the day feels.</div>
</div>'''),

"what-pytest-looks-for": ("what pytest looks for", '''<div class="card">
  <div class="lab">what pytest looks for</div>
  <table>
    <tr><td class="k">files</td><td><code>test_*.py</code> or <code>*_test.py</code></td></tr>
    <tr><td class="k">functions</td><td>name starts with <code>test</code></td></tr>
    <tr><td class="k">classes</td><td>name starts with <code>Test</code>, and no <code>__init__</code></td></tr>
  </table>
  <div class="p">Finding tests is called <b>collection</b>. If a test is not
  running, the name is nearly always why. <code>pytest --collect-only</code>
  shows exactly what pytest can see.</div>
</div>'''),

"reading-a-failure": ("reading a failure", '''<div class="card hot">
  <div class="lab">reading a failure</div>
  <pre class="no">    def test_greeting():
&gt;       assert greet("sam") == "hi sam"
<span class="r">E       AssertionError: assert 'Hi sam' == 'hi sam'</span>
<span class="r">E         - hi sam</span>
<span class="r">E         + Hi sam</span></pre>
  <div class="p"><code>&gt;</code> marks the failing line, <code>E</code> lines
  are the explanation, and <b>pytest prints the actual values</b>. Here: a
  capital H.</div>
  <div class="rule">You get that diff from a plain <code>assert</code>. pytest
  rewrites your test file as it loads it so it can show both sides. This is why
  there is no assertion library to learn.</div>
</div>'''),

"fixtures": ("fixtures: reusable setup", '''<div class="card hot">
  <div class="lab">fixtures: reusable setup</div>
  <div class="p">A <b>fixture</b> is a named piece of setup. Ask for it by
  putting its name in your test's arguments, and pytest runs it and hands you
  the result.</div>
  <pre>import pytest

<span class="y">@pytest.fixture</span>
def <span class="y">user</span>():
    return {"name": "sam", "admin": False}

def test_not_admin(<span class="y">user</span>):
    assert user["admin"] is False</pre>
  <div class="rule"><b>The argument name is the wiring.</b> Writing
  <code>user</code> in the signature is what finds the fixture called
  <code>user</code>. Nothing else connects them.</div>
</div>'''),

"teardown": ("cleaning up afterwards", '''<div class="card">
  <div class="lab">cleaning up afterwards</div>
  <pre><span class="y">@pytest.fixture</span>
def db():
    conn = connect()
    <span class="a">yield conn</span>      <span class="c"># the test runs here</span>
    conn.close()      <span class="c"># then this runs</span></pre>
  <div class="p">Everything after <code>yield</code> is <b>teardown</b>. It runs
  when the test finishes.</div>
  <div class="rule"><b>Teardown runs even when the test FAILS.</b> That is the
  reason to use a fixture instead of writing setup at the top of the test: a
  crash in the middle still closes the connection.</div>
</div>'''),

"factories": ("factories: making several", '''<div class="card hot">
  <div class="lab">factories: making several</div>
  <div class="p">A plain fixture gives you <b>one</b> thing. Sometimes a test
  needs three, or needs one with particular settings. So the fixture returns a
  <b>function</b> instead of a value. That is a <b>factory fixture</b>.</div>
  <pre><span class="y">@pytest.fixture</span>
def <span class="y">make_user</span>():
    def _make(name, admin=False):
        return {"name": name, "admin": admin}
    <span class="a">return _make</span>          <span class="c"># the FUNCTION, not a user</span>

def test_two_users(<span class="y">make_user</span>):
    boss  = make_user("ada", admin=True)
    other = make_user("sam")
    assert boss["admin"] and not other["admin"]</pre>
  <div class="rule">Reach for a factory the moment you would otherwise write
  <code>admin_user</code>, <code>expired_user</code>,
  <code>user_with_no_email</code> as separate fixtures. Those pile up fast, and
  a reader has to open another file to find out what each one is.
  <br><br>A factory can also keep a list of what it made and clean up after the
  test, using <code>yield</code> the same way the fixture above does.</div>
</div>'''),

"free-fixtures": ("fixtures you get for free", '''<div class="card">
  <div class="lab">fixtures you get for free</div>
  <table>
    <tr><td class="k">tmp_path</td><td>an empty folder, new for every test, cleaned up for you</td></tr>
    <tr><td class="k">capsys</td><td>captures anything printed, so you can assert on it</td></tr>
    <tr><td class="k">monkeypatch</td><td>change something temporarily and have it put back</td></tr>
    <tr><td class="k">caplog</td><td>captures log messages</td></tr>
      </table>
  <pre>def test_writes_a_file(<span class="y">tmp_path</span>):
    out = tmp_path / "report.txt"
    save_report(out)
    assert out.read_text().startswith("REPORT")</pre>
  <div class="rule">Never write to a fixed path like <code>/tmp/out.txt</code>
  in a test. Two tests running at once will fight over it.</div>
</div>'''),

"conftest": ("conftest.py: sharing fixtures", '''<div class="card">
  <div class="lab">conftest.py: sharing fixtures</div>
  <div class="p">Move a fixture into a file called <b>conftest.py</b> and every
  test in that folder can use it, <b>with no import</b>.</div>
  <pre>tests/
  <span class="a">conftest.py</span>      <span class="c"># fixtures live here</span>
  test_users.py     <span class="c"># just ask for them by name</span>
  test_billing.py</pre>
  <div class="p">It is the one file where a name appears from nowhere, so it is
  the first place to look when you meet an argument you do not recognise.</div>
</div>'''),

"parametrize": ("parametrize: same test, many inputs", '''<div class="card hot">
  <div class="lab">parametrize: same test, many inputs</div>
  <pre><span class="y">@pytest.mark.parametrize</span>("number,word", [
    (0, "zero"),
    (1, "one"),
    (2, "many"),
])
def test_naming(number, word):
    assert name(number) == word</pre>
  <pre><span class="a">$ pytest -v</span>
test_naming<span class="y">[0-zero]</span>  PASSED
test_naming<span class="y">[1-one]</span>   PASSED
test_naming<span class="y">[2-many]</span>  <span class="r">FAILED</span></pre>
  <div class="rule">Three <b>separate</b> tests, so one failing does not hide
  the others. A <code>for</code> loop inside a single test stops at the first
  problem and reports one result.</div>
</div>'''),

"glossary": ("glossary", '''<div class="card hot">
  <div class="lab">glossary</div>
  <table>
    <tr><td class="k">assertion</td><td>a line that says what must be true. <code>assert x == y</code></td></tr>
    <tr><td class="k">test</td><td>a function whose name starts with <code>test</code></td></tr>
            <tr><td class="k">fixture</td><td>named setup a test asks for by argument name</td></tr>
    <tr><td class="k">factory</td><td>a fixture returning a function, so a test can make several</td></tr>
    <tr><td class="k">teardown</td><td>cleanup after a test, written after <code>yield</code></td></tr>
        <tr><td class="k">conftest.py</td><td>shared fixtures for a folder, no import needed</td></tr>
    <tr><td class="k">parametrize</td><td>run one test many times with different inputs</td></tr>
    <tr><td class="k">pytest.raises</td><td>assert that something DOES fail: <code>with pytest.raises(ValueError):</code></td></tr>
        <tr><td class="k">skip</td><td>this test does not apply here, do not run it</td></tr>
        <tr><td class="k">flaky</td><td>passes and fails without the code changing. always a bug</td></tr>
        <tr><td class="k">coverage</td><td>which lines ran. NOT whether they were checked</td></tr>
  </table>
</div>'''),

"glossary-doubles": ("glossary: fakes and patching", '''<div class="card hot">
  <div class="lab">glossary: fakes and patching</div>
  <div class="p">Words for "a stand-in used instead of the real thing".
  Collectively they are <b>test doubles</b>.</div>
  <table>
    <tr><td class="k">stub</td><td>always gives the same canned answer</td></tr>
    <tr><td class="k">fake</td><td>a real but simplified version, e.g. a dict instead of a database</td></tr>
        <tr><td class="k">mock</td><td>a spy that also checks it was called correctly</td></tr>
    <tr><td class="k">monkeypatch</td><td>temporarily replace something, put back automatically</td></tr>
    <tr><td class="k">injection</td><td>passing the collaborator in, instead of the code fetching it</td></tr>
  </table>
  <div class="rule"><b>Prefer a fake.</b> A stub that always returns success
  cannot tell you what happens on failure, because it was never pretending to
  be anything.
  <br><br>If a test is painful to write, that is usually the code talking. Code
  that fetches its own database or network connection is hard to stand in for;
  code that is <b>handed</b> one is easy.</div>
</div>'''),

"good-habits": ("habits worth starting with", '''<div class="card">
  <div class="lab">habits worth starting with</div>
  <ul>
    <li><b>Name the behaviour, not the function.</b>
    <code>test_rejects_empty_name</code> beats <code>test_create_user_2</code>.</li>
    <li><b>One idea per test.</b> Four unrelated asserts report the first
    failure and hide the rest.</li>
    <li><b>Write the failing test first</b> when fixing a bug. If it does not
    fail before your fix, it is not testing the fix.</li>
    <li><b>Check the unhappy path.</b> Empty input, missing file, wrong type.
    That is where the bugs are.</li>
  </ul>
</div>'''),

"when-stuck": ("when something looks wrong", '''<div class="card">
  <div class="lab">when something looks wrong</div>
  <table>
    <tr><td class="k">test not running</td><td>check the name, then <code>--collect-only</code></td></tr>
    <tr><td class="k">fixture not found</td><td>spelling, or it is not in <code>conftest.py</code></td></tr>
    <tr><td class="k">passes alone, fails together</td><td>something is shared between tests</td></tr>
    <tr><td class="k">passes here, fails on CI</td><td>a path, a clock, or an installed package</td></tr>
    <tr><td class="k">no output shown</td><td>pytest hides prints on pass. use <code>-s</code></td></tr>
      </table>
  <div class="rule">Stuck on a failure? <code>pytest --lf -x --tb=short</code>
  gets you the shortest useful loop: last failure only, stop at it, short
  traceback.</div>
</div>'''),

}
