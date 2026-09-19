# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 19, 2026.

## Retention passes; natural advantage and integration do not

[Session evidence](docs/evidence/red-trainer-retention-result-2026-09-19.json).
Pete requested all next steps. Completed the interrupted local checkpoint,
authenticated all180 existing TRAIN contexts, ran one constrained fit, then
one frozen three-arm natural Champion comparison. No new TRAIN collection.

The new candidate preserves all134 old head decisions. All three unchanged
regret gates pass: original44 attack0.008849232≤0.0554; all52 attack0.035435587
≤0.0648; all52 composed0.098488040≤0.1609. Terminal128 composed regret improves
0.829764698→0.478781094 (42.3%); newer80 improves1.274601178→0.709266719.
The five prospective TRAIN checks pass. This is actual offline learned progress.

Natural Champion: candidate wins22decisions/1party faint/389HP lost; frozen wins
16decisions/0faints/156HP; fixed wins29decisions/2faints/345HP. All67decisions and
259event records complete, zero teacher queries, memory edits or invalid actions.
The natural comparison FAILS. Player integration is deliberately blocked.
The unused Champion encounter shares historical ancestry with prior League
sources; it is not independent replication or a fresh full-game completion.
Do not tune to/replay it or any consumed earlier DEVELOPMENT battle.

## Retained implementation and private artifacts

`red_trainer_retention.py`: algebraic score-preserving control-schema bridge,
vectorized expected-regret gradients, projected steps and nonlinear backtracking.
All constraints apply only in training; inference remains the ordinary three-head
neural policy. No lookup table or teacher selects final actions.

`audit_red_trainer_retention.py` authenticated original states, manifests, plans
and branch logs once. Private directory red-trainer-retention-20260919-v1 holds
targets.json, manifest.json and audit.json; use the bound cache, not recollection.
No identical-input winner conflict crosses old/new groups; this does not prove
network learnability or isolate reward scale as a cause.

`run_red_trainer_retention.py` made its sole fit from the frozen100-context
terminal ancestor. Private directory red-trainer-retention-fit-20260919-v1 holds
model.json, all three optimizer traces, intermediate models and result.json.
Candidate SHA256:
9f2aa62d01b72217931a3fab4b60e69522734f69b7eeab43b90e46498c34cbbc.

Natural capture/comparison directories:
red-trainer-retention-champion-capture-20260919-v1 and
red-trainer-retention-champion-comparison-20260919-v1.
The latter includes candidate-verdict.json: natural comparison false,
final-player readiness false. One post-fit evaluation, no retries or refits.
Earlier candidates and failures remain intact.

## Concrete remaining issue

The move head's terminal128 argmax regret slightly worsens0.275556666→0.279465267
despite lower expected loss. Move/control stop after152/113accepted updates at
the stronger exact-old-choice constraints; switch completes1200updates.
This is not convergence evidence. The first natural divergence is an attack:
move005 against Alakazam does zero damage, then the learner takes127HP, switches,
and later loses that replacement. Randomness prevents a causal optimality claim.

Next bounded objective: audit the attack optimizer's active constraints and
supported move/stat coverage on TRAIN only. Preserve the original regret limits;
do not automatically freeze every old mistake forever or blindly refit. Declare
a successor only after that diagnosis, then require unused natural and independent
origin evidence. Do not rebuild the trainer or enable unqualified player authority.
Estimate one60–90minute diagnosis/implementation session; qualification timing
depends on the result. Unsupported status/recovery/boost, Counter, self-destruct
and all-party Struggle remain outside the attack/switch segment.

Checks:135focused/documentation tests passed,13integration skips; Ruff passed.
Mypy540source files passes. Registry, focus, documentation and public checks pass.
Earlier full suite12420passed/9known failures/16skips/1xfail was not rerun.
Known failures: dashboard projections7, timing golden1, runtime fingerprint1.

Model137 stays137examples/92successes/58economy-qualified; Red96/124 and fresh
acceptance0/5. Gameplay stopped. No full game, ROM hack, Crystal or GitHub push.
No Flash/Claude contribution this session. Recommended next: Astra High, Fast
off for constrained-learning and generalization judgment, not another final review.
