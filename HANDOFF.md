# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Teacher-only battle practice: levels and stats verified

Pete authorized teacher interventions for training and asked for a reusable
battle factory. The first [factory slice](docs/evidence/red-teacher-battle-practice-factory-2026-09-17.json)
controlled actor moves/PP and opponent HP. The [level/stat extension](docs/evidence/red-teacher-battle-level-stats-2026-09-17.json)
now controls both combatants' levels, current/max HP and Attack, Defense,
Speed and Special. The private Red adapter updates and reads back the party,
active battle and unmodified battle copies. The model never receives a
state-edit action.

The new isolated state set the actor to level32,85/90 HP and declared stats,
and the opponent to level34,80/90 HP and declared stats. Materialization used
zero controller actions and frames. Four real moves at matched 2,048-frame
timing dealt 14.4%,31.1%,44.4% and0% opponent HP respectively. The frozen
model chose the missing Guillotine, while Ice Beam was best at this timing.
This is one correctable assisted training case, not independent coverage or
evidence of model gain. No fit or promotion occurred. The source save is unchanged.

Limits: species, opponent moves, status, items and trainer AI are not yet
configurable. Changing actor level does not recalculate party experience, so
the current qualification is a bounded single-turn practice case, not a
coherent long-running battle campaign. Next: address experience or explicitly
enforce single-turn use; prospectively vary assisted train configurations and
RNG timing. Fit only when the training gate is met, then compare against frozen
and fixed controls on untouched natural development roots. Generated siblings
are not independent roots or Red completion. No full run or GitHub push.

Red remains 96/124 with 74 specimens and 198 cash. Model137 remains 137
examples, 92 successes and 58 economy-qualified; fresh Red acceptance is 0/5.
Gameplay is stopped. Recommended next: Sol High, Fast off, 90–120 minutes for
experience consistency and a varied, bounded train curriculum.
