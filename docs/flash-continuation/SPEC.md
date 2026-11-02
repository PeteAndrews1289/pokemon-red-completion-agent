# Continuation contract

## Mission check

1. Capability: resume an interrupted chosen task and replan from actual remaining resources.
2. Authority: model chooses consequential new goals; coordinator only enforces a declared continuation policy.
3. Transfer: ROM-free state machines cover different resources/goal kinds; no cross-game result claimed.
4. Falsifier: a fake paid search interrupted twice triggers duplicate payment, replay, budget reset or a new target.
5. Time box: five stages; reassess3hours, maximum6hours active implementation.
6. Stop: unknown failure, ambiguous durable state, unsupported adapter, design outside this packet.

## Architecture approved for implementation

A small additive coordinator with dependency-injected observation, execution, clock and durable storage.
A typed boundary/outcome contract, cumulative budget ledger and explicit session state machine.
Adapters for (a) already-paid Safari search and (b) existing evolution continuation.
An explicit optional entry point in the existing collection runner, or a thin sibling CLI
that reuses its runtime construction without copying the full runner.
Use existing package conventions; proposed new module names in WORK_PLAN are not mandatory.
Do not replace the planner, whole executor stack, existing file formats or historical receipts.
All new durable formats are versioned. Existing default invocation/output behavior remains compatible.

## Authority and boundary classification

Continue only the SAME persisted selected goal, from its latest authenticated safe terminal.
A fresh consequential choice requires a fresh action-free inventory and the existing model selector.
No new query for same-goal continuation; no reselecting a target after seeing failure.
For a model-selected area, missing-species encounter logic may behave as its existing contract permits.
Do not silently promote equivalent-exploration or deterministic-safety decisions to learned authority.

A local chunk boundary is NOT permission to reset a global budget.
Allowlisted prospective boundaries must be typed, adapter-attested and safe:
- Paid Safari: semantic search chunk ended, same session active, available balls/steps and exit reserve.
- Evolution: local action quantum ended, same unique goal and exact terminal remain admissible.
Unknown exceptions, failed verification, unsafe/missing observation, all-party loss,
hash mismatch and ambiguous execution status STOP. Do not catch-all and continue.
Legacy error_type/reason_code text alone is insufficient evidence of resumability.
A resumed action/frame counter must distinguish local from campaign exhaustion.

## Lifetime accounting

Explicit finite caps: model decisions, continuation chunks per goal and campaign, actions,
frames, encounters, no-progress chunks, cash spending, and session wall time.
Every valid input counts, including navigation, storage, healing, failed captures and failed legs.
Budgets are checked before the next costly operation; if exact granularity is unavailable,
conservatively reserve a bounded operation or stop. No invented exact hard wall-time claim.
Clock must be injectable. Persisted resume must not reset elapsed/remaining budget or extend deadline.
Reject bool-as-int, negative, nonfinite, malformed and inconsistent counters.
Keep semantic actions separate from controller macros and frames; document their units.
No hardcoded reset of cash, balls, steps, HP, PP, bag stock or experience.
Actual cash cost differs from replacement valuation; neither may be double-counted.

## Paid Safari specifics

Authenticate original decision/menu/execution/outcome and every continuation terminal link.
Reconstruct the original private area/patrol from authenticated semantic context or retained
private binding metadata; never invoke admission again or reload an earlier gameplay state.
Read-only reconstruction of old context must not issue inputs or become a live reset.
Persist an admission/session lineage identity and verify current native session through the adapter.
No after-exit reuse: inactive session is not made active by stale positive steps/balls.
Same-goal continuation has zero extra admission payment and zero new goal query.
Do not fix capture randomness. Failed Scyther attempts stay failed with balls consumed.
Use existing patrol resume and survey APIs; preserve supported controller timing.
Stop at a prospectively configured exit reserve; reserve exhaustion is NOT balls exhausted.
Report actual remaining balls/steps and a distinct typed reason.
Do not add a fixed escape route. After a safe ordinary goal/session boundary, use normal model
replanning and existing departure capability when admissible. Otherwise stop needing recovery.
A new admission may occur only as a newly model-selected goal after verified session closure,
with actual payment, fresh budget admission and real alternatives. No automatic re-entry loop.
For this package, fresh re-entry automation may remain explicitly unsupported.

## Evolution specifics

Reuse unique configuration-fingerprint rebinding and protected specimen/registration checks.
Continue from terminal only, never the source checkpoint; no target switch or new random seed search.
Some useful progress changes species or party order: byte inequality is not semantic progress,
and slot-matched XP alone cannot prove all progress. Use existing observations conservatively.
Do not implement a new battle-training policy, change XP yield, or weaken reserve protection.
No outcome of a resumed segment becomes an extra fitted goal choice.

## Crash/duplicate safety

Append immutable intent/choice/execution-started/terminal/outcome records; preserve all originals.
Claim a campaign and each dispatch exclusively before any model query or input.
An incomplete execution-started record without a trustworthy terminal is ambiguous: STOP;
do not infer that nothing ran and retry. Same for a possibly consumed model query.
Restart may use only the last fully reconciled terminal with no newer uncertain action/query.
No two children for one parent terminal. Concurrent claim losers must make zero queries/inputs.
Atomic publication and flush boundaries should reuse established repository helpers.
A corrupted/missing/truncated record must not become a fresh campaign or implicit budget reset.
Explicit resume is opt-in and must never autonomously start an OS process or scheduler.

## Results and telemetry

Record original goal outcome separately from each continuation and final goal resolution.
A later success does not erase the prior failure or add duplicate novelty/reward.
Aggregate unique model choices, goal successes, continuation attempts, failures and interventions.
Log per goal/segment: kind, authority mode, candidate count, selection/observation/execution/verification
time, actions/frames, encounters/capture attempts where observable, cash and item deltas,
balls/steps, XP/registration/specimen deltas, exact stop reason and remaining budgets.
Missing telemetry is explicitly unavailable, not zero. Reconciled totals equal segment deltas.
Private state hashes/binding references remain out of model features; paths never enter public reports.
No new training or fitting path. Report native qualification as NOT RUN.
