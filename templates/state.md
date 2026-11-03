<!--
State file of a long task: more than one turn budget, or background jobs. Created as the
first step, updated after every step.
It is what work resumes from: the same agent after a turn limit, or a fresh agent after a lost session.
-->
# STATE {{task id}}

BRIEF: {{absolute path of the brief}}
WORKTREE: {{absolute path}}
SHA: {{base}}
UPDATED: {{date time}}

## Steps
| # | step | status | artifact |
|---|---|---|---|
| 0 | measure before | {{todo|doing|done|failed}} | {{output path}} |
| 1 | {{step}} | {{status}} | {{path, command or sha}} |

## Decisions
- {{fork}}: chose {{what}}, because {{why}}; numbers for both readings: {{…}}; undo: {{how}}

## Refuted
- {{hypothesis}} | {{command}} | {{fact}}

## Background jobs
- {{what}} | `{{command}}` | log {{path}} | check: `pgrep -fl {{pattern}}`; `tail -n 3 {{log}}`

## Remaining
- {{next step to resume from}}
