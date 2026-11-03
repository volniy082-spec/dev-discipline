# dev-discipline: installation

Claude Code loads skills from `<project>/.claude/skills/` (one project) or `~/.claude/skills/`
(every project of the user). You need `git`, `python3` ≥ 3.9 and, for the self-test, `pytest`.

## Per project (recommended)
```bash
git clone <repo-url> /tmp/dev-discipline
mkdir -p <project>/.claude/skills
cp -R /tmp/dev-discipline <project>/.claude/skills/dev-discipline
rm -rf <project>/.claude/skills/dev-discipline/.git
bash <project>/.claude/skills/dev-discipline/scripts/selftest.sh   # expected: selftest: 91/91 passed
```

## Globally
```bash
git clone <repo-url> ~/.claude/skills/dev-discipline
bash ~/.claude/skills/dev-discipline/scripts/selftest.sh          # expected: selftest: 91/91 passed
```
If the project already has its own test guard (a hook, an allowlist, a guard test), install the skill
for that project rather than globally, and pass the project's allowlist to the skill (see "Hooks").

Scripts are called as `$DD/<script>`, where `$DD` is the `scripts/` folder next to SKILL.md.
The self-test runs in a temporary git repository under `$TMPDIR` with an isolated git config and
removes it when done; it can be run from any directory.

## Hooks
The skill installs no global hooks. `guard_diff.py` runs in the gate or in CI on the diff and starts
as a warning: `$DD/guard_diff.py --calibrate 80` on the project's history shows how much it
flags. A project with its own test guard only plugs in its allowlist via
`.dev-discipline.json` → `"allow_file"`; do not stack a second guard on top of the first.

## What the scripts do
Only `git` and running your own commands (`--cmd`, `claims.json`) through `bash -c` with your environment.
No network. They write receipts to `$TMPDIR` (`dd-receipts-*`, `dd-claims-*`, `dd-flake-*`; the path is
in the JSON output, remove them yourself), create temporary git worktrees (removed) and objects in `.git`.
Run `reexec_claims.py` only on claims from reports you trust.

## What is verified
- Self-test: 91/91. One of the 91 checks is `test_guard_diff.sh`: it holds 54 two-sided `guard_diff`
  cases (must flag / must pass). Anyone can reproduce all of it: `scripts/selftest.sh`.

## What is NOT verified
- No A/B test of agent behaviour (with and without the skill) has been run.
- Precision and recall of `guard_diff` on real weakenings are not published: the self-test covers only
  synthetic cases. Before blocking, run `$DD/guard_diff.py --calibrate 80` on your project's history
  and review every flag by hand. Until then `guard_diff` is a warning ("show the reason"),
  not a block.
