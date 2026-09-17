# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Battle practice: complete-turn scoring verified

Pete authorized teacher interventions for training and asked for a reusable
battle factory. The first [factory slice](docs/evidence/red-teacher-battle-practice-factory-2026-09-17.json)
controlled actor moves/PP and opponent HP. The [level/stat extension](docs/evidence/red-teacher-battle-level-stats-2026-09-17.json)
now controls both combatants' levels, current/max HP and Attack, Defense,
Speed and Special. The private Red adapter updates and reads back the party,
active battle and unmodified battle copies. The model never receives a
state-edit action.

The [species/moveset extension](docs/evidence/red-teacher-battle-species-moves-2026-09-17.json)
reads all151 species from the authenticated cartridge: base stats, types,
starting and level-up moves, TM/HM compatibility, growth rates and experience.
It can change both species and their levels, stats and moves/PP. A private
Pikachu-versus-Squirtle state read back with coherent species, stats, levels,
actor experience and movesets. Materialization took zero actions and frames.
Four real move branches executed at matched timing; Thunderbolt knocked out
Squirtle and was the frozen model's choice. The follow-up
[complete-turn verification](docs/evidence/red-battle-complete-turn-verification-2026-09-17.json)
found that the earlier collector stopped at the first move effect, sometimes
before the opponent replied. It now settles to the next MAIN or terminal
boundary while proving the selected PP spend and refusing a second move.
The same Diglett test changed Quick Attack's measured player damage from 0 to
27.9%; the Squirtle test now records retaliation on nonterminal moves and a
real battle exit on Thunderbolt. Earlier first-effect outcomes must not be
treated as complete-turn labels. The source save is unchanged.

Limits: requested custom movesets are assisted even when they exceed a species'
natural learnset. Evolution-inherited/event moves are not cataloged. Status,
items, full teams, switching and trainer AI are not yet configurable in the
factory. Existing learned battle-control and switch-target components are
separate; do not rebuild them blindly. Three timings of the same Ground matchup
produced three different best attacks, so the next bounded curriculum must
average or otherwise model timing/RNG uncertainty before fitting. Fit only when
the multi-root training gate is met, then compare against frozen
and fixed controls on untouched natural development roots. Generated siblings
are not independent roots or Red completion. No full run or GitHub push.

Red remains 96/124 with 74 specimens and 198 cash. Model137 remains 137
examples, 92 successes and 58 economy-qualified; fresh Red acceptance is 0/5.
Gameplay is stopped. Recommended next: Sol High, Fast off, 90–120 minutes for
prospective multi-timing train configurations and the natural-battle comparison.
