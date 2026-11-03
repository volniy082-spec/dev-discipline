# Evidence base
Labels: **[E]** external published research (listed at the end); **[H]** engineering heuristic — not measured here, apply with your own calibration.
Only [E] items carry numbers (plus one piece of arithmetic). [H] heuristics are reasoning and common practice; check them on your own data before making them hard rules.
## Mechanism, not text
- [E] METR (2025): asking "Please do not cheat" did not change the reward-hacking rate (80% → 80%, 20 runs on the Optimize LLM Foundry task); the authors call the effect of instructions "nearly negligible".
- [H] Heuristic: an error class closed by a mechanism (a gate check, a lock, a selftest) recurs less often than one closed only by the text of a rule. If it recurs, it needs a check, not another line in the instructions.
## Rigor by surface
- [H] Heuristic: the full loop is expensive; it pays off where a silent error costs a lot (what judges, money and numbers, migrations, auth). For prose, UI and prototypes, tests and a smoke are enough; for a small edit, `prove_fix.py` and a couple of hand-written mutants.
## 1. Measure before editing, scope from raw data
- [H] Heuristic: a summary compresses error classes; recounting from raw reports with a script usually finds more instances than are "known".
- [H] Heuristic: measure the cost of a check that keeps being postponed "because it is expensive" — eyeball estimates can be off by orders of magnitude.
- [H] Heuristic: code nobody calls passes any gate; an inventory of call sites is part of the measurement.
## 2. Root on the defect path; design before code
- [H] Heuristic: a short design before code (5–10 lines) and its review in another context are cheap compared with rework, especially for migrations and money or data flows.
- [H] Heuristic: a guard on top of the symptom leaves the root alive; the fix goes on the path the defect took.
## 3. The test is proven
- [H] Heuristic: a test that was never red on the defect may be vacuous; what reliably shows it is mutation or reverting the fix (`prove_fix.py`), not a rule in the text.
- [H] Heuristic: boundary conditions are what most often "survive" targeted tests; a hand-written mutant at the boundary is a cheap check.
## 4. Gate: skip = NOT_PROVEN
- [H] Heuristic: an environment variable or a missing dependency turns a check into a silent skip; two gates on the same code then give different verdicts. Hence "skip, timeout, 0 tests are not PASS".
- [H] Heuristic: a hand-maintained list of gate tests drifts behind the collected files over time. Hence `gate-integrity.md` §1 "The gate runs everything that is collected".
## 5. Accept on the exact tree, verdict from the summary line
- [H] Shell behaviour: in a pipeline `cmd | tail` the exit code belongs to the last command; without `pipefail`, `; echo rc=$?` does not reflect the runner's outcome.
- [H] Heuristic: check an agent's self-report of a run ("all passed", percentages, counts) against the summary line of the final run on the exact tree.
## 6. Close with a re-measure
- [H] Heuristic: a re-measure is necessary but not sufficient — something closed by a re-measure sometimes reopens; add an independent oracle and a measurement before the code of the next change.
- [H] Heuristic: "no errors found" means "no probe found any", not a measured zero.
## The oracle is independent
- [E] Knight & Leveson (1986): failures of independently written versions of one program are correlated — the independence hypothesis was rejected. A replication on 48 implementations by coding agents (arXiv 2606.20158): substantial common-mode failures, similar to the original work.
- [H] Heuristic: parity of two implementations built on a shared library, or a check against your own catalogue, is consistency, not correctness; an external engine and real data find what they miss.
## Protecting the oracle: judge the final diff
- [E] ImpossibleBench: Claude Opus 4.1 passes (that is, cheats on) 50% of Conflicting-SWEbench tasks (55% with a lenient prompt); Claude models and Qwen3-Coder as a group cheat mostly (>79%) by editing tests.
- [E] BenchJack: a `conftest.py` (pytest hook) planted at the repository root rewrites test outcomes to pass; a substituted `python3` on PATH forges the reward. [H] `*.pth` files are the same bypass class, but the paper does not cover them.
- [H] By construction: a hook on Edit/Write does not see edits made through the shell (`sed -i`, `>`, `cp`). So judge the final diff, not the edit tool.
- [H] Heuristic: a test-weakening detector gives false flags on renames and moves (the test lives on under another name, in a class, a helper, a table); its recall without labelled data is unknown. Calibrate on your own history: `guard_diff.py --calibrate 80`, review the flags by hand; enable it as a warning first. A detector that flags almost everything is useless — remove it.
## A check that blocks legitimate work is a defect
- [H] Heuristic: a global check that does not know the project's permission channel blocks sanctioned edits and invites workarounds. Integrate it with the project's allowlist.
- [H] Heuristic: an interceptor needs a two-way selftest (block and pass), otherwise false blocks go unnoticed until an incident.
## Honest exit
- [E] ImpossibleBench: the option to abort the task (flag_for_human_intervention) cut cheating for GPT-5 from 54% to 9% and for o3 from 49% to 12%; for Claude Opus 4.1 the effect was "much less pronounced". It complements mechanisms, it does not replace them.
## Autonomy
- [H] Heuristic: a "continue?" question about a reversible step costs the human more than a rollback; ask about the irreversible. In a team the checkpoint is the PR.
## Three failures — change approach or context
- [E] Huang et al. (ICLR 2024): self-correction without an external signal does not fix reasoning errors and sometimes makes the result worse.
- [H] Heuristic: anchoring on your own hypothesis grows with the number of attempts. The number 3 is not measured (Huang et al. do not give it), so it is advice, not a prohibition.
## Delegation
- [E] Pairwise error correlation: within one model ρ̄≈0.68, within one family ≈0.52, across families ≈0.47 (arXiv 2607.10139, §5.4). Cross-review is asymmetric: Claude reviewing Codex raised the pass rate 71.6% → 89.7%, while Codex reviewing Claude lowered it 91.4% → 82.8% (116 LCB tasks, a single experiment; arXiv 2607.21656).
- [H] Heuristic: two writers of the same semantics diverge at the seams; independent tasks parallelize safely.
- [H] Heuristic: a large change across dozens of files hits a single agent's turn limit — cut it into parts with a state file. The threshold is not measured.
- [H] Heuristic: a noticeable share of red gates is bookkeeping, not a code defect; a preflight pays off when the gate is long.
- [H] Observation from one long-running project (11 change cycles; not a controlled measurement): with
  identical ceremony for every item and three full cycles per item (measure, design, code), an item cost
  about 2.5–3 M tokens and 1–3 calendar days. Real defects were caught by cross-model review of the design
  and of the code. The mechanical auditor raised no FAIL over the 11 cycles; it was kept as a cheap check
  (tens of thousands of tokens) against fitted facts. A separate closer mostly repeated re-measures already done. Hence ceremony levels, one cycle per item, and the closer off by default
  (`delegation.md` §0–1). The expected saving from this restructuring is not yet measured.
