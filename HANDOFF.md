# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Trainer practice: package ready for Astra pre-training review

The [qualification record](docs/evidence/red-trainer-practice-pretrain-qualification-2026-09-17.json)
retains both failed variants and a new valid three-on-three TRAIN configuration.
The original off-slot PP increase remains unexplained and its exact attempt is
closed. A distinct custom-stat configuration exposed impossible HP 65,535 after
a knockout; it was also closed and is not fit-eligible. Red cartridge species
IDs are not National Pokédex numbers, which caused that roster to differ from
the intended one. New teacher plans can pin each intended National number and
fail before writes on a mismatch. Future episodes reject HP above maximum
before logging an outcome and retain levels/max HP in each decision summary.

An identity-checked, cartridge-neutral-stat Pikachu/Squirtle/Bulbasaur team
faced Geodude/Machop/Pidgeotto. Its frozen attack-only baseline completed 15
decisions over 14,498 frames, beat one opponent, and lost all three members.
Six matched opening choices passed the new read-only TRAIN admission check.
Over the same two-player-turn horizon, switching to Squirtle beat the first
opponent with no party HP loss; all four opening attack branches beat none.
These are executed outcome contrasts, not teacher labels. They and all prior
assisted configurations share one upstream TRAIN root.

No model fit, learned switch authority, natural DEVELOPMENT comparison or
promotion occurred. Model137 remains 137 examples / 92 successes / 58
economy-qualified; Red remains 96/124 and fresh acceptance 0/5. Gameplay is
stopped. No full run, ROM hack, Crystal execution or GitHub push occurred.

Next: Astra High, Fast off, read-only pre-training review of (1) failed-run
exclusion despite unresolved PP cause, (2) the raw outcome-to-target contract,
and (3) minimum distinct TRAIN roots and matchup coverage. Training stays
closed until those decisions are explicit. Later fit only on admitted TRAIN
outcomes, then compare against frozen/fixed controls on untouched natural
DEVELOPMENT battles.
