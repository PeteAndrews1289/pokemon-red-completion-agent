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

**GPT-6 work in progress:** implements a per-call validated capability index and exact shared join,
while retaining full private-plan validation in the freezer. Six added regression cases cover
bounded projection work, parity across context faults and projection substitution. The focused
slice passes 25 tests in 62.72 seconds. Lint, typing across 364 modules, documentation/privacy/focus
checks and four registry reproductions pass. Hosted CI and production timing are pending.

**Corrections so far:** the first test invocation and registry-generation batch omitted the
worktree import path and failed before executing tests; both were corrected. An additional
protocol-golden test failure followed registry regeneration: one expected assignment digest was
missed while updating the other source-derived golden values. The 140 other protocol/focus tests
passed in that run (65.54 seconds); the stale digest was corrected and the failed test rerun.

**Usage:** exact assistant token totals, weekly subscription debit, actual reasoning setting and
Fast-mode state are unavailable in this log. The recommendation to use High is not evidence
that High was selected. No cost or speed superiority is established yet.

**Current judgment:** promising repair implementation, insufficient evidence for a model-value
comparison. The decisive result is a verified completed development gate at acceptable cost.
