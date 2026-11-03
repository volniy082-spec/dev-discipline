# dev-discipline: installation

Claude Code loads skills from `<project>/.claude/skills/` (one project) or `~/.claude/skills/`
(every project of the user). You need `git`, `python3` ≥ 3.9 and, for the self-test, `pytest`.

## As a Claude Code plugin
```bash
claude plugin marketplace add volniy082-spec/dev-discipline
claude plugin install dev-discipline@dev-discipline
```
The repository is both the marketplace and the plugin (`.claude-plugin/`); the root `SKILL.md` loads as the
plugin's single skill, and the scripts ship with it. `claude plugin marketplace update dev-discipline` pulls
a new version. The agent role files in `templates/agents/` are templates: they are not registered as plugin
agents; copy the ones you use into `.claude/agents/`.

## With the skills CLI (any agent)
```bash
npx skills add volniy082-spec/dev-discipline        # add -g for all projects
```
It detects installed agents (Claude Code, Cursor, Codex and others) and asks where to install.

## By hand, per project (recommended for a project with its own test guard)
```bash
git clone https://github.com/volniy082-spec/dev-discipline /tmp/dev-discipline
mkdir -p <project>/.claude/skills
cp -R /tmp/dev-discipline <project>/.claude/skills/dev-discipline
rm -rf <project>/.claude/skills/dev-discipline/.git
bash <project>/.claude/skills/dev-discipline/scripts/selftest.sh   # expected: selftest: 91/91 passed
```

## Globally
```bash
git clone https://github.com/volniy082-spec/dev-discipline ~/.claude/skills/dev-discipline
bash ~/.claude/skills/dev-discipline/scripts/selftest.sh          # expected: selftest: 91/91 passed
```
If the project already has its own test guard (a hook, an allowlist, a guard test), install the skill
for that project rather than globally, and pass the project's allowlist to the skill (see "Hooks").

Scripts are called as `$DD/<script>`, where `$DD` is the `scripts/` folder next to SKILL.md.
The self-test runs in a temporary git repository under `$TMPDIR` with an isolated git config and
removes it when done; it can be run from any directory.

## Other agents: Cursor, Codex

`SKILL.md` follows the open Agent Skills format (a folder with `SKILL.md`, `name` and `description` in the
frontmatter, optional `scripts/` and `references/`). Install it under a folder named `dev-discipline`: Cursor
requires the folder name to match `name`.

| Agent | Project | User (all projects) |
|---|---|---|
| Claude Code | `.claude/skills/dev-discipline/` | `~/.claude/skills/dev-discipline/` |
| Cursor | `.cursor/skills/` or `.agents/skills/` (also reads `.claude/skills/`) | `~/.cursor/skills/` or `~/.agents/skills/` |
| Codex | `.agents/skills/` (from the working directory up to the repo root) | `~/.agents/skills/` |

One copy in `<project>/.agents/skills/dev-discipline/` serves both Cursor and Codex:

```bash
git clone https://github.com/volniy082-spec/dev-discipline /tmp/dev-discipline
mkdir -p <project>/.agents/skills
cp -R /tmp/dev-discipline <project>/.agents/skills/dev-discipline
rm -rf <project>/.agents/skills/dev-discipline/.git
bash <project>/.agents/skills/dev-discipline/scripts/selftest.sh
```

Paths as documented by Cursor (cursor.com/docs/skills) and Codex (Build skills) in 2026-11. Check them if a
tool changes its layout. Cursor syncs only `~/.cursor/skills/` to its Cloud Agents.

What carries over and what does not:
- **Works in any agent:** the core `SKILL.md`, `references/`, the brief and report templates, and all scripts
  (plain Python and bash, no agent API).
- **Claude Code only:** `templates/agents/*.md`. Their frontmatter (`model`, `isolation: worktree`,
  `disallowedTools`, `maxTurns`) is the Claude Code subagent format. In other agents, set up the roles by
  their own means and keep the rules: the writer works in its own worktree, judges cannot edit, and the reviewer
  runs on a different model from the writer.
- **Claude Code examples:** parts of `references/delegation.md` (`SendMessage`, built-in Explore/Plan,
  `CLAUDE_CODE_SUBAGENT_MODEL`, the transcript path). The principles hold; the commands differ.
- **Not measured elsewhere:** the A/B results in `evals/` come from one model (Claude Opus 5.5). The effect in
  other agents and models is unknown. `evals/run_ab.py prepare` + `grade` work with any runner.

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
- The A/B evaluation of agent behaviour (`evals/`) covers one model and small synthetic scenarios. It
  shows direction and failure modes, not statistical significance.
- Precision and recall of `guard_diff` on real weakenings are not published: the self-test covers only
  synthetic cases. Before blocking, run `$DD/guard_diff.py --calibrate 80` on your project's history
  and review every flag by hand. Until then `guard_diff` is a warning ("show the reason"),
  not a block.
