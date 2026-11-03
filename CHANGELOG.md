# Changelog

## 1.3.0

- English only. The Russian translation is removed so there is a single copy of the rules.
- `INSTALL.md`: install paths for Cursor and Codex (`.agents/skills/`), and what is Claude Code only.
- Installable as a Claude Code plugin (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`) and
  with the skills CLI (`npx skills add volniy082-spec/dev-discipline`).

- `references/delegation.md`:
  - §0 ceremony levels S/M/L by risk;
  - one cycle per item (measure → decision → code → invariant → gate) instead of separate measure, design
    and code cycles;
  - §2 a model-per-role table: the reviewer's model differs from the writer's, and the most expensive context
    does not write code;
  - §6 review sampling by telemetry and a non-blocking decision check for level L;
  - §7 limits on parallel writers and gates;
  - §4 one result document with a `## CLOSING` section;
  - the closer is off by default, and its re-measure is now the auditor's fact 7.
- Templates:
  - `brief.md` has a `LEVEL` key;
  - `report.md` has a `## CLOSING` section;
  - `auditor.md` checks seven facts;
  - `reviewer.md` is pinned to a different model from the writer;
  - `closer.md` is marked optional.
- `references/release.md` §11: release in batches when proof is expensive.
- `references/process-ledger.md`: three numbers (tokens per role, cycle hours, A findings per review),
  reviewed every five changes.
- `scripts/selftest.sh`: one more case, a report with a `## CLOSING` section passes `check_report` (91 cases).
- `references/evidence.md`: the observation behind these changes, labelled [H]. The saving is expected, not
  measured.

## 1.2.0

- Contract rule tightened (`SKILL.md`, `references/oracle-protection.md`): when working alone, a test
  value changes only when the user's request names the change (new spec, ticket, value). "Make it pass" is
  not a contract. A test that contradicts the spec stays as it is, and the answer is `SPEC_CONFLICT`.
- New `evals/`: an A/B harness (`run_ab.py`) with 10 synthetic scenarios, deterministic graders and a
  selfcheck, plus published results for no instruction, a one-paragraph rule, skill v1.1 and skill v1.2.
- Held-out set S20–S25, pre-registered with hashes before any run. Results: skill v1.2 18/18, rule 15/18,
  no instruction 13/18.

## 1.1.0

- English is now the primary language: `SKILL.md`, `INSTALL.md`, `references/` and `templates/`
  (including the agent role files) are in English. Report and brief keys are unchanged.
- The core `SKILL.md` is shortened (to ~60 lines); the delegation and release details
  it dropped live in `references/delegation.md` and `references/release.md`.

## 1.0.0 — initial public release

- `SKILL.md` procedure, reference notes, brief/report/state templates and agent role templates.
- Scripts: `prove_fix`, `guard_diff`, `reexec_claims`, `flake_check`, `gate_meta`, `check_report`,
  `tree_hash`, with a two-sided self-test (`scripts/selftest.sh`, 90 cases).
