# Coding-model comparison log

Purpose: assess whether GPT-6 improves useful project progress enough to justify its usage
relative to GPT-5.6 Sol. These are observations from development, not a controlled benchmark.
The coding assistant and the trained Pokemon policy are different models.

## What to record each session

- Task and starting revision; whether the diagnosis/design was inherited.
- Verified deliverable and connection to learned gameplay or living-Pokedex progress.
- Measured local test time, hosted CI time and private-run time separately.
- Corrections after failed commands, failed tests, review or production use.
- Input/output/reasoning tokens and account usage only if actually available; otherwise unknown.
- Reasoning setting and Fast mode only when confirmed for that session.

Compare cost per verified deliverable over several similar sessions, accounting for task size,
inherited work, machine/runtime differences and CI waits. Faster generated text, more tests or
more documentation alone do not establish better value. API prices do not establish subscription
usage debits. No account quota or billing data is inferred from elapsed time.

## 2026-09-04: GPT-5.6 Sol handoff to GPT-6

**Inherited evidence:** PR 211 fixed the mixed-partition binding defect, passed 6,688 local tests,
merged at `32dcb064`, and passed CI `33904380404/1`. The following census was interrupted after
65+ minutes in binding diagnosis with zero protected effects. The repeated-validation diagnosis
and proposed index refactor were already present before the model switch; credit for finding
that defect must not be assigned to GPT-6.

**GPT-6 delivered:** implements a per-call validated capability index and exact shared join,
while retaining full private-plan validation in the freezer. Six added regression cases cover
bounded projection work, parity across context faults and projection substitution. The focused
slice passes 25 tests in 62.72 seconds. Lint, typing across 364 modules, documentation/privacy/focus
checks and four registry reproductions pass. PR 212 merged as `7d654cdf`; both hosted runs passed
6,691 tests, with four skips and one expected failure. No hosted CI run failed in this session.

**Production outcome:** all 429 feasible supplements bound with zero failures. Completion was
observed within 834 seconds of launch (an upper bound; exact process duration was not measured).
The preceding attempt had been stopped after 65+ minutes. The following one-shot freeze completed
in a measured 788.71 seconds and stored/reopened three new development roots. Both commands had
zero gameplay, prediction, fit, outcome, teacher and claim effects. Supply preparation succeeded;
the Pokemon model did not learn or gain authority in this session.

**Audit finding:** the existing held runner parses historical mixed schedules and cannot consume
the new zero-train supplement. GPT-6 identified and documented the missing reader/admission and
executable preflight instead of treating the freeze as gameplay readiness.

**Infrastructure timing:** PR pytest took 1,498.24 seconds; main pytest took 982.70 seconds for the
same source and test counts. That variation is a warning against attributing session wall-clock
differences to the coding model. Total pytest waiting alone was about 41 minutes. The subsequent
census and freeze also spent substantial time in unchanged input checking and capability discovery;
their individual stage timings were not instrumented, so the split is unknown.

**Corrections so far:** the first test invocation and registry-generation batch omitted the
worktree import path and failed before executing tests; both were corrected. An additional
protocol-golden test failure followed registry regeneration: one expected assignment digest was
missed while updating the other source-derived golden values. The 140 other protocol/focus tests
passed in that run (65.54 seconds); the stale digest was corrected and the failed test rerun.

**Usage:** exact assistant token totals, weekly subscription debit, actual reasoning setting and
Fast-mode state are unavailable in this log. The recommendation to use High is not evidence
that High was selected. No cost or speed superiority is established yet.

**Current judgment:** a verified engineering success, but insufficient evidence that GPT-6 earns
its additional usage cost over Sol. Sol had already supplied the diagnosis and refactor direction.
Credit GPT-6 for implementation, regression coverage, completing the gate and the downstream
integration audit; do not claim a controlled model advantage. Compare several similarly scoped
sessions and their observed usage before changing the default solely on this result.

Evidence: [binding result](evidence/red-living-dex-development-supplement-binding-result-v1-2026-09-04.json),
[freeze result](evidence/red-living-dex-development-supplement-freeze-result-v1-2026-09-04.json).
