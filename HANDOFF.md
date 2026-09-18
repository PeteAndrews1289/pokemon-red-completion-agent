# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Astra decision: freeze attacks; test useful switching next

[Review](docs/reviews/red-trainer-astra-readiness-decision-2026-09-17.md) and
[evidence](docs/evidence/red-trainer-astra-readiness-decision-2026-09-17.json).
A read-only composition of the older attack head with corrected cold-fit control/
switch heads passes all unchanged TRAIN gates: original-44 attack regret 0.03538
<=0.0554; all-52 attack 0.04475 <=0.0648; complete-action regret 0.11260 <=0.1609.
No new model was fitted or packaged. Both prior failed fits remain failures.
Stop the same-corpus attack-refit recipe.

Next: package that exact composition with authenticated per-head lineage and
unchanged attack weights; round-trip through the policy loader and reproduce
the gates. Fix build_refit_plan silently inheriting prior warm-start settings
when no new warm arguments are supplied. The 34 focused tests pass but do not
cover that reproduced defect.

Then the four-scenario terminal HP pilot: two matchups, healthy/critical pairs,
two own members versus one foe, five timings, common four-turn horizon. All
branches must terminate; both pairs must reverse attack/switch preference with
>0.10 margins. Freeze attacks while training switching; require complete actions
within 0.02 of best in all four cases and preserve original-corpus gates.
Reserve unseen semantic variations before fitting; TRAIN replay is not transfer.

Inventory new-origin natural supply before any promotion comparison; this review
verified none. Do not reopen consumed DEVELOPMENT or silently launch a teacher
progression factory. Broad status/recovery/Counter/Struggle coverage remains
outside this first segment. Detailed scope and conditional estimates are in review.

Next: Sol High, Fast off, one implementation/pilot session with a two-hour
reassessment cap. No standing additional Astra gate if checks pass; escalate
failed falsifiers or material design decisions.

Model137 stays 137 examples / 92 successes / 58 economy-qualified;
Red stays 96/124; fresh acceptance stays 0/5. Gameplay is stopped.
This review changes the next design decision, not learner authority.
No full game, ROM hack, Crystal work or GitHub push. Pete decides publication.
