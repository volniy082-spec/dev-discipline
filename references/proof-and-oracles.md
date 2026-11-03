# Proving the test, and oracles

Details for step 3 and the "The oracle and its protection" section of `SKILL.md`; rationale in `evidence.md`. A test
that is green without the fix proves nothing; a check that stays quiet on bad input is decoration.

## 1. Red on the parent, by an assertion

| Leg | Tree | Expected |
|---|---|---|
| A | parent (merge-base) + new tests | red **by an assertion**; with `--expect`, the message matches |
| B | fix | new test green; with `--full-cmd`, the whole suite green |
| C | fix with all non-test changes reverted | tree equals A; red again by an assertion |

```bash
$DD/prove_fix.py --repo <worktree> --base <sha before fix> --fix WORKTREE \
  --cmd "python3 -m pytest -q tests/test_x.py::test_y" --expect "== 40" --full-cmd "python3 -m pytest -q"
```

- `--fix WORKTREE` (or a path to a worktree directory) takes the uncommitted tree; `--fix HEAD` takes the
  committed fix. `--cmd` runs through `bash -c`: `GATE=1 cmd`, `&&`, `cd` all work.
- Marker, optional: if the test has several failure points, print a marker right before the deciding
  assert and add `--reached REACHED`. A red without the marker is then a failure for some other reason.
- **Not red:** ImportError, collection error, skip, xfail, timeout, fixture failure, "0 tests", an exception
  without an assert (a crash fix is proven by an assert on behaviour). These are `NOT_PROVEN` (exit 2), not proof.
- Each leg runs `--repeat` times (default 1; for a nondeterministic repro use `--repeat 3`). A red that
  turns green on a repeat is an unstable repro (exit 1).
- Put the receipts path (`receipts_dir`) in the report. Without the script: `git worktree add /tmp/base <base>`,
  copy only the test files there, run. No `stash` in the live tree.
- Have a known-good version (a past release, a reference)? The test must pass on it.

## 2. Vacuity on the exact fixture

Before calling a test a guard, run the **old code** (or the formula with the protected term removed)
**on the same fixture**. If old and new code give the same result there, the fixture does not
discriminate; pick an input that does.

Common forms of vacuity:
- both paths clamp the value to zero or a default; the input was selected by the same predicate the test checks;
- the mutation was applied to data that is already correct; `is None` on a value that is never `None`;
- two paths enforce the rule: remove one and the test stays green because the other covers it;
- a later branch masks an earlier one; an "impossible" branch was never exercised by injecting bad data;
- the test's witness is itself dead (fixture does not load, loop over an empty list);
- `assert violations == []` is half an oracle: loosen the tolerance and nothing turns red.

A written rule does not prevent vacuity. A mutant or a run of the old code catches it.

## 3. Negative tests for checks

Every check (invariant, detector, linter, gate rule, validator) gets a pair:
- a known-bad input produces **exactly its own** finding, attributed to **its own** rule. A rejection by
  some other rule does not count: otherwise the negative is vacuous;
- a known-good input passes silently.

A check's tolerances are pinned as literals in the test (`assert TOL == 1e-6  # oracle: spec §4`)
so they do not drift with the code. A loop over a glob or registry asserts how many items it found.

## 4. Mutants

A mutant measures the suite's **sensitivity**, not the oracle's correctness: if the oracle is tied
to the bug, mutants get killed while the bug lives on.

- Mutate only within the diff, on a **copy** of the tree:
  `mutmut run --paths-to-mutate <files>`, `cargo mutants --in-diff <diff>`, `npx stryker run --mutate <files>`.
- Add 3–5 hand-written mutants of the defect class: flipped sign, `/10` instead of `/100`, off-by-one at
  a boundary, a removed branch. The new test must kill all of them. A timeout is not a kill.
- Each mutant's verdict is one of these classes:

| Class | Meaning | Action |
|---|---|---|
| `caught` | the test failed, and failed **on the rule being checked** | nothing |
| `uncaught` | behaviour changed, tests green | a hole: new test or an honest record |
| `inert` | the mutant does not change behaviour (equivalent, dead code) | explain; delete dead code |
| `masked_by_base` | data or another rule suppresses the mutant before the check | other input; excluded from recall |
| `out_of_contract` | the mutant is outside what the check promises to catch | record the boundary |

