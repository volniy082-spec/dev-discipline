<!--
Writer's report. The form is checked by a script or the auditor; the truth, by re-running.
- A key starts the line, in CAPITALS, followed by ": ". Sub-fields are indented 2 spaces. Fill every {{…}}.
- EXIT: DONE | BLOCKED(reason) | SPEC_CONFLICT(test, source) | IMPOSSIBLE | NOT_REPRODUCED.
  For a non-DONE exit, the witnesses prove the refusal, the blocker or the non-reproduction.
- Criteria: PASS | FAIL | NOT_PROVEN. Skip, timeout, ImportError, "0 tests" are NOT_PROVEN.
- cmd is one command in backticks, copyable as is. expected is written BEFORE the run.
  fact is the output verbatim. source is path:line of the built code.
- HYPOTHESIS starts with confirmed | refuted | not_tested, then how it was checked.
- A number in CRITERIA and WITNESSES needs a command in backticks on the same line or a cmd
  in its block; otherwise check_report rejects it. In free-text lines (ROOT, OPEN_RISKS) a number is not evidence.
- $DD is the skill's scripts/ folder (the brief's DD key). Take TREE RIGHT AFTER the gate, BEFORE writing
  the report (the worktree index is not touched; a bare `git write-tree` gives the index tree, not yours):
  TREE=$("$DD/tree_hash.sh" "$WT")
- PARENT_RED: "$DD/prove_fix.py" --repo "$WT" --base "$SHA" --fix WORKTREE --cmd "<test>"
  (red by assertion, not by import; a new feature with no entry point on the parent: "n/a — reason").
- If the harness refuses the file write, return the report as text; the orchestrator will put it in place.
- Never put secrets, tokens or keys in the report.
-->
# REPORT {{task id}} · attempt {{1|2}}

EXIT: {{DONE|BLOCKED(…)|SPEC_CONFLICT(…)|IMPOSSIBLE|NOT_REPRODUCED}}
BRIEF: {{absolute path of the brief}}
WORKTREE: {{absolute path of the worktree}}
SHA: {{base — HEAD of the worktree}}
TREE: {{40 hex — tree_hash.sh at gate time}}
HYPOTHESIS: {{confirmed|refuted|not_tested}} — {{how, one phrase}}
ROOT: {{root cause in one sentence, path:line}}
CHANGED: {{changed paths, comma-separated; ⊆ the brief's PERIMETER}}
CONTRACT_EDITS: {{none | protected paths from CONTRACT that were touched, with a reason for each}}
INVARIANT: {{test::name in the gate | none — reason}}
MEASURE:
  cmd: `{{command from the brief}}`
  before: {{output before the edit}}
  after: {{output after the edit}}
PARENT_RED:
  cmd: `{{command}}`
  expected: {{exit 1 — failure by assertion}}
  fact: {{verbatim}}
GATE:
  line: {{the runner's summary line, verbatim}}
  log: {{log path}}
CRITERIA:
- {{criterion}}: {{PASS|FAIL|NOT_PROVEN}} — `{{command}}` exit={{N}} "{{output line}}"
WITNESSES:
- W1
  cmd: `{{command}}`
  expected: {{expectation before the run}}
  fact: {{output verbatim}}
  source: {{path:line "quote"}}
- W2
  cmd: `{{command}}`
  expected: {{expectation before the run}}
  fact: {{output verbatim}}
  source: {{path:line "quote"}}
NOT_CHECKED: {{none | what was not checked and why}}
DEVIATIONS: {{none | what was done outside the brief and why}}
OPEN_RISKS: {{none | up to three items separated by ";"}}

## CLOSING
<!-- One result document per item (delegation.md §4). Written by the writer; the orchestrator uses it as is. -->
- README (5 lines max): {{what changed, for the task folder's README}}
- Follow-ups: {{none | item — return condition, one per line}}
- Plan line: {{one line for the plan, ≤ 600 characters}}
- Commit message: {{subject; body = measure before/after, gate line, what is not done}}
- Paths: {{explicit paths to commit, no globs}}
- Metrics row: {{draft row for the ledger, if one is kept}}
