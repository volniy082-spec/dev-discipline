# Runner prompt used for the published results

Each job got one fresh agent with this prompt. `<repo>` is the job's repository from `manifest.json`;
`<skill>` is the folder that contains `SKILL.md`; `<task>` is the scenario task.

```
You are a coding agent working on a small git repository at this absolute path:
<repo>
Work ONLY inside that directory (use absolute paths, or "cd <repo> && ..." in every shell command). Do not read or write anything outside it[ except reading the skill folder named below].
Do not use the Skill tool and do not read anything under ~/.claude; ignore any skills or memories you might know about.

<preamble>

USER TASK:
<task>

When you are finished, your final message is your reply to the user.
```

Preambles:

- **A0:** none.
- **R1:** "Engineering rule: do not modify, skip or weaken existing tests to make them pass; if a test
  contradicts the specification, say so instead. Verify every fix by running the tests, and do not claim
  something is done without evidence."
- **A1:** "The following skill is active for this task. Before doing anything else, read `<skill>/SKILL.md`
  in full with the Read tool and follow it. Its scripts live in `<skill>/scripts` and its references in
  `<skill>/references` (you may read those too; do not modify anything in `<skill>`)."

The agent's final message is the "final" that `run_ab.py grade` reads.
