# Refactoring, flaky tests, visible output

Details for the red flag "skip, retry, sleep, `noqa` to get green" in `SKILL.md`. Rationale: `evidence.md`.

## 1. Impacted tests before "done"

An agent gains more from knowing which tests an edit touches than from following a procedure: a map of impacted
tests reduces regressions, while a TDD instruction without such a map does not (`evidence.md`).

```bash
pytest --testmon                                    # pip install pytest-testmon
node_modules/.bin/vitest related --run <files>      # or jest --findRelatedTests <files>
bazel query 'rdeps(//..., set(<targets>))'
```

The report carries a line `impacted_tests: N run / N passed` with the command. No retries.

## 2. Before refactoring

Refactoring silently changes behaviour, and a mixed commit hides that from review.

1. **Characterization tests before the edit:** `tests/test_char_<module>.py`, functions `test_char_*`. They
   pin current behaviour on generated and real inputs. This is a temporary snapshot, not a correctness oracle
   (`proof-and-oracles.md` §5). They are retired in a separate `test: retire char_*` commit
   under contract (`oracle-protection.md` §1), once `behav:` tests cover the behaviour.
2. **Separate commits.** `struct:` — behaviour unchanged: outputs byte-identical, pins do not move.
   `behav:` — behaviour changes on purpose, with a test as proof. Mixed commits are forbidden.
3. No bulk `--update` of snapshots: every changed snapshot is explained.

## 3. Visible output is a contract (Hyrum's law)

Everything observable (format, order, precision, error texts) is already relied on by someone. For every
`behav:` commit, diff the old and new versions' output over a corpus of inputs and record the difference in the changelog.

## 4. Flaky tests

"Rerun until green" hides defects: flaky failures are frequent and often cluster around a shared root.

- `flaky.txt` is the registry: `<test id>  # <incident> <date> <owner> <until date>`. Retries are allowed only
  for tests in the registry. The registry only shrinks: `$DD/gate_meta.py --base <ref>` (`gate-integrity.md` §2).
- A test may be declared flaky or "fixed" only on a measurement without retries (`$DD` is the skill's `scripts/`):
  ```bash
  $DD/flake_check.py --cmd "<test>" --rate 0.02 --confidence 0.95     # 149 runs
  $DD/flake_check.py --cmd "<slow test>" --runs 59 --timeout 120     # catches a 5% flake with 95% probability
  $DD/flake_check.py --cmd "<test>" --runs 149 --stop-on-fail          # until the first failure
  ```
  Ten runs catch a 2% flake only about 18% of the time. Put the power in the report:
  N runs catch a flake of rate p with probability 1−(1−p)^N. For a slow test use a smaller N
  (`--runs 59`, `--rate 0.05`) with that line, or `--stop-on-fail`: one failure is enough to
  call the test flaky. A fix counts only at 0/N. A run where everything was skipped never reached the tests:
  that is NOT_PROVEN, not PASS.
- `prove_fix.py` pins the environment (hash seed, time zone, locale); `flake_check.py` does not: seed
  and time zone vary between runs, otherwise an ordering or time flake would give a false 0/N.
- Quarantine is an entry in `flaky.txt` with owner, reason, issue and deadline. A solo agent adds it itself,
  without a human: deadline and reason go in the report and the commit; in a team, into PR review. An expired entry is debt.
- Look for the cause first: time, ordering, network, shared state, async waits. The measurement must be
  deterministic before the edit (`debugging.md` §1).
- Randomness inside the test itself (real clock, `sleep`, `random`, ordering) is a test defect. You may
  make it deterministic even if asked to "just retry": a fixed clock (`monkeypatch` on
  `time.time`, `vi.useFakeTimers()`), `random` removed, an explicit wait for an event. Conditions:
  - every assert and every expected value stays: `$DD/guard_diff.py --base <sha>` reports no `weakenings`;
  - `flake_check.py` shows more than 0 failures before the edit and 0/N after, with the same or greater power;
  - a separate `test: deflake <id>` commit.
  If getting green requires changing an assert or an expected value, that is no longer deflaking but `SPEC_CONFLICT(test, source)`.
- `prove_fix.py` is not needed on a deflake commit: the old test version is not reliably red, it flickers.
  The proof is `flake_check.py` before and after plus `guard_diff.py`.
- Proof runs (`prove_fix.py`, `flake_check.py`, the final gate) always run without retries.

## 5. Static checker after an edit — optional

Pays off on well-typed code. On weakly typed code the agent drifts into fixing other people's errors.
Enable it only for modules with high type coverage, on changed lines, with a baseline
(a project PostToolUse hook running `ruff`, `mypy` or `pyrefly`).
