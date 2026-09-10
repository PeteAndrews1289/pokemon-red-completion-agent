# Quick audit — status recovery and learning claims

Reviewed executable source: `e1005df566713ef22635543253ba2efff6f0c0d3`.
Scope: retained batch N, escape verification, outcome reporting, and the next useful
Red-learning step. No gameplay, refit, reset, or authority promotion in this audit.

## Verdict

Useful collection learning is running, but sustained operation still depends on
better handling of ordinary degraded states. Prioritize bounded status recovery,
not another large architecture rewrite or an unrelated capability lane.

- Overnight baseline: 44 registered species and 19 fitted examples.
- Latest retained result: 53 registrations, 47 specimens, 36 fitted examples.
- Current corpus: 23 successful and 13 unsuccessful settled examples. These are
  correlated training observations, not an independently evaluated success rate.
- The prior L/M batches completed eight steps successfully, seven fitted and one
  forced support step excluded. Machop capture followed by Machoke evolution,
  trainer income, ball purchase and needed healing are concrete useful behavior.
- N selected Mansion acquisition, used 238 actions / 19,596 frames, then stopped.
  Its failure and checkpoint were retained and fitted once. No new registration.

## Findings

### 1. Ordinary status damage currently terminates the batch

The recorded encounter begins with the lead at 93/93 HP and no status; subsequent
snapshots show burn at 72 HP, then 67 HP, then field/input-ready at the same location.
The escape implementation compares final status against encounter-entry status.
That mismatch alone is sufficient to reject `Route1WildFleeEvidence.verified`.
The status transition is observed, not merely guessed from the final snapshot.

This does not prove every other receipt predicate passed: the exception records a
generic gate failure, not its predicate bitmap. Field/control alone is also not
proof of an authenticated RUN result or a safe complete party. Preserve the existing
failed outcome; do not relabel it as a successful acquisition.

Next repair should distinguish verified degraded exits requiring care from unsafe
or unverifiable exits. Keep map, position, roster, PP, no-faint, battle-result and
bounded-control evidence. A status change must not become unconditional permission
to keep walking. Resume through explicit recovery/replanning from the actual state.

Relevant source: `route_1_wild.py` (`flee_wild`, `Route1WildFleeEvidence.verified`),
`gen1_route_runtime.py`, `red_routed_recovery.py`, and the failed-step stop branch in
`scripts/run_red_regional_learning_cycle.py`.

### 2. Training quantity is not learned advantage

Fitting real outcomes is genuine training. Neither 36 examples, lower training
error, nor eight consecutive same-lineage steps establishes better unseen play.
Record registration gain, actions/frames, resources, recovery interventions and
executor version. Evaluate a frozen policy on genuinely separate ordinary
development scenarios once this bounded recovery works. No sealed test is needed
to answer the immediate engineering question.

Execution failures are valid end-to-end outcomes, but are not proof that a destination
was strategically wrong. Keep failure category visible; do not invent labels for
unplayed alternatives or rewrite previous rewards after repairing an executor.

### 3. Current status must not lag behind stopped gameplay

The published model35 checkpoint remained the top status after N produced model36
and stopped. This audit updates evidence, dashboard references and handoffs. Report
running, stopped, preparing, testing and saved-state playback distinctly; documentation
and test counts never increment learning totals.

## Flash review and Codex adjudication

Gemini 3.8 Flash High completed a bounded no-tool review of supplied source excerpts
and aggregate facts. It did not independently inspect the repository or run tests.

- **Accept:** separate degraded state from unsafe failure; test preexisting versus
  newly inflicted status; do not equate correlated successes with generalization.
- **Reject:** its claim that the 19-to36 update indicates memorization. No evidence
  establishes that, and registrations increased from44 to53 during that interval.
- **Reject:** its proposed run-counter bug. Counting an attempt against the state
  before issuing RUN is intentional; successful escape does not erase the attempt.
- **Defer:** proposed battle-result decay/latching. No recorded evidence currently
  establishes decay. Do not change that boundary based on speculation.
- **Reject as sufficient:** field-ready plus positive lead HP alone proves safety.
  Full protected-party and transition evidence remains necessary.

Post-review service display at approximately11:03UTC: Gemini group92.27% five-hour
remaining (reset about3h29m),79.97% weekly remaining (about36h20m). Initial values
were cached; these shared windows cannot establish this task's isolated cost.
Claude was not used; its quota was not queried. No external agent remains active.

## Next bounded session and mission check

1. **Capability:** safely recognize and handle status degradation during travel.
2. **Learned authority:** preserve model-selected goals/destinations and return
   verified recovery needs to the existing planner. Repair itself is maintenance,
   specifically unblocking the next registered-collection learning batch.
3. **Transfer test:** ROM-free variants across maps, existing/new status and roster
   changes; later separate development starts. No cross-title result claimed.
4. **Cheapest falsifier:** a status-only change must be distinguishable from PP,
   position, party, control or battle-result corruption without controller input.
5. **Time box:** 60–90 minutes for the repair and focused tests, then reassess;
   if qualified, a fresh bounded continuation from model36's actual terminal.
6. **Stop:** any lost guard, ambiguous terminal, repeated failure without new
   diagnostic information, consumed retry, fabricated resources or forced destination.

Keep the unqualified stone draft isolated. Flash may draft a small ROM-free test
matrix after Codex defines the return contract; Codex owns integration and gameplay.

## Validation and reporting

Existing focused suite: **105 passed, one skipped** across play, Gen I route runtime
and routed recovery. This is not a full-suite pass or proof of the proposed repair.
No runtime code was changed during this audit.
The synchronized product-focus suite passed **104 tests**, and the documentation
link/focus check passed. An initial command named a nonexistent documentation test
file and ran no tests; the corrected focused invocation is the reported pass.

End each session with verified changes, learning/counter delta, current runtime state,
failure/limitations, next bounded objective and estimate, candid feedback, external
agent contribution/quota when used, then recommended model/effort/Fast mode.

Next-session recommendation: **Astra High, Fast off**. Reserve Extra High for a
specific unresolved state-contract/design question, not routine waits or test runs.
This is a task-specific recommendation, not a measured model-cost comparison.