- [H] Heuristic: review sampling relaxed only after measured quiet (six reviews with no blocking finding) and
  restored at the first finding. The thresholds are a starting point, not a measured optimum.
## Refactoring and flaky tests (`refactor-flaky.md`)
- [E] TDAD (arXiv 2603.17973, v2): a map of affected tests cut the regression rate 6.08% → 1.82% (SWE-bench Verified, Qwen3-Coder 30B, 100 tasks); a TDD instruction without the map gave 9.94%, worse than baseline.
- [E] Bavota et al. (SCAM 2012): 15% of refactored classes (1,616 of 10,969) later underwent bug fixes; hierarchy refactorings (Pull Up Method, Extract Subclass) induce fixes more often.
- [E] Google (Micco, 2016): ~1.5% of runs give a flaky result; almost 16% of tests have some degree of flakiness. Luo et al. (FSE 2014): in 45% of commits fixing flaky tests the root is Async Wait. Parry et al. (EASE 2025): 75% of flaky tests belong to clusters of co-failing tests, often with a shared root.
- [H] Arithmetic: a 2% flake over 10 runs shows up with probability 1 − 0.98¹⁰ ≈ 18%; 95% needs 149 runs.
## Release (`release.md`)
- [H] Heuristic: health 200 does not prove the right version from the right checkout was deployed; compare file or tree hashes.
- [H] Heuristic: a raw float repr can differ between machines in the last digits with equal code; compare after rounding to a fixed number of digits.
- [H] Heuristic: rolling back by snapshot name can restore the wrong version; roll back by hash or an explicit identifier.
## Skill shape
- [E] SkillsBench (v4): compact and standard skills +19.0 and +21.5 pp, detailed +14.5 pp, "comprehensive" +0.7 pp; self-generated skills fall below baseline by 8.1–11.5 pp. SWE-Skills-Bench (v2): 92 of 98 public skills show no statistically significant effect, mean pass ratio 76.6% → 76.9%. Hence a short core plus references.
## Sources
- Von Arx S., Chan L., Barnes B. *Recent Frontier Models Are Reward Hacking*. METR blog, 2025-06-05. https://metr.org/blog/2025-06-05-recent-reward-hacking/
- Zhong Z., Raghunathan A., Carlini N. *ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases*. arXiv:2510.20270, 2025. https://arxiv.org/abs/2510.20270
- Wang H., Li H., Mang Q., Cheung A., Sen K., Song D. *Do Androids Dream of Breaking the Game? Systematically Auditing AI Agent Benchmarks with BenchJack*. arXiv:2605.12673, 2026. https://arxiv.org/abs/2605.12673
- Knight J. C., Leveson N. G. *An Experimental Evaluation of the Assumption of Independence in Multiversion Programming*. IEEE Transactions on Software Engineering, SE-12(1):96–109, 1986. https://doi.org/10.1109/TSE.1986.6312924
- Ron J., Baudry B., Monperrus M. *N-Version Programming with Coding Agents*. arXiv:2606.20158, 2026. https://arxiv.org/abs/2606.20158
- Liu N. *LLMs as a Jury: Cross-Model Consensus Can Outperform Process Reward Models for LLM Reasoning*. arXiv:2607.10139, 2026. https://arxiv.org/abs/2607.10139
- Xiang Z., Zhang Y., Zhang Y., Xu H. *Cross-Model LLM Code Review: Should you use Claude to review Codex or vice versa?* arXiv:2607.21656, 2026. https://arxiv.org/abs/2607.21656
- Huang J., Chen X., Mishra S., Zheng H. S., Yu A. W., Song X., Zhou D. *Large Language Models Cannot Self-Correct Reasoning Yet*. ICLR 2024; arXiv:2310.01798. https://arxiv.org/abs/2310.01798
- Alonso P., Yovine S., Braberman V. A. *TDAD: Test-Driven Agentic Development — Reducing Code Regressions in AI Coding Agents via Graph-Based Impact Analysis*. arXiv:2603.17973, 2026. https://arxiv.org/abs/2603.17973
- Bavota G., De Carluccio B., De Lucia A., Di Penta M., Oliveto R., Strollo O. *When Does a Refactoring Induce Bugs? An Empirical Study*. IEEE SCAM 2012, pp. 104–113. https://people.lu.usi.ch/bavotg/papers/scam2012.pdf
- Micco J. *Flaky Tests at Google and How We Mitigate Them*. Google Testing Blog, 2016-05-27. https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
- Luo Q., Hariri F., Eloussi L., Marinov D. *An Empirical Analysis of Flaky Tests*. FSE 2014, pp. 643–653. https://doi.org/10.1145/2635868.2635920
- Parry O., Kapfhammer G. M., Hilton M., McMinn P. *Systemic Flakiness: An Empirical Analysis of Co-Occurring Flaky Test Failures*. EASE 2025; arXiv:2504.16777. https://arxiv.org/abs/2504.16777
- Li X. et al. *SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks*. arXiv:2602.12670 (v4, 2026-06). https://arxiv.org/abs/2602.12670
- Han T., Zhang Y., Song W., Fang C., Chen Z., Sun Y., Hu L. *SWE-Skills-Bench: Do Agent Skills Actually Help in Real-World Software Engineering?* arXiv:2603.15401 (v2, 2026-10). https://arxiv.org/abs/2603.15401