Recall is computed over live pairs (`caught + uncaught`); the other classes do not dilute it.
Compare equivalent mutants with comments stripped. A mutant set built from closed defect classes is a
good benchmark for a detector: its holes have names.

Full mutation runs are for things that judge, formulas, money and numeric semantics, and stage close.
A local edit of up to ~10 lines with a spec literal: 2–3 hand-written mutants (`SKILL.md`). UI, text: none.

## 5. Independent oracle

An oracle shares no code or algorithm with what it checks:
- a second engine (another library, an external calculator, a real DBMS instead of a mock);
- a literal from a spec, a standard, a domain law, or a hand calculation;
- a metamorphic relation (section 7);
- a known-good version or a human-labelled set.

Goldens, snapshots and parity with your own numbers prove **consistency**, not
correctness. Two implementations by the same author (or the same model) fail in the same places.
Example: if both implementations compute through the same numeric library, its error yields green parity;
only an external engine will see it.

Before shelving an oracle as "too expensive", measure its cost with one command.

## 6. Oracle literals

```python
assert discount(price=50, pct=20) == 40  # oracle: spec §3.2 "20% discount on 50 → 40"
```

- In tests of money, numbers and things that judge, the expected value carries `# oracle: <spec §|REQ-id|URL|
  domain law|measurement with command>`. In other tests it is optional.
- The implementation's formula must not appear in the expected value: it shifts together with the defect.
- A snapshot of current behaviour is marked `characterization`; it catches regressions but proves nothing.
- Emptiness probe: if the function returns a default (0, `[]`, `None`), the test must turn red.

## 7. Property-based and metamorphic testing

- Property strength: `no crash < type < invariant < idempotence < roundtrip / oracle`. Take the strongest.
- Derive the property from the spec, a schema or a domain law, not from your understanding of the code.
- Put constraints in the strategy, not in `assume()`. Check `pytest --hypothesis-show-statistics`:
  few passing examples or many discarded ones means the test is vacuous.
- Check the property against one hand-written mutant: if it passes on a broken implementation, it is a tautology.
- Triage a counterexample against the spec: `bug in code | wrong property (quote the spec) | ambiguity`
  (both readings with numbers). Never weaken the property "until green".
- Metamorphic relations give truth without knowing the answer: scaling, shifting, permuting the
  input, additivity, "feature off ≡ old behaviour" on every output row.

## 8. The checker is code under test too

A script that checks, measures or reconciles:
1. is first run on a known-good and a known-bad input;
2. prints how many objects it examined, and the pair "fired / not judged";
3. compares item by item, not in aggregate; thresholds are relative, not `abs < 1e-6` on billions;
4. a surprising result (zero mismatches, 100% agreement) is re-checked a second way.

Typical breakages: a `while read` loop with `ssh` inside swallowed stdin and checked one file; comparing
the wrong tree; a denominator other than the one in the label.

For every number used as proof, record **on what** and **by what** it was obtained, and what would give false
agreement: your own fixtures or corpus, the same formula as in the code, someone else's denominator. Coverage
of your own artifacts is a regression ratchet, not an argument for correctness.

Compare the hash of numeric output after canonicalisation: keys sorted, ids and timestamps removed,
floats rounded above the noise. Otherwise "DIFFER" means noise, not a defect.

## 9. Do not tune the producer to the number

Expected and actual disagree: use an oracle to find out who is wrong.
- The expectation is wrong: change the value in a separate `test:` commit with its source. Contract: the brief, or,
  without a coordinator, the user's request plus a line written before the edit (`oracle-protection.md` §1).
- The code is wrong: fix the root on the defect's path.
- Unclear: `SPEC_CONFLICT(test, source)` with the numbers for both readings.

Never twist code, parameters, rounding or coefficients until the result matches
the expected value. A match obtained by tuning is a false green: truthfulness matters more than
untouched tests.
