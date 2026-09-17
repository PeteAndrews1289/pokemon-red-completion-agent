# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Model-owned battle episode core is tested; gameplay has not begun

The [ROM-free implementation evidence](docs/evidence/red-model-battle-train-episode-core-2026-09-17.json)
covers a train-only, bounded multi-encounter episode. It inherits one
authenticated upstream source identity, retains every child battle's
pre-choice state, model selection and settled outcome, and reopens those files
before allowing another encounter. Repeated semantic observations remain one
distinct decision, never new independent roots. A missing retained outcome,
unsafe field state, child failure or cost overrun stops further setup. The
single-encounter runner now records train partition without granting fit
eligibility; its former development default is unchanged. The episode caller
must still provide the hard action/frame limiter.

This is only the tested core. The existing cartridge launcher is for one
Route 11 development encounter and cannot safely claim or execute one of the
six untouched train sources as a multi-encounter episode. No train pilot,
model fit, development source, or new learned outcome occurred. The one-session
no-learning-output alarm applies: next work must prioritize a real bounded
choice/outcome attempt, not more static inventory or presentation work.

Next: prospectively choose one untouched train source and build its
source-authenticated launcher with a hard action/frame limiter and
natural-encounter-only setup. Run at most one train-only mechanical pilot;
preserve its terminal even on failure. If it yields actual varied decisions,
develop isolated train-side candidate-outcome branches, then compare a fitted
ranker against frozen and fixed-heuristic controls on disjoint development
roots. No fit from unbranched action traces, no promotion, full run, or push.

Red remains 96/124 with 74 specimens and 198 cash. Model137 is unchanged
(137 examples, 92 successes, 58 economy-qualified); fresh Red acceptance is
0/5. Gameplay is stopped. The six untouched train and four development roots
remain unclaimed. No GitHub push. Recommended next: Sol High, Fast off for
source-authenticated launcher and one measured pilot; escalate to Astra High
only for a difficult source/setup design or unexpected failure.
