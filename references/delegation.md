# Delegation: roles, brief, report, acceptance

The full role pipeline is expensive: use it for a stage where a silent error costs a lot. A normal PR is one
writer, the gate and re-executed numbers. Rationale: `evidence.md`.

## 0. Ceremony by risk, one cycle per item

The waste in a role pipeline is rarely in the checks themselves. It is in running **the same** checks for a
label change and for a new money flow, and in splitting one item into several full cycles (a measure cycle,
then a design cycle, then a code cycle, each with its own brief, review and commit).

**One cycle per item.** Measure → decision → code → invariant → gate go in one brief, one worktree, one
result document. The orchestrator closes forks in the brief with numbers from the measure, not the writer.
A separate measure-only cycle (with its own commit) is worth it only when the question is "should we build this
at all, and what exactly". This applies when demand is unknown or nothing yet carries the feature. A separate
design cycle (design, then review, before any code) is worth it only on the owner's request, or when the
change rewrites the failure matrix on three or more axes. Every brief stays short (≤ 10 lines), and the
orchestrator fills agent prompts and path lists from templates or scripts, not by hand.

| Level | Criterion (any of) | Cycle | Checks |
|---|---|---|---|
| **S** — surface | text, labels, i18n, docs; no computed number changes | one writer, one cycle | full gate; auditor facts 1, 3, 4, 5; no review |
| **M** — mechanism with an oracle | an expected number exists (spec, owner, measure); fewer than three modules; no new domain entity | one cycle as above | auditor, all seven facts; cross-model review when §6 "When" applies, with §6 sampling |
| **L** — structure | a new domain entity or failure matrix; three or more modules or several layers; fixed points or cycles; evaluator semantics | as M + a **non-blocking decision check** (§6) | auditor ∥ cross-model code review, always |

The orchestrator picks the level in the brief. When in doubt, take the higher one. Keep the gate itself
identical across levels: it is machine time, not tokens. The table assumes an auditor. Without one, the
orchestrator re-executes the same facts itself (§5).

## 1. Roles by capability, not by persona

| Role | Writes | Does |
|---|---|---|
| orchestrator | brief, commit | picks the level, writes the brief (the brief is the design decision), accepts on artifacts, triages findings, commits and deploys by script |
| writer | code and the result document in its own worktree | the whole cycle: measure → decision → code → invariant → parent-red → gate → result document |
| auditor | nothing | mechanical acceptance: a short list of re-executable facts, including the re-measure; returns a table |
| reviewer | nothing | hunts defects on a frozen snapshot, findings with repro; also the non-blocking decision check for L |
| scout (opt.) | nothing | fan-out reading for the brief when the orchestrator needs facts from many files |
| closer (opt., off by default) | only the task folder and a draft commit | see below |

- **One writer** in an isolated worktree (`isolation: worktree`). It does not commit.
- **Judges only read, enforced by tools** (`disallowedTools: Edit, Write, NotebookEdit`): a judge that can edit fixes what it judges.
- **The closer is off by default.** In practice it repeated the auditor's and the writer's re-measures and
  otherwise wrote documents. Give the re-measure to the auditor (one `MEASURE` command, numbers before and after
  must match the result document), the closing text to the writer (§4), and metrics rows to a script. Keep
  `templates/agents/closer.md` only if your canon (plan, log, registry) is too large for the writer's budget.
  The orchestrator commits, with explicit paths.
- **The orchestrator accepts on artifacts:** the auditor's table, the reviewer's verdict, the gate line. It does
  not re-read the diff "to form an opinion": that burns context and replaces the check.
- Templates: `templates/agents/*.md` → the project's `.claude/agents/`. Do not create a role you do not use.

## 2. Model per role: pinned and verified in the transcript

Two rules decide the assignment. The reviewer's model differs from the writer's, because errors within one model
are correlated (`evidence.md`, Delegation). And the most expensive context does not write code.

