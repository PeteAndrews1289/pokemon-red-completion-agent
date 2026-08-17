# Claude audit handoff: party-outcome V2 successor

Read-only review only. Do not run the emulator, send controller input, fit a model, open sealed Red
or Crystal, modify files, or create a replacement result. Codex remains the sole implementer and
publisher. A reviewer verdict can block an authorization request; it cannot authorize execution.

## Why this review exists

The owner authorized V1 plan-file SHA
`e8647ac8b232b0f892fd2dcf174d83e331bc5833dede71fa5510f9cdbb1960be`, semantic plan SHA
`8742a06e5f9b4a9a781c1c76874ad133829085fe7972928398d0fc1edc231416`, source
`44156676d23225b8330ff7b318ad2f6cc481b8dc` and CI run `31978843670` attempt 1. Trial 1 was
claimed, initial completion-aware observation failed before the action executor was constructed,
and an immutable invalid terminal was written. No later claim exists. The old identity is consumed
and may never retry.

The failure was a port-capability defect: `FrameBudgetEmulator` dynamically forwarded reads, but a
runtime `ReadOnlyCartridgeRam` protocol check could not see that method. Full-box observation
refused. The candidate repair gives semantic and party readers the raw emulator's complete
read-only port and gives only `FrameSafeExecutor` the frame-budget proxy.

## Candidate invariants to attack

1. The exact execution helper used by both read-only preflight and `_execute_trial` must keep raw
   observation and bounded control separate. Mutate either call site back to the proxy and require
   a test to fail.
2. Preflight must exercise full completion-aware observation through that helper and advance zero
   controller frames. A merely static source assertion is insufficient.
3. The successor must retain all 14 questions and 55 assignment identities while exposing exactly
   54 active trials: 32 train and 22 development.
4. The inherited trial must bind the exact V1 plan file, semantic plan, claim, result, terminal,
   sealed-record and manifest digests. Mutate each independently.
5. `PartyDevelopmentOutcomeTrialClaim.build` must reject the inherited assignment before any
   private publication or controller construction.
6. Successor record IDs must be plan-specific and cannot collide with V1 or a later V3 successor.
7. A second successor must carry both older inherited records and any newly consumed V2 records
   without rebinding their result to the newest plan.
8. Result assembly may accept an inherited result only through its exact lineage entry. The lost
   development menu remains unusable and cannot be silently dropped or replaced.
9. The dashboard must show one historical tombstone, trial 2 as next untouched, 1/55 terminal
   progress, 54 remaining and a fresh-authorization wait—not a retry or a newly active failure.
10. V1 must remain unloadable for execution under the changed source; V2 must require its own exact
    plan-file digest, semantic digest, published source and green CI attempt.

## Evidence and files

- [Failure receipt](evidence/red-party-development-outcome-campaign-v1-failure-2026-08-16.json)
- `src/pokemon_red_completion/party_development_outcome_campaign.py`
- `src/pokemon_red_completion/party_development_outcome_lineage.py`
- `src/pokemon_red_completion/party_development_outcome_results.py`
- `scripts/run_red_party_development_outcome_campaign.py`
- `scripts/freeze_red_party_development_outcome_campaign.py`
- `scripts/run_party_development_readiness_dashboard.py`
- `tests/test_party_development_outcome_lineage.py`
- `tests/test_red_party_development_outcome_campaign_scripts.py`
- `tests/test_party_development_readiness_dashboard.py`

The published review target is the exact PR head containing this document. Require green CI for
that exact commit, then recompute every committed/source digest rather than trusting a pasted
summary. The later private V2 plan and preflight are separate artifacts and should be checked only
after Codex freezes them from the green head.

## Required verdict

Return `APPROVE TO ASK`, `APPROVE WITH CONDITIONS`, or `REJECT`. Every condition or rejection must
name a concrete falsifier, affected invariant and smallest repair. Also report mutation totals with
equivalent or invalid probes separated from real survivors. Approval means only that Codex may ask
the owner for one new 54-trial authorization; it grants no controller authority itself.
