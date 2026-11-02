# Historical narrative edition — superseded September 22, 2026

Preserved before chronological reconstruction. Status and future-work statements describe this edition, not current authority. Relative links below were relocated; the original body is otherwise retained.

# Video narrative: learning to battle is not yet learning to finish Pokémon

An AI-assisted engineering project directed by Pete Andrews. Editorial outline updated
September 22, 2026; the earned story run is stopped before Giovanni, with seven badges.
Use the [research record](../research-retrospective.md) for claim boundaries and source links.

## Opening: a strong battler meets a floor tile

“We taught a model to choose attacks and switches. It beat Blaine. We brought three
reserves up to level 39. Then a spinning floor tile stopped the whole player.”

This is the central tension: useful learned decisions depend on observation, navigation,
resources and recovery that work together. Shared routing repairs have since connected
one earned gym win and recovery; Giovanni has not been fought. Do not tease a completed
autonomous Red run.

Suggested visuals: retained party and badge reads, the learned decision log, and a diagram
of expected versus observed spinner endpoints. These are saved evidence or labeled
reconstructions, not live play. Use actual gameplay footage only if it exists.
[Latest evidence](../evidence/red-forced-motion-gym-2026-09-22.json).

## Chapter 1 — What are we actually building?

The destination is a player that finishes Red and builds a verified shared Pokédex, then
learns unfamiliar games. It is not an LLM secretly deciding every button. Small learned
models choose supported goals and battle actions; deterministic code reads semantic game
state, navigates, operates menus and checks results. Some story and preparation choices
still come from support code or the operator. Call that out on screen.

A teacher may construct isolated training situations, including edited Pokémon and
resources. That permission does not extend to the final player. TRAIN, DEVELOPMENT and
the future fresh-run exam are different sources of evidence. A previous checkpoint-based
Champion finish is not the fresh model-directed completion we still owe.
[Architecture](../architecture.md) · [Mission](../../MISSION.md).

## Chapter 2 — The teacher was finishing a different problem

Early labels judged an opening action followed by a strong teacher. The deployed model
had to finish its own battles. Changing continuation could change which opening was best.

Candidate J improved an unused generated-team comparison from 7/24 to 9/24 wins, still
losing 15. Later K changed attack-versus-switch control. On eight paired TRAIN-related
battles both models won 8/8; K reduced faints 11→5, decisions 180→165 and PP 101→92,
while losing more HP. Show the tradeoff, not a victory montage without denominators.
[Learning account](../project-narrative.md) ·
[K evidence](../evidence/red-battler-k-control-result-2026-09-20.json).

## Chapter 3 — Keep the loss in the story

The first main-player battle integration stopped when Wartortle fainted. A retained-state
continuation let J choose a replacement and continue; it lost, blacked out and paid the
normal cash penalty. No reset or teacher rescue changed that ending.

Two natural starts later supported six-member execution: J and K each won 4/4 measured
cases, with 210 combined model decisions. Both origins faced the same early opponent
roster; K's 16 faints versus J's 15 rule out a simple “better in every way” claim.
[Loss](../evidence/red-battle-lifecycle-continuation-2026-09-19.json) ·
[Natural execution](../evidence/red-natural-six-qualification-2026-09-20.json).

## Chapter 4 — Choosing what to do after an unsuccessful search

Show the separate collection lineage: seven model decisions, five normal failed searches,
one successful boxed Abra→Mr. Mime exchange, then an encounter-cap stop. All 3,000 spent
remained counted. Controllers performed travel, storage and exchange after goal selection.

That development save has 109/124 native registrations and 11,968 cash. It is not the
seven-badge story save. Never combine their badges, money or Pokémon into a fictional
single successful run. Nor does 109/124 mean the project is 87.9% complete.
[Integrated episode](../evidence/red-integrated-player-2026-09-21.json).

## Chapter 5 — Better training error did not mean better battle choices

