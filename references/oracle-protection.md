# Oracle protection

The oracle is everything that decides whether a change is "green": tests, snapshots, fixtures, expected values,
pins, runner config, `conftest.py`, CI, the gate script, the checks themselves. The cheapest way to green is to
weaken the oracle. A written ban does not close that path. A check of the final diff inside the gate does.
Rationale lives in `evidence.md`.

## 1. Contract before work

Tests, snapshots, expected values and CI change only by contract. With a coordinator, the contract is in the
brief. Working alone, the contract is a user request that names the change (a new spec, a ticket, a value)
plus one line written before editing: which tests change and where the new value comes from. "Make the tests
pass" or "make it green" names no change: if a test contradicts the spec, leave the test, fix the code to the
spec and report `SPEC_CONFLICT(test, source)`. A value change made that way is allowed, in a separate `test:`
commit. Skips, deleted asserts, narrowed coverage: only with a reason in the report and the commit. Never tune
code to hit an expected number.

| Edit | Allowed? |
|---|---|
| New test, new test file, tests added to an existing file, stronger assert | yes, no contract needed |
| Change an expected value | by contract, with the source of each value, in a `test:` commit |
| Skip/xfail, delete an assert, narrow parametrization or collection | by contract, reason in report and commit (`WEAKEN-OK`) |
| Runner config, CI, `conftest.py`, gate script | by contract; the first runner in a repo without tests is setup |
| The checks themselves, the grant channel, the evaluation harness | never granted to the writer |
| Tune code or a parameter to hit an expected number | never |

A test contradicts the spec and the source is unclear: stop with `SPEC_CONFLICT(test, source)`.

## 2. Grant channel (with a coordinator or PR review)

Permission for a protected edit is granted by the coordinator, not the writer. A single agent does not set up a
channel: it puts the paths from the contract line (§1) into a temp file outside the tree, runs
`guard_diff.py --allow <file>` and puts the result in the report.

