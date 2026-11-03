<!--
Brief for the writer. Task-specific only; standing rules live in the role file (templates/agents/writer.md).
Fill every {{…}}. The writer reads only this file and the files it points to.
-->
GOAL: {{observable result in one sentence: what the user or the gate gets differently}}
LEVEL: {{S | M | L}} — delegation.md §0; for L, first write {{task folder}}/<task>_decision.md (outside the worktree), then code without waiting
MEASURE: {{one measurement command, identical BEFORE and AFTER; where to put its output}}
HYPOTHESIS: {{root-cause hypothesis}} — test it, do not confirm it; refuting it is a valid outcome
SPEC: {{path:section of the spec or task}}; must hold: {{invariants that must not break}}
PERIMETER: {{globs of paths that may change}}; always: {{task folder}}, adding the test to the gate
EXCLUDED: {{protected paths outside the contract}}; git commit/push; deploy; {{other}}
CONTRACT: EDIT={{none | exact paths of tests, snapshots, pins that may change, and where the new value comes from; a weakening needs a line `WEAKEN-OK: <path> <reason>`}}; FROZEN={{none | signatures and formats}}
WITNESSES: ≥ 2 × {cmd · expected · fact · source}; PARENT_RED is required (or "n/a — reason"); needed: {{what the orchestrator wants to see}}
DD: {{absolute path to the scripts/ folder of the dev-discipline skill — $DD in commands}}
EXIT: DONE | BLOCKED(reason) | SPEC_CONFLICT(test, source) | IMPOSSIBLE | NOT_REPRODUCED — an honest non-done exit is a success; attempt {{1|2}} of 2
REPORT: {{report path}} per templates/report.md; reply with the report path and the EXIT line
