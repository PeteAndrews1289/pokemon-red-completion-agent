# Ordinary control with explicit bounded healing

The strict prospective trial stopped before its first attack at Gyarados.
One learned field heal and one forced story consumed 135 actions, 12,204 frames
and one item. All 30 specimens remain; no battle medicine was used. Its complete
trace is quarantined, not fitted or resumed. See the
[retained result](../evidence/red-proactive-recovery-stop-2026-09-09.json).

## Diagnosis and decision

Leer was an unqualified incoming effect. Pinned
[move data](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/data/moves/moves.asm)
and [stat effects](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/engine/battle/effects.asm)
support zero direct HP damage for pure stat reductions. Existing residual damage
still applies; the next action rereads live defenses. Already-confused active
plus any incoming debuff remains unqualified: within-turn stat and badge changes
can invalidate a pre-turn self-hit bound. This includes damaging Psychic (ID94).

Removing that coverage gap is not enough. Strict critical-inclusive bounds would
reject healthy Jolteon172 against a219 bound and switch to Blastoise159 against132.
Worst-case switch damage leaves27; a heal to217 followed by132 leaves85, still
below the next bound. One medicine does not guarantee strict progress.

The explicit successor therefore keeps ordinary attacks and switch screens, and
adds bounded active healing before the half-HP/status rejection. This is a new
profile mode, not an automatic fallback or a changed historical contract.
Ordinary attacks retain their existing, uncalibrated critical/miss risk. Only the
healing turn requires a supported incoming bound below restored maximum HP.
Neither regime promises a no-faint run.

## Six-part mission check

1. Capability: reusable item-aware story execution, not another boss learner.
2. Learned authority: native82 retains goal choice; battle controls deterministic.
3. Transfer: varied ROM-free state/budget/target tests; correlated Red test only.
4. Falsifier: exact owned-stock menu, then one bounded Lance-only continuation.
5. Time box: reassess after the next bounded outcome; no repeated boss cohort.
6. Stop: first unsupported turn, failed goal, ledger loss, or source mismatch.
   Preserve failure and do not reset or silently change controllers.

The profile binds mode and budget. A healing request binds its entire observed
state, then rechecks damage before claiming and spending an item. Exact bag checks
survive loop restarts and Champion epilogue. Tests cover a same-bound changed
active member, failed item claims, over-spending and both real caller modes.

The focused combined suite passed513tests before the final target-binding
repair; the34-test ordinary-controller suite passed afterward. Mypy checked453
source files. These are targeted, not full-suite claims. Independent internal
review identified and verified the binding seam; no external usage audit claimed.

## Remaining roster is known, not assumed

A read-only cartridge/checkpoint review verified Champion class243/set2, with
inline [trainer move overrides](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/engine/battle/read_trainer_party.asm).
The strict controller has remaining Whirlwind, Mirror Move, Recover, Reflect,
Horn Drill and Roar gaps. Ordinary switching also rejects Mirror Move and Horn
Drill. The next plan ends after Lance, then checks the actual carried party and
Champion boundaries. It does not claim general Champion qualification.

Phase4 remains open at the unchanged model-directed completion exit. Native82
still has82 rows; the seven-return shadow remains unused. Engineering progress
does not itself count as learned advantage or story completion.
