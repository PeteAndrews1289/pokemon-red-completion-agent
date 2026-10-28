# 8. September 22: status learning, preparation, and the floor-tile problem

[Previous](07-player-and-story.md) · [Chronicle contents](README.md)

## Predicting an effect was not enough to choose well

The September 21–22 status work exposed a familiar mismatch: improving an
intermediate training metric did not necessarily improve complete battles.
Confusion, repeated recovery and later-turn timing all mattered.

A full-HP recovery move may still heal if the opponent acts first and inflicts
damage. The [timing-aware work](../evidence/red-timing-effect-learning-2026-09-22.json)
therefore tested a different prediction question from a static effect lookup.
Yet the [combined selector](../evidence/red-native-later-selector-2026-09-22.json)
still failed its native screen. Better effect estimates did not establish better
integrated policy behavior.

A later additive actor won 72/128 battles against K's 66 with zero illegal or
flagged choices, but used 349 decisions against 276. The original efficiency
criterion still failed. Pete explicitly admitted the exact actor for bounded
story DEVELOPMENT so the project could return to Red progression.
The [admission receipt](../evidence/red-additive-story-admission-2026-09-22.json)
preserves that exception instead of rewriting it as a passed original gate.

## Learned combat returned to the gyms

Prepared Silph and subsequent story work cleared the immediate blockage.
The [Blaine result](../evidence/red-learned-blaine-2026-09-22.json) records eight
Cinnabar gym wins, including the leader, with 48 learned choices, zero faints or
illegal actions, and 18,613 earned cash. Blastoise and Dugtrio both fought.

That success has clear limits: one prepared developmental lineage, supported
route/opponent selection and healing, no matched baseline. It demonstrates
connected battle authority on that workload, not independent generalization.

Mansion navigation also remained imperfect. Legal Dig and Fly supplied an escape.
Using a legitimate existing mechanic was useful progress; it did not prove a
general switch-puzzle solver.

## The team needed preparation, not an arbitrary level target

Pete's concern about relying on one workhorse led to readiness and preparation
logic rather than automatically grinding every newly caught low-level Pokémon.
The post-Blaine request identified three reserves, not the entire party.

Forty earned outings brought Dugtrio, Farfetch'd and Jolteon to level 39.
Blastoise stayed 50; Snorlax reached 33 incidentally through learned switches.
There were 160 encounters, 153 wins, seven nonwinning exits, two faints and
32 status changes. All costs and recovery remained visible.

The 496 K choices were battle decisions. Targets, trainees, venues and healing
remained support. The operator's Route 15-to-16 change improved observed throughput
but was not a controlled comparison. Earned XP is not a model-weight update.
The [readiness audit](../evidence/red-giovanni-readiness-2026-09-22.json) retains
those distinctions and the completed preparation budget.

## A spinning floor tile stopped a prepared party

Viridian arrival first exposed a legitimate gym-open event that a strict Fly
guard rejected. The retained event change supported a narrow repair without
replaying the flight.

The next blockage was movement geometry. A spinner carried the player to a
different settled position than the route expected. More waiting could let motion
finish, but could not make the planned destination correct.

An independent read also corrected a misleading support label: visiting Viridian
Center with a full party had skipped healing, so Celadon was still the registered
recovery anchor. A plausible log message was not enough; actual state won.

## Shared routing repair, then an earned win

Forced-motion edges were added from the cartridge's movement scripts. They retain
intermediate tiles for hazard checking and require the observed settled endpoint.
Changed-layout tests cover chains, cycles, blockers, warps and hazards.

A subsequent approach still stopped before combat because prospective feasibility
ignored trainer sight lines. That shared check was corrected while retaining the
14 actions and 336 frames of the failed approach. No earlier state was replayed.

Stage285 then defeated a gym trainer in nine model decisions and earned 1,365.
Jolteon fainted; the model still won. Native Center healing restored everyone and
this time verifiably registered Viridian as the recovery anchor.
The [checkpoint audit](../evidence/red-forced-motion-gym-2026-09-22.json) records
294 targeted test passes and the limitation that not every spinner chain or
Hideout map has independent native execution qualification.

## Where this edition ends

The earned story save is safe and stopped in Viridian Gym: seven badges,
28/36 story objectives, 17 local registrations and 26,627 cash. Giovanni has not
been fought in this earned continuation and still requires further gym clearance.

The collection save remains separate at 109/124. Final fresh Red acceptance is
still 0/5. No new fit or registration occurred in the routing session.

The honest ending is therefore not “the model finished Pokémon.”
It is that learned combat, preparation, recovery and navigation are becoming a
connected player—and the remaining work can be named without hiding what failed.
Future chapters should continue this history rather than replace it.
