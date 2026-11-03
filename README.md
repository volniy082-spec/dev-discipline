# dev-discipline

An agent skill (written for [Claude Code](https://docs.claude.com/en/docs/claude-code); the core and scripts
also work in Cursor and Codex, see `INSTALL.md`) that makes an AI coding agent
(or a human) prove that a change is done, instead of declaring it done. It ships a short operating
procedure (`SKILL.md`), reference notes, agent role templates, and a set of small, stdlib-only
scripts that check the proof mechanically.

Each rule is backed either by published research on testing and agent reliability or by an
explicitly labelled engineering heuristic. See `references/evidence.md` for the sources and for
what is not measured.

**Author:** Andrey Zheltukhin

## Philosophy

- **"Done" is an external signal you did not tune.** A green run you shaped yourself is not proof.
- **A test proves a fix only if it is red on the parent by an assertion**, green on the fix, and red
  again when the fix is reverted. ImportError, skip, or "0 tests" are NOT_PROVEN, not red.
- **The oracle shares no code with what it judges.** Goldens and parity with your own numbers show
  consistency, not correctness.
- **Judge the resulting diff, not the editing tool.** Weakened tests are caught at the gate,
  whatever channel changed them.
- **A rule in text names a failure class; a check in the gate stops it.** The second time a class
  appears, the check goes into the gate in the same commit.

## Language

Everything is in English: `SKILL.md`, `INSTALL.md`, `references/`, `templates/` and script help. The agent can
still answer in any language. There is one copy of the rules on purpose: a translation drifts from the original.
The core `SKILL.md` is about 60 lines; details live in `references/`.

## Layout

```
SKILL.md                 the skill core, ~60 lines (loaded by Claude Code)
INSTALL.md               install notes
references/              details per topic: debugging, proofs and oracles, oracle protection,
                         gate integrity, refactoring and flaky tests, delegation, release,
                         process ledger, evidence
templates/               brief / report / state templates, pinned.py, expected_failures.py
templates/agents/        Claude Code subagent role files (writer, reviewer, auditor, closer)
scripts/                 prove_fix, guard_diff, reexec_claims, flake_check, gate_meta,
                         check_report, tree_hash, selftest
evals/                   A/B evaluation: 10 synthetic scenarios, graders, published results
```

The agent templates use Claude Code subagent frontmatter (`model:`, `isolation:`,
`disallowedTools:`) as of 2026; check the current Claude Code documentation if a field changes.

## Install

Per project (recommended):

```bash
git clone https://github.com/volniy082-spec/dev-discipline /tmp/dev-discipline
mkdir -p <project>/.claude/skills
cp -R /tmp/dev-discipline <project>/.claude/skills/dev-discipline
rm -rf <project>/.claude/skills/dev-discipline/.git
```

Globally, for every project of the user:

```bash
git clone https://github.com/volniy082-spec/dev-discipline ~/.claude/skills/dev-discipline
```

Then run the self-test (it works in a throwaway repo under `$TMPDIR` with an isolated git config):

```bash
bash <skill dir>/scripts/selftest.sh      # expected last line: selftest: 91/91 passed
```

Cursor and Codex: see "Other agents" in `INSTALL.md` (one copy in `.agents/skills/` serves both).

No hooks are installed. `guard_diff.py` is meant to run in the gate or CI, as a warning first.
A project that already has its own test guard passes its allowlist via `.dev-discipline.json`
→ `"allow_file"`.

## Requirements

- `git`
- `python3` >= 3.9 (scripts use the standard library only)
- `pytest` for the self-test

## Exit codes

Every script follows the same convention and prints JSON (except `tree_hash.sh`, which prints a hash):

| Code | Meaning |
|---|---|
| 0 | PASS |
| 1 | FAIL |
| 2 | NOT_PROVEN (could not judge: environment error, skip, timeout, missing binary, crash) |

## Quick examples

`DD` is the `scripts/` directory of the skill.

Prove that a new test really proves a fix (red on parent by assert, green on fix, red after revert):

```bash
$DD/prove_fix.py --base origin/main --fix WORKTREE \
  --cmd "python3 -m pytest -q tests/test_tax.py::test_rate" --full-cmd "python3 -m pytest -q"
```

Check the diff against the base for weakened or ungranted test / CI changes:

```bash
$DD/guard_diff.py --base origin/main                      # JSON; 0 PASS, 1 FAIL, 2 NOT_PROVEN
$DD/guard_diff.py --calibrate 80                          # replay the last 80 commits first
```

Run `--calibrate` on your own history and judge every flag by hand before making `guard_diff` block
anything; start it as an advisory check. The self-test covers it with synthetic must-flag and
must-pass cases; precision and recall on real-world weakenings are not published.

Re-run the commands behind the numbers in an agent's report:

```bash
cat > claims.json <<'EOF'
[{"name": "tests passed", "cmd": "python3 -m pytest -q", "extract": "(\\d+) passed", "reported": "42"}]
EOF
$DD/reexec_claims.py claims.json --repo path/to/worktree
```

**Warning:** `reexec_claims.py`, `prove_fix.py` and `flake_check.py` run the given commands through
`bash -c` with your environment. Only run claims from reports you trust, and read each command first.
The scripts make no network calls; they write receipts to `$TMPDIR` and create temporary git
worktrees and objects in `.git`.

## Does it help? (A/B results)

`evals/` compares three arms on 10 synthetic scenarios, 3 runs each (Claude Opus 5.5, 2026-11-02): no
instruction, a one-paragraph "don't weaken tests, verify" rule, and this skill. Each arm passed 24/30 with
skill v1.1, and each failed different scenarios:
- **The rule** kept agents from editing tests. But on a flaky test it stopped to ask permission and left
  CI flaky in 3 of 3 runs.
- **No instruction and skill v1.1** changed a test that contradicted the spec to match the spec, and said
  so openly.

v1.2 tightens the contract rule and passes 30/30. That run is in-sample, because the rule was rewritten after
those failures. On six new scenarios, frozen before any run, the results were: skill v1.2 18/18, the rule
15/18, no instruction 13/18. The skill costs about 3x the output tokens on these small tasks. These runs measure the
single-agent core. The multi-agent orchestration material in `references/delegation.md` (v1.3) comes from one
project's practice and is not measured. Method, per-scenario tables,
cost and limitations are in [`evals/README.md`](evals/README.md).

## License

MIT © 2026 Andrey Zheltukhin, see [LICENSE](LICENSE).

Not affiliated with or endorsed by Anthropic. Claude and Claude Code are trademarks of Anthropic, PBC.
GitHub, pytest, Jest, Vitest and other names are trademarks of their respective owners and are used only
to describe compatibility.
