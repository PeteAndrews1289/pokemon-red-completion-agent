# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Battle practice: six-member party setup qualified

The teacher-only Red factory can set both combatants' Gen I species, level,
stats, HP and moves/PP from the authenticated 151-species cartridge catalog.
The [complete-turn verification](docs/evidence/red-battle-complete-turn-verification-2026-09-17.json)
settles attack outcomes through the opponent's reply or battle exit; earlier
first-effect labels are not complete turns. Teacher changes are confined to an
isolated training capture; the model has no memory-write action.

The [six-member qualification](docs/evidence/red-teacher-battle-team-2026-09-17.json)
adds up to five distinct existing reserve-party slots, each with cartridge-derived
types, stats, experience and display name, plus declared level, HP and moves/PP.
The source had six occupied slots. One private materialization used zero actions
and frames and read back six distinct species. The existing semantic switch
view exposed all five reserves. A bounded real-game switch to slot 2 succeeded
in 18 actions and 1,098 frames; the opponent replied and battle state remained
wild/active. Source state bytes were unchanged.

This is an infrastructure qualification, not model learning. No model selected
that switch, no outcome was added to training, no fit or promotion occurred,
and the generated state adds zero independent roots. Trainer opponent rosters,
trainer AI, replacement after KO, items and multi-turn trainer-battle
settlement are still unqualified. Custom movesets remain explicitly assisted.

Next bounded work: capture model-selected attack and switch outcomes from
varied six-member train states across multiple timings, then assess whether
trainer-roster setup is the next bottleneck. Preserve root clustering and use
untouched natural development battles before any promotion. No full Red run,
ROM hack, Crystal execution or GitHub push.

Red remains 96/124 with 74 specimens and 198 cash. Model137 remains 137
examples, 92 successes and 58 economy-qualified; fresh Red acceptance is 0/5.
Gameplay is stopped. Recommended next: Sol High, Fast off, 90–120 minutes.
