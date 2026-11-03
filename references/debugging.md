# Debugging and the stage loop

Details for steps 1–2 of the loop in `SKILL.md`. A hypothesis without a red signal is guessing. Rationale: `evidence.md`.

## 1. Measure before editing

One command. Save its output to a file and compare it before and after. The same command, unchanged,
becomes the re-measurement at close; better still if someone other than the writer runs it.

```bash
python3 tools/measure_x.py > /tmp/measure_before.txt; shasum -a 256 /tmp/measure_before.txt
```

- The measurement is deterministic: two runs in a row give the same hash. If not, make it deterministic
  first (seed, clock, network, ordering — `refactor-flaky.md`).
- The expectation ("after the fix it will be N") is written down before the run. The input is real (corpus,
  the user's case, prod read-only), not your own fixtures.

Feedback loop, cheapest first:
1. An existing test, narrowly selected: `pytest -q path::test -x`.
2. A new failing test on the minimal input from the bug.
3. A repro script: input, call, compare with the expected value from the spec, `exit 1` on mismatch.
4. A run over the corpus that counts affected cases: you know the defect's scale before designing.
5. A differential run: two versions or two builds on the same input.
6. Logs tagged `[DBG-<id>]` (removed via `rg -l DBG-<id>`); for UI, Playwright with DOM assertions.

Minimise the input (`hypothesis`, `shrinkray`, ddmin) and check that the same assert still fails.

## 2. Scope from raw data

The work list is built by a script over the primary source: logs, audit JSON, DB rows, the list of
failing tests. Not a summary, not memory, not a subagent's report.

```bash
pytest -q -rf 2>&1 | rg '^FAILED' | sed 's/ - .*//' | sort > /tmp/failing.txt; wc -l /tmp/failing.txt
jq -r '.findings[] | .rule' audit.json | sort | uniq -c | sort -rn
```

Summaries compress classes: recounting from raw data can find several times more than is "known".
The script prints how many records it examined: "0 violations out of 0 examined" is not clean.

## 3. Inventory by script

Before planning, list what already exists in the area: tests, gate checks, validators, hooks, CI jobs.
Generate the list, do not recall it. An agent's memory is stale context, not an inventory.

```bash
rg -l '<module|function|term>' tests/ | sort
rg -n '<module>' .github/workflows/ gate.txt scripts/ 2>/dev/null
```

The plan is a delta over that output: "X and Y exist; I add Z because X does not catch <input>".

## 4. Class list (yokoten)

Fix the class, not the instance: every place sharing the same root.

1. Write a query (`rg`, `ast-grep`, `semgrep`) that **first finds the known instance**.
2. Generalise step by step. Triage every match: `same defect → fix` or `false → why`.
3. Stop when half or more of the matches are false.
4. The list is written down **before the first edit**. The report reconciles each item: `fixed | left (reason)`.
5. The test covers the class (parametrised over the found instances), not just the ticket's example.
6. When the class shows up a second time, the query goes into lint or the gate in the same commit.

## 5. Delivery path

Name the path by which the bad output reached the user: input → functions → output. Fix and test
**that** path. A neighbouring path (a template instead of the real build, dev config instead of prod config,
a unit instead of the built artifact) does not count.

- A guard or detector on top of the defect is not a fix. The report names the state plainly:
  "guard added, root alive", "fixed off the defect's path".
- An incident can have several roots: look for every path. On "are you sure?", retrace the path;
  do not just rerun the same tests.

## 6. Consumer

For every new mechanism (check, field, flag, report), name its runtime consumer:
who calls it or reads it.

```bash
rg -n '<new_function>\(' --glob '!tests/**'
```

Zero callers outside tests means "mechanism without a consumer", not `DONE`; no consumer in the plan either — do not build it.

## 7. Regressions: bisect

A regression starts with `git bisect run`, not with reading the diff. Bisect runs in a **separate worktree**:
no `stash` and no `checkout` in the live tree, where another session or the gate may be running.

```bash
git worktree add /tmp/bis <bad> && cd /tmp/bis
git bisect start <bad> <good> && git bisect run ./repro.sh   # 0 good, 1 bad, 125 skip
git bisect reset && cd - && git worktree remove /tmp/bis
```

A commit that does not build is 125, not 1. The first bad commit goes into the log and the retry packet. A pin
or threshold may be lowered only after bisect proves the search broke, not that code was removed.

## 8. Hypothesis log

```
H1 | hypothesis | prediction: what we will see if true | command | observed | confirmed/refuted
```

- Before the first fix: 3–5 ranked, falsifiable hypotheses.
- Only an observation predicted in advance confirms. "The symptom went away" confirms nothing.
- A refuted hypothesis is a result: it stays in the log, the commit and the retry packet.

## 9. Three attempts — a heuristic

An attempt is a fix you considered done that then failed the measurement or a test. After three
failures, change approach or context: the context is anchored on its own version. This is a heuristic, not a ban —
the threshold is not measured (`evidence.md`); a new hypothesis with a new measurement is already a different approach.

Options: change approach (another layer, another hypothesis, revisit the architecture) or hand the
task to a fresh context (subagent, new session, `/clear`) with a **packet of what was refuted**:

1. the task — one self-contained prompt with the goal and the measurement command;
2. the error signal verbatim: command, exit code, output tail;
3. where the error is, if known: `file:line`, first bad commit;
4. the hypothesis log, refuted ones included, with observations;
5. what was tried and why it failed — one line per attempt. Do not pass the previous patch in full:
   it anchors;
6. if the same failure repeats in the fresh context, change the approach or the model, not just the session.
The packet is written to a file (`retry_packet.md`) so it survives losing the session.

## 10. Design note for new semantics

A new entity, money or data flow, migration, or public contract: 5–10 lines first,
then code. A targeted fix from a repro needs no note: a contract line before the edit is enough (which tests
change and where the value comes from, `oracle-protection.md` §1). An edit of up to ~10 lines with a spec literal
takes the light path: `$DD/prove_fix.py`, 2–3 hand-written mutants and a run on an input not used while working.

```
What changes for the user: <one sentence>
Before/after on real input: <input> → was <N>, will be <M> (command: ...)
Single resolver: <where the definition lives; who consumes it>
Non-goals: <what we do not do>
Files: <written>; protected paths that change: <tests/snapshots under contract>
Tests in the gate: <which, what they catch>
Rollback: <how to revert>
```

- Before/after numbers are computed by a command on real input. The premise "the numbers will not change" is
  checked by a measurement before coding and by review of the note, not by the author's confidence.
- Reviewing the note: a reviewer on a different model, or a human if available; otherwise a fresh context
  given only the note and the code. A blocking finding means a new revision of the note,
  not "I'll fix it as I go".
