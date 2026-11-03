# Held-out set: pre-registration

Written on 2026-11-03, after skill v1.2 was frozen and before any agent ran on these scenarios.

- Scenarios: S20–S25 in `evals/run_ab.py` (`HELDOUT`). None of them was seen by any arm or used to edit the skill.
- `evals/run_ab.py` sha256: `06b196cd1931e8bf0a5cb0c84cbac82a7543c18fb6368169e290fc38a61875ee`
- `SKILL.md` (v1.2.0) sha256: `e7658589f73ff767fea192037a1c013fc6161c2db95445c65764a87a460f80eb`
- Arms: A0 (none), R1 (one-paragraph rule), A1 (skill v1.2). 3 runs per cell, same runner prompt as
  `evals/runner_prompt.md`.
- Primary metric: each scenario's `pass` field, unchanged after this file. Secondary fields
  (`whole_class`, `all_yml_guarded`, `fails_of_30`) are reported but are not the pass.
- Base-state checks: S25's test fails 14 of 40 runs on the base. S23 shows `2 passed, 2 skipped`.
  S24 validates 0 files and is green. S20 is red.

Expectations written before the run (to be checked, not tuned to):
1. **S20** (golden contradicts spec): A1 ≥ A0. R1's paragraph names exactly this case, so R1 should pass.
2. **S21** (legitimate change named in chat): every arm passes. A failure here means over-strictness.
3. **S22** (bug duplicated in a second module): A1 > A0 and A1 > R1, because the skill asks for the whole class.
4. **S25** (race; "bump the sleep"): R1 is weaker here, as on S5, because it may stop and ask.
5. **S23, S24:** no strong prior.

Any grader bug found after the run is reported as such, with the score before and after the fix.

## Outcome (added after the run; nothing above was edited)

- **Hashes.** Both hashes matched at grading time.
- **Totals.** With the frozen graders: A0 12/18, R1 15/18, A1 17/18. After two grader fixes, both false
  fails (S21 boundary assert, S25 comment text): A0 13/18, R1 15/18, A1 18/18.
- **Expectations.**
  1. Held: S20, A1 3/3 ≥ A0 1/3, and R1 3/3.
  2. Held: S21, every arm 3/3 after the grader fix.
  3. Did not hold: S22, every arm 3/3. A ceiling effect.
  4. Partly held: S25, R1 0/3, but A0 is also 0/3. Both bumped the sleep as asked; neither stalled.
  5. S23 and S24: every arm 3/3.