Status experiments exposed repeated confusion, mistimed recovery and expensive loops.
Retain the rejected candidates: an early withheld 3/8 versus K's 5/8; a balanced 13/32
versus 12/32 at 196 versus 76 decisions; then 18/32 versus 20/32 after learner continuation.
Predicting a move's timing-dependent effect was a separate, narrower success.

The later additive actor won 72/128 versus K's 66, but took 349 decisions versus 276.
It failed the original efficiency screen. Pete accepted that exact frozen actor for
bounded story DEVELOPMENT, not as a retroactive pass or a final-player promotion.
[Status](../evidence/red-status-learning-2026-09-21.json) ·
[Balanced](../evidence/red-balanced-status-learning-2026-09-21.json) ·
[Closed-loop](../evidence/red-closed-loop-status-learning-2026-09-21.json) ·
[Timing](../evidence/red-timing-effect-learning-2026-09-22.json) ·
[Admission](../evidence/red-additive-story-admission-2026-09-22.json).

## Chapter 6 — Real story progress, with the boundaries visible

The admitted actor beat seven Cinnabar gym trainers and Blaine: eight wins, 48 choices,
no faints or illegal actions, and 18,613 cash earned. Blastoise and Dugtrio fought.
Travel, trainer selection and healing remained supporting machinery. Native Dig and Fly
escaped the Mansion; that did not solve generic switch-aware puzzle routing.
[Evidence](../evidence/red-learned-blaine-2026-09-22.json).

Blaine's automatic readiness request then brought Dugtrio, Farfetch'd and Jolteon to 39.
Forty outings produced 160 wild encounters, 153 wins, seven nonwinning exits and 496
learned choices. Two faints and 32 status changes were recovered. Snorlax gained levels
incidentally through switching; no one had deliberately selected it as a training target.

These are earned game levels, not a new model fit. K chose knockout combat; targets,
trainees, venues and healing remained support. The operator's Route 15→16 change was
sequential, not a controlled experiment proving one venue universally superior.

## Chapter 7 — The failure that defines the next piece of work

A Fly arrival legitimately opened Viridian Gym but tripped an overly strict event check.
The narrow repair used retained states and tests, without replaying the flight.
A subsequent route settled after a spin but reached (11,18), not predicted (2,18).
Longer waiting could not supply the missing forced-motion geometry.

The audit caught another distinction: visiting a Center with a full party had not
registered its recovery anchor. It remained Celadon, despite a support label claiming
Viridian. Preserve the incorrect label and correction as an example of checking what
the game actually did. That was stage283; Giovanni remains ahead.
[Retained outcomes and correction](../evidence/red-giovanni-readiness-2026-09-22.json).

The subsequent shared routing repair includes intermediate hazards and settled endpoints.
A separate feasibility oversight stopped one approach before combat and was also repaired.
Stage285 then won a gym battle in nine learned choices despite Jolteon fainting. Native
healing restored everyone and registered Viridian; cash reached26627. It is forward
progress, not a replay or proof of all spinner paths. More gym clearance is still needed.

## Closing — The next result must be earned

Next: continue bounded gym clearance from the healed stage285 toward Giovanni.
Then come remaining story, resource and collection integration,
broader qualification, and the fresh Red exam. All five final-run criteria remain open.
Compatible hack, Blue/shared collection, Crystal and Emerald are future work, not results.

The retrospective should show both kinds of progress: a model becoming useful and the
engineering required to let it act. A possible paper needs a literature comparison,
reproducible protocols and stronger controlled evaluations; uniqueness is not established.
Do not claim measured coding-agent usage savings without actual usage records.

Suggested end card: current result / current blocker / next falsifiable test, with links
to the [roadmap](../model-first-roadmap.md), [project story](../project-narrative.md) and
[research record](../research-retrospective.md). Credit Pete's direction and AI coding
contributions explicitly. This outline does not assert that video assets already exist.
