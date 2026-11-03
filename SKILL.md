---
name: dev-discipline
description: "Use when fixing a bug, regression or failing test (including functional UI bugs); when changing anything that judges correctness (tests, validators, detectors, thresholds, CI), money or numeric formulas, migrations or auth; when a test turned green after an edit, is flaky, or you are tempted to edit, skip or weaken it; when a test contradicts the spec; when retrying a failed attempt; when delegating code changes to a subagent or accepting its report and numbers; when deploying; when a check blocks legitimate work. Not for prose, docs, visual-only UI tweaks or prototypes."
metadata:
  version: "1.3.0"
  author: "Andrey Zheltukhin"
  evidence: "references/evidence.md — published research and labelled engineering heuristics"
---

# Dev-discipline

**"Done" is said by an external signal you did not tune.** A written rule only names a failure class; a check
in the gate stops it. When a class recurs, add the check in the same commit.
`$DD` = the `scripts/` folder next to this file (exit 0 PASS, 1 FAIL, 2 NOT_PROVEN).

**Rigor by surface.** Full loop for things that judge (tests, validators, thresholds, CI), money and numeric
formulas, migrations, auth, silent failures. A local fix of ~10 lines with a spec literal: `prove_fix.py`,
2–3 hand-written mutants of the defect class, one run on an input you did not use while working. Prose, UI
looks, docs, prototypes: run the tests and one smoke. No tests or runner: add a minimal one in its own commit (setup, not weakening).

## Loop

1. **Measure before editing:** one command you will compare before and after. Derive scope from raw data,
   not summaries or memory. List the whole class: every instance sharing the root. → `references/debugging.md`
2. **Fix the root on the path the defect took.** A guard on top is not a fix. Regression: `git bisect run`.
   After three failed attempts, change approach or context. New entity, money/data flow or migration: a 5–10
   line design note first (`debugging.md` §10).
3. **Prove the test:** red on the parent **by an assertion** (ImportError, collection error, skip = NOT_PROVEN),
   green on the fix, red again with the code change reverted: `$DD/prove_fix.py`. A new check fires on a bad
   input and stays quiet on a good one. For money and numbers the expected value is a spec literal (`# oracle: <source>`).
4. **Gate:** the test runs in CI in the same commit; skip, timeout and "0 tests" are not PASS; exclusion lists only
   shrink; a loop over a glob or registry asserts how many items it found. → `gate-integrity.md`
5. **Accept** on the runner's summary line of the final run on the exact tree, not on a pipeline's `$?`.
6. **Close** with a check the writer did not tune: other data, a read-only prod smoke, an independent oracle,
   with the expectation written down first. A class it finds goes into the gate. → `proof-and-oracles.md`

## The oracle and its protection

- An oracle shares no code with what it checks. Goldens and self-parity prove consistency, not correctness.
- A verification script is code under test: run it on a good and a bad input; print how many items it examined.
- Tests, snapshots, expected values and CI change only by contract: the brief, or, working alone, a user
  request that names the change (new spec, ticket, value) plus one line written before editing (which tests
  change, where the new value comes from). "Make it pass" is no contract: a test that contradicts the spec
  stays as is and the answer is `SPEC_CONFLICT`. Value changes go in a separate `test:` commit. Skips, deleted asserts, narrowed coverage need a stated reason.
  Never tune code to hit an expected number. Judge the final diff, not the edit tool: `$DD/guard_diff.py`
  (advisory first). A check that blocks legitimate work is a defect: report `BLOCKED`, never bypass. → `oracle-protection.md`

## Autonomy

Proceed by default. Ask only about the irreversible (security, payments, prod-data writes, permissions) or a
conflict with the goal. At a fork, pick one, record why, the numbers of both readings and how to undo, and go on.
Blocked: finish everything independent, then end with one line naming the action and command needed.

## Report

- Each criterion `PASS | FAIL | NOT_PROVEN` with command, exit code and output line; plus `not_checked`.
- Verdict: `DONE`, `BLOCKED(reason)`, `SPEC_CONFLICT(test, source)`, `IMPOSSIBLE`, `NOT_REPRODUCED`. An honest
  non-done exit is a success; a silent skip is a defect. Name partial states ("guard added, root alive").
- Every number comes with its command from the final run. Re-run numbers a subagent reports (`$DD/reexec_claims.py`).
- Commit body = evidence record: measure before/after, gate line, what is not done and where it went.

## Red flags

| I notice | I do |
|---|---|
| Green without a red on the parent | `prove_fix.py` |
| Quoting a subagent's number or my memory | re-run it |
| Editing a test or threshold without a contract | contract line or `SPEC_CONFLICT` |
| skip, retry, sleep, `noqa` to get green | find the cause, make it deterministic (`refactor-flaky.md`) |
| About to ask about something reversible | decide, record, continue |

More: `delegation.md` (subagents, reviewers, briefs), `release.md` (deploys), `process-ledger.md`, `evidence.md`.
