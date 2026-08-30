"""Glossary cards for the printed reference. GENERATED, do not edit.

Written by gen_glossary.py from terms.py. Edit those.
"""

CARDS = {

"glossary-the-basics": ("glossary: the basics", '''<div class="card hot">
  <div class="lab">glossary: the basics</div>
  <table>
    <tr><td class="k">test</td><td>a function whose name starts with <code>test</code>. It passes if it does not raise</td></tr>
    <tr><td class="k">assertion</td><td>a line stating what must be true. <code>assert x == y</code></td></tr>
    <tr><td class="k">test suite</td><td>all your tests together</td></tr>
    <tr><td class="k">test runner</td><td>the tool that finds and runs them. pytest is one</td></tr>
    <tr><td class="k">collection</td><td>pytest finding your tests, before running any</td></tr>
    <tr><td class="k">fail vs error</td><td><i>fail</i> = an assertion was false. <i>error</i> = it blew up before reaching one</td></tr>
    <tr><td class="k">AAA</td><td>arrange, act, assert. The three parts of most tests, in that order</td></tr>
    <tr><td class="k">TDD</td><td>write the failing test first, then the code that makes it pass</td></tr>
  </table>
</div>'''),

"glossary-fixtures": ("glossary: fixtures", '''<div class="card hot">
  <div class="lab">glossary: fixtures</div>
  <table>
    <tr><td class="k">fixture</td><td>named setup a test asks for by putting its name in the arguments</td></tr>
    <tr><td class="k">factory fixture</td><td>a fixture returning a <b>function</b>, so a test can make several things</td></tr>
    <tr><td class="k">setup / teardown</td><td>before and after. In pytest, teardown is whatever follows <code>yield</code></td></tr>
    <tr><td class="k">scope</td><td>how often a fixture is rebuilt: function, class, module, package, session</td></tr>
    <tr><td class="k">autouse</td><td>a fixture applied to every test without being asked for</td></tr>
    <tr><td class="k">conftest.py</td><td>shared fixtures for a folder and everything under it. No import needed</td></tr>
    <tr><td class="k">override</td><td>a fixture in a test file shadowing one of the same name from conftest</td></tr>
    <tr><td class="k">tmp_path</td><td>built in: an empty folder, new per test, cleaned up for you</td></tr>
    <tr><td class="k">capsys / capfd</td><td>built in: captured output. capfd when the write bypasses Python</td></tr>
    <tr><td class="k">caplog</td><td>built in: log records. Set the level or you capture nothing</td></tr>
    <tr><td class="k">monkeypatch</td><td>built in: change something temporarily, put back automatically</td></tr>
  </table>
</div>'''),

"glossary-running-and-selecting": ("glossary: running and selecting", '''<div class="card hot">
  <div class="lab">glossary: running and selecting</div>
  <table>
    <tr><td class="k">test id</td><td>the name in the report, e.g. <code>test_naming[2-many]</code></td></tr>
    <tr><td class="k">parametrize</td><td>run one test many times with different inputs, each reported separately</td></tr>
    <tr><td class="k">indirect</td><td>send a parametrize value to a fixture, so each case gets setup and teardown</td></tr>
    <tr><td class="k">marker</td><td>a label on a test: <code>@pytest.mark.slow</code>. Select with <code>-m</code></td></tr>
    <tr><td class="k">skip / skipif</td><td>does not apply here. skipif decides at collection</td></tr>
    <tr><td class="k">xfail</td><td>known broken. Needs <code>strict=True</code> or it stays green once fixed</td></tr>
    <tr><td class="k">xpass</td><td>an xfail that unexpectedly passed. Usually means delete the marker</td></tr>
    <tr><td class="k">deselect</td><td>excluded from this run by <code>-k</code> or <code>-m</code>. Not the same as skipped</td></tr>
  </table>
</div>'''),

"glossary-test-doubles": ("glossary: test doubles", '''<div class="card hot">
  <div class="lab">glossary: test doubles</div>
  <table>
    <tr><td class="k">test double</td><td>any stand-in used instead of the real thing</td></tr>
    <tr><td class="k">dummy</td><td>passed only to fill a signature. Never actually used</td></tr>
    <tr><td class="k">stub</td><td>always returns the same canned answer</td></tr>
    <tr><td class="k">fake</td><td>a real but simplified implementation. A dict instead of a database</td></tr>
    <tr><td class="k">spy</td><td>works, and records how it was called</td></tr>
    <tr><td class="k">mock</td><td>a spy that also asserts it was called correctly</td></tr>
    <tr><td class="k">patching</td><td>replacing something in place, by name</td></tr>
    <tr><td class="k">injection</td><td>passing the collaborator in, rather than the code fetching it itself</td></tr>
    <tr><td class="k">seam</td><td>a place you can change behaviour without editing there. An argument is one</td></tr>
    <tr><td class="k">mock transport</td><td>a fake put in the place where code would talk to the network</td></tr>
  </table>
</div>'''),

"glossary-kinds-of-test": ("glossary: kinds of test", '''<div class="card hot">
  <div class="lab">glossary: kinds of test</div>
  <table>
    <tr><td class="k">unit</td><td>one function or class, nothing real underneath it</td></tr>
    <tr><td class="k">integration</td><td>several pieces together, often with a real file or database</td></tr>
    <tr><td class="k">end-to-end</td><td>the whole system as a user meets it. Slow, valuable, few</td></tr>
    <tr><td class="k">regression test</td><td>written to pin a bug you just fixed, so it cannot come back</td></tr>
    <tr><td class="k">smoke test</td><td>does it start at all</td></tr>
    <tr><td class="k">property-based</td><td>assert a rule for all inputs and let a tool hunt counterexamples</td></tr>
    <tr><td class="k">fuzzing</td><td>throw generated input at it and check nothing escapes the contract</td></tr>
    <tr><td class="k">differential</td><td>run two implementations over one input; whichever disagrees is wrong</td></tr>
    <tr><td class="k">oracle</td><td>differential testing where the reference is a trusted external tool</td></tr>
    <tr><td class="k">golden / snapshot</td><td>compare output against a stored known-good file</td></tr>
    <tr><td class="k">contract test</td><td>pin the shape you publish: names, codes, status codes, schema version</td></tr>
    <tr><td class="k">meta-test</td><td>a test about the test suite, e.g. does every test still assert</td></tr>
  </table>
</div>'''),

"glossary-test-quality": ("glossary: test quality", '''<div class="card hot">
  <div class="lab">glossary: test quality</div>
  <table>
    <tr><td class="k">coverage</td><td>which lines ran. <b>Not</b> whether anything checked them</td></tr>
    <tr><td class="k">branch coverage</td><td>did both sides of each <code>if</code> run</td></tr>
    <tr><td class="k">mutation testing</td><td>break the code deliberately and see whether the suite notices</td></tr>
    <tr><td class="k">equivalent mutant</td><td>a deliberate break that changes no behaviour, so nothing can catch it</td></tr>
    <tr><td class="k">mutation gate</td><td>admit a generated suite only if it kills a threshold of mutants</td></tr>
    <tr><td class="k">flaky</td><td>passes and fails without the code changing. Always a bug, never noise</td></tr>
    <tr><td class="k">quarantine</td><td>move a flaky test behind a deselected marker with a ticket</td></tr>
    <tr><td class="k">test smell</td><td>a sign the test or code is wrong. More patching than assertion is one</td></tr>
  </table>
</div>'''),

"glossary-an-ai-author": ("glossary: an AI author", '''<div class="card hot">
  <div class="lab">glossary: an AI author</div>
  <table>
    <tr><td class="k">apparatus</td><td>the machinery that makes reading generated output unnecessary: tests, types, sanitizers, canaries</td></tr>
    <tr><td class="k">provenance separation</td><td>whatever wrote the code does not grade it, and ideally is not the same family</td></tr>
    <tr><td class="k">self-preference bias</td><td>an evaluator scoring its own generations higher than a human would</td></tr>
    <tr><td class="k">intrinsic self-correction</td><td>a model revising its own output with no external signal. Does not reliably work</td></tr>
    <tr><td class="k">external feedback</td><td>a signal from outside the model. A test run is one, which is the point</td></tr>
    <tr><td class="k">characterization test</td><td>assertions transcribed from what the code currently does. Pins change, not correctness</td></tr>
    <tr><td class="k">the oracle problem</td><td>knowing what the right answer is, independently of the thing being tested</td></tr>
    <tr><td class="k">metamorphic relation</td><td>a property linking two runs when you cannot state the answer for either</td></tr>
    <tr><td class="k">translation validation</td><td>proving one output matches its input for this run, rather than proving the tool</td></tr>
    <tr><td class="k">the intent gap</td><td>tests cannot check that they encode what was actually wanted. No technical fix</td></tr>
  </table>
</div>'''),

}
