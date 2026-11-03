# Process ledger and incident registry (optional)

A module for long agentic programs with many iterations. In an ordinary repository with short PRs it is
overkill: the commit body as the evidence record is enough: measure before and after, the gate line, what is
not done; out-of-scope findings go into the plan with a return condition (`templates/agents/closer.md`, step 3).
If the ledger is not being filled in, delete it. An empty column is worse than a missing one.

## Change ledger: one row per change

A minimal CSV, filled in at close, not after the fact:

```
id,date,sha,kind,first_gate_green,gate_runs,red_causes,closed_by,reopened_by,cost
```

- `kind`: evaluator | money | migration | feature | docs.
- `red_causes`: defect | pin | ritual | env, so you can see what share of red gates is bookkeeping.
- `closed_by`: the command or file of the re-measurement. `reopened_by`: who found the change wrong later
  (re-measurement, audit, user); this column is the reason the ledger exists.
- `cost`: cycle time or tokens, **only if a tool actually measures them**. Otherwise there is no column.

## Three numbers, not a metrics system

For an orchestrated program, track three numbers per change, plus nothing that no decision depends on (Goodhart):
tokens per role, cycle hours, and A findings per review. Every five changes, revisit the ceremony levels and the
review-sampling rule (`delegation.md` §0, §6) against these numbers. Review is relaxed only by the §6 rule.
The gate and the auditor's facts are never relaxed on quiet: they are cheap and they guard against silent
failure. Keep the plan line ≤ 600 characters and the state or memory head ≤ 1,500 characters. Details live in
the result document.

## Process rules come only from your own history

- A process rule is introduced only if a retrospective run over **your own** ledger showed a class it would
  have caught. An imported "best practice" without that check is a hypothesis.
- Before a pilot, write down: the acceptance criterion (which metric must be no worse than which baseline),
  how you measure it, how to roll the rule back. The criterion is written by someone other than the one being
  evaluated, or fixed before the pilot.
- Every rule is either instrumented (a column or script sees it) or deleted.
- Small n and a model change midway: say it plainly, "not attributable", not "improved".

## Incident registry

One row per class, not per event. A repeat is appended to the same row with its date.

```
date | incident (what broke, how it was noticed) | root | mechanism+sha or rule-only (at risk)
```

An illustrative example of the format:

```
YYYY-MM-DD | sweep test green on an empty glob, noticed in review | loop without a count pin | pin() in the test, <sha>
YYYY-MM-DD, YYYY-MM-DD | test flickers on the real clock | time not frozen | rule-only (at risk)
```

- `rule-only (at risk)` is open debt. A second repeat of such a class: a mechanism in the gate in the same
  commit (SKILL.md: "When a class recurs, add the check in the same commit").
- A mechanism is given with its sha. Check it is still in the gate: `git grep` for its name in the gate script.

## Memory is stale context, not an inventory

Memory files, summaries and "state" describe the past. Before a plan and before quoting a number, re-check
with a script against the live tree: which tests exist, what is in the gate, what is in production. A memory
entry does not prove a mechanism exists or works.
