# Gate integrity

The gate is the external signal that "done" relies on: green must mean "checked".
`$DD` is the skill's `scripts/` folder. Rationale lives in `evidence.md`.

## 1. The gate runs everything that is collected

- By default CI runs **every test the runner collects** (`pytest`, `jest`, `go test ./...`), with no
  hand-kept list. A new test then enters the gate on its own.
- An explicit test list is an option for slow or legacy suites. It requires an orphan meta-test: a
  collectable test file that is neither in the list nor in an exclusion list (files or folders; an entry
  `f.py::test_x` does not cover the file) is a FAIL.
  ```bash
  $DD/gate_meta.py --base <base sha>          # 0 PASS, 1 FAIL, 2 NOT_PROVEN
  ```
- A new test enters the gate in the same commit as the fix.
- No tests or no runner: add a minimal one (config, one test, gate command) in its own commit and mark it
  in the report as setup. This is not a weakening; `guard_diff` labels such a config `bootstrap`.

## 2. Exclusions only shrink

- Every exclusion (legacy, flaky, slow, temporarily disabled) is a line in an explicit file with a reason:
  `tests/legacy/test_old.py  # reason; when to restore`.
- The list only shrinks. `gate_meta.py --base <sha>` compares it with the version at the base;
  growth is a FAIL. The lists are named in `.dev-discipline.json` → `"shrink_lists"`.
- Criteria and thresholds only get stricter. A weakening needs a contract and a reason (`oracle-protection.md`).

## 3. A skip in the gate is not a PASS

Inside the gate, a missing dependency, a missing external oracle (binary, service, dataset) or "0 tests" is a
gate FAIL, and NOT_PROVEN in the report. A silent skip on the CI machine looks green.

- The gate sets `GATE=1` (in the scripts' `--cmd`: `GATE=1 pytest -q`). The helper fails instead of skipping:
  ```python
  def require(cond: bool, what: str) -> None:
      if not cond:
          if os.environ.get("GATE") == "1":
              raise AssertionError(f"{what} missing in the gate: this is a FAIL, not a skip")
          pytest.skip(f"{what} missing (outside the gate)")
  ```
- A safety net for the whole run (`conftest.py`):
  ```python
  def pytest_sessionfinish(session, exitstatus):
      tr = session.config.pluginmanager.get_plugin("terminalreporter")
      skipped = [r.nodeid for r in tr.stats.get("skipped", [])] if tr else []
      if os.environ.get("GATE") == "1" and skipped:
          print(f"\nGATE: skipped {len(skipped)} -> FAIL: {skipped[:5]}")
          session.exitstatus = 1
  ```
  Legitimate skips (platform, OS) go into a shrink-only list, compared by `nodeid`.
- The gate log header prints which oracles are active: external tool versions, data path, number of
  collected tests. An empty line there is visible at once.

## 4. Environment contract

The same code can give a red or a green gate depending on an environment variable.
The gate must run in the production environment.

- Every variable the production code reads (`os.environ.get`, `os.getenv`, `process.env.X`) is either
  exported by the gate script or named in it with a line `# gate-env: NAME — reason`.
- A test checks both sides: a new variable without a line is a FAIL; a line for a variable the code no
  longer reads is a FAIL. The number of reads found is pinned (§6).
- Write down the limit of the detector honestly: indirect reads (pydantic-settings, config objects) are invisible.

## 5. Root from the file's own path

Scripts and tests find the repository root from their own file, not from `cwd`. Otherwise a gate run from
another directory or worktree judges the wrong tree or fails with false ImportErrors.
```bash
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
```
```python
ROOT = Path(__file__).resolve().parents[1]
```
Commands on the tree name it explicitly: `git -C "$ROOT" …`, an absolute path to the gate script.

## 6. A search asserts how much it found

Apply this **only where a test walks a glob, registry, directory or extracted list**. Ordinary
example-based tests do not need it. The single danger: the source degenerated to nothing, the loop ran
zero iterations, the test is green.

```python
from pinned import pin            # templates/pinned.py
files = sorted(ROOT.glob("migrations/*.sql"))
pin(len(files), 42, "SQL migrations")                              # exact: the number is known
pin(len(registry()), 10, "handlers in the registry", mode="at_least")   # growing source
pin(len(future_items()), 0, "entries in the future registry")      # empty future source: pin at zero
for f in files: ...
```

- The pin message tells the two cases apart. More: the code grew, update the number in the same commit.
  Fewer: check the search criterion first, do not edit the number.
- A pin goes up only with a probe for each new item: why it legitimately appeared. Raising a pin to
  accept a defect is forbidden.
- A pin goes down only after proof that code was removed, not that the search broke.
- If there are many such sweeps, add a meta-test "sweep without a pin is a FAIL". It needs positive
  controls: known sweeps it must find. Inherited uncovered sweeps go into a shrink-only list.

## 7. Known failures: a two-way registry

A sweep over many cases does not silently pass a failed case. Instead of a skip, use a registry
`EXPECTED_FAILURES = {case_id: "error fragment"}` (`templates/expected_failures.py`):

- an unexpected failure is a FAIL;
- an expected failure that now passes is a FAIL: remove the line from the registry;
- an expected failure with a different cause is a FAIL;
- a registry key that is not among the cases is a FAIL (the registry does not rot).

The registry only shrinks: a line leaves when its case is fixed.

## 8. Two-way correspondences

Check a correspondence "A ↔ B" (catalog ↔ implementation, routes ↔ handlers) in both directions and against
what the running system returns, not against its config. One direction leaves half of it invisible.

## 9. Optional: a derived preflight (gate > 30 min)

Only if the gate takes half an hour or more and often goes red on "bookkeeping" (pins, snapshots, indexes).

- The subset is **derived** from the gate list by a mechanical criterion, not picked by hand.
  Example criterion: `grep -lE 'pin\(|snapshot|golden|_generated'`. A hand-picked set is always narrower than the gate.
- The preflight runs in the gate's environment, before the full run.
- Classify every red full run: `real | bookkeeping | env`. A red from bookkeeping is a process defect:
  add the missing criterion to the selector.

## 10. Symbolic anchors

A test that checks data against source code points at a symbol (function name, key, marker comment), not at
`file:line`. Line numbers shift with any nearby edit and give a false red.
```python
src = inspect.getsource(module.compute_tax)      # not lines[118:131]
```

## 11. Generated files: one regen-all command

- All generated artifacts (indexes, schemas, clients, catalog snapshots) are rebuilt by one command,
  for example `make regen-all`.
- The gate checks they are fresh: `make regen-all && git diff --exit-code -- <generated paths>`.
- Generated files are never edited by hand. A shared index under parallel work is regenerated once, after the merge.

## 12. The gate verdict

- Read the runner's summary line of the final run (`=== 812 passed in 95s ===`), not the pipeline's `$?`
  and not `tail`. Without `pipefail`, `cmd | tee log; echo $?` returns the exit code of `tee`.
  ```bash
  set -o pipefail; ./gate.sh 2>&1 | tee gate.log; echo "rc=$?"     # bash and zsh
  ```
- Compare the passed count with the previous run. A drop in the count without an explanation is a FAIL.
- A partial run, timeout, collection error or `0 tests` is NOT_PROVEN. The verdict is on the exact commit tree.