- **Grant file (allowlist):** one glob per line (the line's first word; `*` crosses `/`), `#` starts a
  comment, `WEAKEN-OK: <path> <reason>` is an allowed weakening (ignored without a reason; it also grants the
  path). The file's path is in `.dev-discipline.json` → `"allow_file"` and is read from the main checkout:
  a writer in a worktree cannot grant itself. A one-off file: `guard_diff.py --allow <file>`.
- No `allow_file` but a brief exists: the auditor writes the `CONTRACT EDIT=` paths to a temp file outside the
  worktree and passes it via `--allow` (`templates/agents/auditor.md`, fact 4).
- Grants are issued by one project command that logs date, task, reason and paths. It is **not** part of
  the skill; an example `tools/grant_edit.sh` for a project:
  ```bash
  set -eu; F="$(git rev-parse --path-format=absolute --git-common-dir)/../.dd-allow"; L="$F.log"
  case "${1:-}" in --show) cat "$F";; --clear) : > "$F"; echo "$(date +%F) clear $*" >> "$L";;
    --task) t=$2 r=$4; shift 4; for p in "$@"; do echo "$p  # $t: $r" >> "$F"; done
            echo "$(date +%F) $t grant $* — $r" >> "$L";; *) echo "usage" >&2; exit 2;; esac
  ```
  Usage: `tools/grant_edit.sh --task T-17 --reason "contract T-17" tests/test_tax.py`; `--show`; `--clear`.
  In the config `"allow_file": ".dd-allow"`; the file itself goes in the main checkout's `.gitignore`.
- The grant script, the checks, the grant file and the evaluation harness are never granted.
- So the coordinator does not ask a human about every grant, the project's `.claude/settings.json` has a narrow
  rule for that script: `"allow": ["Bash(tools/grant_edit.sh *)"]`. A human adds it, once.
- **Reconciliation at close:** granted / changed / unused / changed without a grant. Changed without a grant is
  a FAIL. Unused is a line in the report. Then `--clear`.
- In team work the channel is PR review (CODEOWNERS on tests and CI): the contract is the PR description.

## 3. Diff check in the gate

A hook on Edit is bypassed through the shell, a script, `sed -i`, `git checkout`. So the **result** is judged:
the tree against the base, whatever channel changed it. `$DD` is the skill's `scripts/` folder.

```bash
$DD/guard_diff.py --base origin/main                                # JSON; exit 0 PASS, 1 FAIL, 2 NOT_PROVEN
$DD/guard_diff.py --repo <writer worktree> --base <SHA> --allow <grant file>
```

- The diff is `base..working tree` plus untracked files. If the base is not an ancestor, the merge-base is used (the output says so).
- `.dev-discipline.json` is read **from the base**: editing the config in the tree does not change what the tree is
  judged by. Keys: `"protect"` (extra protected globs: pins, `pyproject.toml`, `package.json`, check scripts),
  `"tests"` (extra test directories), `"protect_defaults": false`, `"allow_file"` (grant file, §2).
  Protected by default: tests, snapshots, runner config and `conftest.py`, CI.
- `violations`: an existing protected file changed or deleted without a grant; a new runner or CI config.
- Not a violation: new test files and snapshots; `extended`: an existing test file only gained tests or
  asserts, old functions untouched; `bootstrap`: the base had no tests and no runner config, so the new
  config counts as setup. Shrink-only lists are judged by `gate_meta.py --base`.
- `weakenings`, also inside granted files. **Counted per function**, on code tokens (strings and comments do
  not count): skip/xfail/`.only` must not grow, asserts (`pytest.raises`, `expect(`, `t.Error*`) must not drop.
  A deleted test counts as 0. A per-file total hides weakening: a deleted assert is offset by a neighbouring test.
- Old→new pairs: by name; by body hash (rename, move to another file); within the same file, the same name
  in another class, then a near-identical body (token similarity ≥ 0.8). A rewritten test is judged as an edit.
- Not flagged: changed values, new tests, strengthening. A value change is judged by the contract and review.
- A weakening with a reason: `WEAKEN-OK: tests/test_tax.py test covered a removed API; issue 412`. Write the
  exact path: a glob lifts the check wider than needed. In `--calibrate` the same marker goes in the commit message.
- The check is a test inside the gate, not a separate ritual: the gate goes red on its own.

## 4. Calibrate before blocking

A check that blocks legitimate work is a defect of the check. It will be bypassed, and the protection is gone.

1. Replay history: `$DD/guard_diff.py --calibrate 80` gives the flags for each of the last commits.
   `touch` (edits without a grant) is expected when there is no contract; measure precision on weakening flags.
2. Explain every flag: a weakening (with or without a reason in the commit) or a false flag (the test lives on
   under another name, in a helper, in a case table). A false flag: fix the rule and add a MUST-PASS self-test case.
3. Warn first (output goes to the report, the gate stays green); block only after "N real / 0 false".
4. Calibration on the check author's own history is agreement with yourself. If you can, run one more repository.

## 5. Two-sided self-test

The check's self-test has both sets:
- MUST-FLAG: a deleted assert, a new `@skip`, a deleted test, an edit without a grant, an edit
  via `sed -i`, via `conftest.py`, via runner config and CI;
- MUST-PASS: real legitimate actions: a new test, a value change by contract, a heredoc,
  absolute paths, an identifier rename.

Every false block becomes a MUST-PASS case in the same commit. The self-test is in the gate.

## 6. Unparseable input

- A hook that could not parse a command or file **lets it through** (fail-open): the diff check will catch it.
- A diff check that could not evaluate a protected path (does not parse, no base) gives NOT_PROVEN, not PASS.

## 7. Optional: a thin edit hook

A hook is an early signal, not the main protection. Add it only if a calibrated diff check is already in the
gate. The hook goes **in the project** (`<repo>/.claude/settings.json`), **never in `~/.claude/settings.json`**;
it reads grants only from the project's grant file and guesses nothing heuristically; fail-open on
unparseable input; two-sided self-test. A global hook that does not know the project's grant channel
blocks sanctioned edits and will most likely be removed.

## 8. Working alongside the project's own guard

In `.dev-discipline.json` the key `"oracle_guard"`: `"project" | "skill" | "none"`.

- No config: look for a guard: `.claude/hooks/*guard*`, a grant file, a gate test with `guard` in its name. Found:
  `project`: the skill installs no hooks, runs the project's commands and writes `oracle guard: project (<command>) PASS|FAIL`.
- `skill`: `guard_diff.py` is added to the gate as a test after calibration (§4).
- One meaning of "protected" for project and skill: project paths go in `"protect"`/`"tests"`; with its own
  classifier, `"protect_defaults": false`. The `"oracle_guard"` key is read by the agent, not the script.
- Do not stack a second guard on top of the first.

## 9. Known limits

- **A test moved to another file with edits, or rewritten below 0.8 similarity, reads as deleted**
  (a false flag). Review it by eye; if nothing was weakened, `WEAKEN-OK` with reason "rename".
- `WEAKEN-OK` lifts the check from the whole file. While the marker stands, a new weakening in that file is
  invisible. Remove the marker in the closing commit.
- The counter sees the number of skips and asserts, not their strength: it misses a looser tolerance (`rtol`),
  a narrowed domain with the same assert count, a swapped fixture, special-casing (`if x == fixture: return expected`),
  `__eq__`, retries. Those are caught by the contract, re-measurement on independent data and a reviewer with mutants.
- Precision and recall on real weakenings are not published; the self-test covers only synthetic cases.
  Measure precision on your own history (§4); expect false flags mainly on rewritten tests.
- Languages: token counting is reliable for Python; for other languages, check with the self-test before blocking.

## 10. In the report

```
oracle guard: skill (guard_diff.py --base 1a2b3c) exit 0 — PASS — 0 violations, 0 weakenings, 1 granted, 0 extended, 0 bootstrap, 3 protected changed
grants: granted 4 / changed 3 / unused 1 / ungranted 0
WEAKEN-OK: tests/test_tax.py (rename test_vat -> test_vat_rate)
```
No guard at all: `not_checked: oracle guard absent`.