| Role | Model class | Why | Example (Claude family, 2026-11) |
|---|---|---|---|
| orchestrator | the strongest model available | the brief is the design decision; it judges findings and accepts; its context is the costliest, so it does not write code, read whole diffs or hand-write long documents | Fable |
| writer | a strong coding model | one full cycle needs depth and many turns | Opus |
| reviewer | a different model from the writer, as strong as you can afford; ideally another family | correlated errors; a same-model reviewer tends to miss what the writer missed | a fresh Fable agent reviewing Opus code (not the orchestrator's own context); or another vendor's CLI |
| auditor | a cheap model | facts are mechanical: command → output → comparison | Sonnet |
| scout | a cheap model | reading many files for the brief | Sonnet (built-in Explore pinned to it) |
| design draft (opt.) | the writer's model | only for a separate design cycle (§0) | Opus (Plan) |

- **Use the most expensive model for code only as a reviewer.** Then its cost is paid once per change it
  judges, not per turn of writing.
- **Only one model available:** see §6, "Only one model". If the writer and reviewer must share a family, use
  different tiers and a fresh context, and record `cross_model_review: same_family` next to the review verdict.
- Names and prices change. Re-check the mapping when a model generation changes: the rule is the
  constraint, not the names.

A subagent without `model:` inherits the parent's model, often the most expensive one. So do built-in Plan, Explore.

- `model:` in every role file; call agents without a model parameter. Override built-ins with a file of the
  same `name` in `.claude/agents/` or with `CLAUDE_CODE_SUBAGENT_MODEL` in `settings.json`.
- Check which model actually ran in the transcript, not the config — an alias can resolve elsewhere:

```bash
grep -ho '"model":"[^"]*"' ~/.claude/projects/<project>/<session>/subagents/agent-<id>.jsonl | sort | uniq -c
```

## 3. The brief is a file with keys

Template `templates/brief.md`. The writer reads only the brief and its links. Not in the brief, not in the task.

- `GOAL` — an observable result. `MEASURE` — one command, before and after. `HYPOTHESIS` — "test it,
  do not confirm it": refutation is a valid outcome.
- `PERIMETER` / `EXCLUDED` — which paths may change and which may not.
- `CONTRACT` — the exact protected paths (tests, snapshots, pins) that may change, and frozen
  signatures. Written before work starts (`oracle-protection.md`).
- `EXIT` — `DONE | BLOCKED(reason) | SPEC_CONFLICT(test, source) | IMPOSSIBLE | NOT_REPRODUCED`.
  An honest non-done exit is a success. `DD` — path to the skill's `scripts/`: `$DD` in role files.
- The brief is about the task. Standing rules (working practices, answer format) live in the role file.

## 4. The report is a schema a script checks

Template `templates/report.md`. `check_report.py <report>` checks the form (exit 0/1/2); re-execution checks the truth.

- Closed vocabularies: `EXIT`, `HYPOTHESIS confirmed|refuted|not_tested`, criteria `PASS|FAIL|NOT_PROVEN`.
  A number in criteria and witnesses carries its command on the same line; in free text a number proves nothing.
- `SHA` — the base. `TREE` — `$DD/tree_hash.sh <worktree>` right after the gate, **before** writing the report:
  the report is not part of the judged tree. Bare `git write-tree` gives the index tree (usually HEAD), not the judged one.
- Witnesses: at least two, `{cmd, expected, fact, source}`. `expected` is written before the run,
  `fact` is the verbatim output, `source` is `path:line` of the built code.
- The writer's answer to the orchestrator is two lines: the report path and the `EXIT` line.
- If the harness rejects writing the report, the report comes as text and the orchestrator puts it in place.
- **One result document per item.** The writer adds a `## CLOSING` section to the report: five lines for the
  task folder's README, follow-up items with return conditions, the plan line, the commit message with
  explicit paths, and a draft metrics row. There is no separate closing note, review summary or long README
  section. A reviewer's verdict, if any, is stored next to it verbatim (`<task>_review_1.md`).

## 5. Acceptance: every number re-executed

The minimum for any delegation: the orchestrator re-executes the numbers in the report. A subagent's number
is model output until an instrument repeats it.

```bash
# claims.json: [{"name": "passed", "cmd": "pytest -q", "extract": "(\\d+) passed", "reported": "42"}]
$DD/reexec_claims.py claims.json --repo <writer worktree>    # via bash -c; --repo is the writer's tree
```

**Warning:** commands from `claims.json` run through `bash -c` with your environment (tokens and keys in env
stay) — run only claims from reports you trust; read every `cmd` before running it.

**Mechanical auditor** (optional; pays off on heavy projects with a long gate). Cheap model, read-only.
The table `fact | PASS/FAIL/NOT_PROVEN | receipt` comes first, everything else after:

1. Gate green on the stated `TREE`; the log names the right worktree; passed count not below the previous one.
2. The new test is red on the parent **by an assertion**:
   `$DD/prove_fix.py --repo <worktree> --base <SHA> --fix WORKTREE --cmd "<test>"`. ImportError is NOT_PROVEN.
3. Changed paths are inside `PERIMETER`; `HEAD == SHA`; the report hides no paths.
4. Protected paths changed only per `CONTRACT`. No `allow_file` in the config — write the `CONTRACT EDIT=` paths
   to a temp file outside the worktree (one glob per line, `WEAKEN-OK: <path> <reason>` for weakenings the
   contract allows), then `$DD/guard_diff.py --repo <worktree> --base <SHA> --allow <file>`. A test moved
   to another file with an edit reads as deleted — review that flag by hand.
5. The report passes `check_report.py`.
6. k witnesses re-executed verbatim. Which ones is picked by a seed from the report hash, so the writer cannot guess:

```bash
python3 -c "import hashlib,random,sys;b=open(sys.argv[1],'rb').read();r=random.Random(hashlib.sha256(b).hexdigest());print(sorted(r.sample(range(1,int(sys.argv[2])+1),int(sys.argv[3]))))" report.md 5 2
```

7. Re-measure: the brief's `MEASURE` command run by the auditor on the writer's tree; the numbers must equal the
   report's `MEASURE.after`. This replaces a separate closer re-measure.

Any FAIL rejects the report unread. The auditor catches fitted facts (a stale run, "before" instead of
"after", edits outside the contract), not semantic defects: that is the reviewer's job.

## 6. Reviewer: a different model, a snapshot, findings with repro

**When.** By change class, not always: what judges (test oracle, detector, validator, threshold, gate rule),
money and numeric formulas and semantics, migrations, auth, closing a stage. A local edit of ~10 lines
with a spec literal needs no reviewer: `prove_fix.py`, 2–3 hand-written mutants and one run on an input you
did not use while working. An ordinary edit: the same model in a clean context, or no one.

- **A different model.** A clean context removes anchoring, not correlated errors: repeated review rounds
  by the same model tend to miss what the first one missed.
- **A frozen snapshot.** Input: brief, worktree, `SHA`, `TREE`. The reviewer looks at `SHA..TREE`.
  It does not read the writer's report, review history or memory of this task before its verdict.
- **Findings only.** The reviewer does not edit code. Mutations only on a copy: a shared tree spoils the snapshot.
- **Finding = code quote + repro command + expectation + fact.** No repro — `NOT_CONFIRMED`, not acted on.
  A wrong finding with a repro is safe: it simply does not reproduce.

**Triage:**
- `A` — blocks acceptance. Reject if there is at least one A.
- `B` — moves a metric but does not block. Into the plan, with a condition for returning to it.
- `C` — taste. At most three, ignored.

**Stop** after the first round with A = 0, at most two rounds: repeated rounds raise the share of false findings.

**Sampling by telemetry.** L is always reviewed. For M with a numeric core: after six consecutive reviews with
A = 0, review every second M change. The first A finding returns review to every change. Relax control only
on measured quiet, and restore it at the first signal. Record review outcomes (A count per review) so the rule
has data.

**Non-blocking decision check (level L).** Before coding, the writer writes a decision note (what is built,
where it reads its inputs, failure behaviour; 5–10 lines) to `<task>_decision.md` in the task folder, **outside
the worktree**. Then it goes on to code without waiting. Keeping the note outside the worktree keeps it out of
`TREE`, so the code reviewer's snapshot does not include the writer's own account. The orchestrator starts a
reviewer on the note in parallel, with a small budget (tens of thousands of tokens). An A finding goes to the
writer as a message. The goal is to catch a wrong decision before the gate, not to stop the writer.

**Only one model.** No independence — compensate with mechanics: a fresh context without the writer's report,
mutants on a copy against the new test or check, every number re-executed, `prove_fix.py`.
In the report: `cross_model_review: not_run (single model)` — this is not "review clean". If a `codex`
or `gemini` CLI is available, the reviewer calls it through Bash on the same snapshot, findings only.

## 7. Parallelism: one semantics, one writer

- Parallel only on disjoint files **and** with no shared index (generated address maps, `file:line`,
  truth tables). A feature that runs through the core and the surfaces gets one writer.
- Each parallel writer has its own worktree and frozen contract. Merge one at a time, full gate after
  each. Shared indexes are regenerated by a single executor after merging.
- At most two writers at a time, on perimeters declared in their briefs. A third only while one of the two is
  waiting on the gate.
- A heavy gate runs one at a time per machine (check that no other run is going before starting). No edits after the gate:
  the tree under the gate is the tree in the report. Version bumps and merge conflicts in shared files are the
  orchestrator's: a copy step that would overwrite prints a conflict instead.

## 8. State and continuation

A long task (more than one turn budget, or background jobs) keeps a state file from the first step
(`templates/state.md`): step, status, artifact, decisions, what is left, background jobs.

- **Turn limit.** Continue the same agent (SendMessage) from step N per the state file, not from scratch.
  A continuation costs a context re-warm and an orchestrator turn, so the brief asks the writer to batch
  searches and runs into single calls, and the turn limit is set for a whole cycle, not a fragment.
- **Session lost.** No transcript — a fresh agent on the same worktree plus the state file.
- **After any restart** check background jobs first (`pgrep -fl <gate>`, log tail):
  a restart kills background shells. A live background job wakes the agent itself — do not duplicate it.
- **Task larger than one turn budget** — split it before launch: core first, then surfaces.
- **Checklist roles** (auditor, closer) output the table first, or the limit hits before it.

## 9. Other live sessions in the same repo

Another session or a human may be working in the repo. Their tree is not yours.

- Read-only by default (`git show`, `git log`, `cat`, `grep`). Experiments and "before" measurements go
  on a copy: your own worktree (if allowed) or `git -C <repo> archive <sha> | tar -x -C "$(mktemp -d)"`.
- Never `git stash`, `checkout`, `reset --hard` in a live tree: it breaks someone else's work.
  Someone else's uncommitted hunk is taken out and put back surgically (`git add -p`).
- Every command names its tree: `git -C /abs/path`, an absolute path to the script.
- Do not edit a tree while the gate or a reviewer is reading it. Deploy one at a time, with no one else's WIP in the tree.
