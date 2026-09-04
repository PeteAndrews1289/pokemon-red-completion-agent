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

## 2026-09-04: supplement-consumer implementation session

Starting revision: `52cb0dcc`. The preceding GPT-6 session had already identified this adapter
gap, so this session is implementation rather than an independently discovered diagnosis.

The new explicit supplement binding and strict reader share development admission and journals
with the historical held-suffix path. The real stored three-row plan authenticates without
opening state files, a ROM, predictions or outcomes. A ROM-free positive-path test reaches the
actual scorer and selected-outcome journal and recovers without reopening a runtime. The concrete
five-root production command remains unfinished; no real learning progress is claimed.

Corrections: the initial module import used an incorrect guessed filename; several exploratory
file lookups also missed. One test confused a coordination lock with a claim. The positive-path
fixture needed correction for authentic root/recipe pairing, occupied storage and scarce supplies;
otherwise actual providers correctly rejected its offers. A temporary diagnostic initially used
a symlinked system temporary path and was corrected to its resolved path. The real-record check
also corrected the inherited conflation of shared-plan and complete Red-plan digests.

The first focused batch passed 36 tests and failed one lock assertion in 151.03 seconds.
The successful full positive-path test passed in 30.00 seconds after fixture corrections.
Whole-source typing passed across 365 modules and repository lint passed at this checkpoint.
The final regression batch passed 212 tests in 272.94 seconds; a strengthened positive-path
test separately passed in 30.08 seconds. One additional test correction compared a stored JSON
record with the JSON-normalized fixture rather than expecting in-memory tuples to survive as
tuples. A guessed registry-loader function name also failed before being replaced with the
existing parser. No hosted failure is inferred from these local iterations.
These timings are not matched GPT-5.6 comparisons. Exact assistant tokens, account debit,
reasoning setting and Fast-mode state remain unknown.

Judgment: do not yet claim GPT-6 is better value. This session demonstrates useful integration
work but also rework and remaining production assembly. Use a focused two-lane independent audit
before consuming the five development cases, not a large whole-repository review. Official
[model comparison documentation](https://developers.openai.com/api/docs/models/compare) is product
reference material, not evidence of this project's subscription cost or measured speed.

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
