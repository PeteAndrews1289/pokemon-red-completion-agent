# Required ROM-free acceptance matrix

Every row needs a named production-path test or an explicit unfinished finding in REPORT.
Do not satisfy these by testing a reimplementation of the coordinator inside the test.

## Identity and authority

A01 Valid parent decision/menu/execution/outcome/terminal chain admits one continuation.
A02 Wrong model, terminal, goal fingerprint, menu or parent link rejects before query/input.
A03 Cross-run receipt substitution rejects even when resource totals happen to match.
A04 Ambiguous or missing unique evolution binding rejects; no first-match fallback.
A05 Same-goal continuation issues zero model queries; fresh replan issues one durable choice.
A06 Equivalent exploration and deterministic storage remain separately counted.
A07 Historical failed outcome bytes remain unchanged after later success.
A08 Continuation completion adds no extra fitted example or duplicate registration credit.
A09 Private refs, hashes, raw locations and paths never enter model feature vectors.
A10 Unknown schemas/missing required fields reject explicitly, not assumed legacy defaults.

## Resources and limits

B01 Two local chunks cannot each receive the original global action/frame allowance.
B02 Exact cap and one-over-cap cases; zero remaining means zero new inputs.
B03 Bool/negative/noninteger counters and nonfinite deadlines rejected.
B04 Cash spend is actual delta, conserved across segments; fees never double-counted.
B05 Semantic actions, controller actions, encounters and frames use distinct units.
B06 Frame/action limits enforced inside work, not merely checked after overrun.
B07 Time spent observing/choosing/verifying counted; expiration blocks the next costly admission.
B08 Resume inherits remaining deadline/budgets; clock injection handles rollback conservatively.
B09 No-progress limit stops repeated unchanged/meaninglessly changed snapshots.
B10 Failed capture/route work consumes budget and remains in summary.
B11 Lifetime goal/continuation caps prevent unlimited chains or implicit new campaigns.
B12 Storage/support actions count in totals without becoming model goal successes.

## Paid session

C01 Safe search chunk -> same active admission -> continued patrol -> captured registration.
C02 Two failed captures consume balls; zero capture gains recorded truthfully.
C03 Same session continuation pays zero extra fee and cannot call admission.
C04 Inactive session with positive stale steps/balls rejects reuse.
C05 Step reserve stop differs from zero balls and from session end.
C06 Zero balls, insufficient steps or blocked storage stops before more seeking.
C07 Current native session disagrees with persisted lineage/resources -> reject.
C08 Capture succeeded but terminal unsafe -> no success promotion or automatic new goal.
C09 Original source reconstructed read-only; no earlier-state controller inputs.
C10 No hardcoded route/target in continuation; real patrol resume gets the admitted endpoint.
C11 Capture quota spans chunks; one-per-chunk must not silently increase a one-goal quota.
C12 Session ends/goal completes -> normal safe-boundary replan or explicit stop, never auto-pay.

## Evolution

D01 Local quantum -> exact terminal -> same unique evolution goal -> verified success.
D02 Global action exhaustion cannot masquerade as a renewable local quantum.
D03 Target/specimen/reserve mismatch -> stop without replacing the chosen target.
D04 Reordering/evolution does not fabricate XP loss/gain or success from byte changes alone.
D05 Repeated bounded segment without usable semantic progress hits finite stop.
D06 Non-budget executor error and failed postcondition remain terminal failures.
D07 Registration flag and physical specimen accounting both verified after evolution.
D08 Existing continuation/default-run tests still pass unchanged.

## Durability and concurrency

E01 Crash before intent: only provably unconsumed work may be admitted.
E02 Intent persisted but possibly consumed query: ambiguous stop, no re-query.
E03 Choice persisted but execution-started uncertain: no duplicate dispatch.
E04 Execution-started but no trustworthy terminal: ambiguous stop, no replay.
E05 Terminal published but no reconciled outcome: conservative stop; no guessed success.
E06 Complete terminal/outcome permits explicit resume only when no newer uncertainty exists.
E07 Two simultaneous campaign/segment claims: at most one callback/query/input.
E08 Same parent terminal cannot spawn two children after restart.
E09 Partial/truncated/corrupt/wrong-hash records fail closed without overwriting originals.
E10 Input/verification exception retains exact bounded cause and readable terminal if obtainable.
E11 Snapshot failure reports unverified terminal; never manufactures safe=true.
E12 KeyboardInterrupt/SystemExit/cancellation not swallowed into success or automatic retry.
E13 Publication failure never leads to unrecorded inputs or silent continuation.
E14 Existing output directory refused unless explicit valid resume; no auto-clean/delete.
E15 Resume with terminal chain valid but source/config policy changed requires explicit rejection
    or a documented allowed immutable-compatible policy—not silent adoption.

## Wiring and reporting

F01 CLI default leaves historical stop-on-error behavior unchanged.
F02 Explicit opt-in with fake runtime reaches production coordinator and both real adapters.
F03 Invalid opt-in plan fails before emulator construction/model loading.
F04 Dry inspection/summary executes zero controller inputs and zero model queries.
F05 Aggregate cash/actions/frames equal reconciled segment sums; missing values not zero.
F06 Original choice count distinct from segments, successes, interventions and attempted queries.
F07 Same-goal resume then changed-state replan is tested end-to-end with real selector seam.
F08 At least one exhaustion scenario and one unknown-error scenario stop without fallback.
F09 All default guards retained, including protected specimens and ordinary trainer scope.
F10 Native qualification clearly NOT RUN; synthetic tests not called real-game success.

## Existing regression starting set

tests/test_red_autonomous_player.py
tests/test_run_red_autonomous_collection.py
tests/test_red_autonomous_collection.py
tests/test_red_autonomous_capture_recovery.py
tests/test_red_autonomous_safari.py
tests/test_red_live_safari.py
tests/test_red_indoor_safari.py
tests/test_red_safari_acquisition.py
tests/test_red_safari_exit.py
tests/test_red_player_continuation.py

Run with pytest -q and explicit paths plus new tests. Do not modify expected results to hide regressions.
Use ruff check for touched Python files and applicable mypy checks; list inherited errors separately.
Final commands also include:
- python scripts/check_docs.py
- PYTHONPATH=src:scripts python scripts/check_product_focus.py
- python -m pytest -q tests/test_documentation_surface.py
- PYTHONPATH=src python scripts/regenerate_collection_registry.py
- PYTHONPATH=src python scripts/regenerate_collection_registry.py --check
- git diff --check

No minimum artificial test-count target. Meaningful adversarial coverage matters.
