# Model-first development roadmap

Status: active strategy as of 2026-08-14. This document supersedes the execution order in older
dated roadmap and handoff checkpoints. Historical evidence remains valid; historical instructions
to harden or replay the full deterministic route do not.

Read [MISSION.md](../MISSION.md) and [NORTH_STAR.md](../NORTH_STAR.md) first.

## Product definition

The target is a transferable hierarchical Pokémon-playing agent, not a perfect Pokémon Red macro.
It must eventually:

- understand semantic game state rather than memorize addresses or button strings;
- decide story, collection, evolution, training, resource, storage, recovery, and exploration goals;
- navigate and replan when the world differs from a demonstration;
- battle, catch, train, rotate a party, and manage resources efficiently;
- solve field-move, dungeon, legendary, and story-flag prerequisites;
- maintain a living-Pokédex plan across versions, trades, and legitimate event inputs;
- carry useful knowledge into another title with less teaching than starting from zero.

The likely product is a hierarchical system with a shared semantic representation, reusable skill
policies, a goal planner, persistent memory, and thin game-specific observation/mechanics adapters.
It may contain several learned heads; “one model” does not require one undifferentiated network.

## Strategic reset

The deterministic teacher is complete enough to serve as an oracle and state generator. Further
teacher-route reliability work is maintenance and is not an active lane. Development now happens in
short authenticated scenarios. Save states and snapshots are permitted for private development and
training; clean power remains mandatory only for the official evaluations defined by the completion
contract.

No milestone below may silently expand into a full game replay. Each milestone has an exit gate and
a stop rule.

## Learning approach

Use four complementary stages:

1. **Supervised initialization:** fit semantic choices from audited teacher demonstrations and
   counterfactual candidate sets.
2. **Interactive correction:** let the model act in short scenarios; the teacher intervenes only at
   declared unsafe or irrecoverable boundaries. Retain intervention and outcome data.
3. **Outcome learning:** compare choices by success, efficiency, resource cost, and safety rather
   than exact teacher imitation. Use causal replay or reinforcement learning where an action's
   quality cannot be inferred from a label.
4. **Progressive authority:** move one bounded skill at a time from shadow, to intervention-backed
   control, to teacher-free control on unseen scenarios, then to multi-skill episodes.

This is a DAgger-like curriculum with outcome-based refinement. It avoids both pure button cloning
and learning an entire game from random inputs.

## Milestone 0 — preserve and explain the pivot

Purpose: make the failed Red shadow run useful and ensure no agent repeats it blindly.

Work:

- preserve its path-free public receipt and private corrections;
- recover or explicitly mark unavailable the precise runtime cause;
- cluster 600 battle disagreements by unique semantic state, moveset, teacher choice, and model
  choice;
- distinguish likely model mistakes from arbitrary first-usable teacher choices;
- measure the Saffron collision/retry pattern and the training recovery policy;
- add exact failure reasons, heal counts, battle counts, party levels, and final state to future
  dashboards and receipts;
- record the decision in the handoff, audit, roadmap, narrative, and review log.

Exit gate:

- every retained claim is reproducible from a path-free receipt or explicitly labelled inference;
- the correction cluster has an actionable taxonomy;
- the next experiments can start from bounded states without replaying Red.

Stop rule: one focused work session. If the exact exception was not retained, record that fact and
fix future observability; do not reconstruct it through another full run.

Learned authority gained: none. This is the final permitted maintenance milestone before model-first
experiments.

## Milestone 1 — authenticated scenario laboratory

Purpose: turn hours-long failures into seconds- or minutes-long experiments.

Build a private development-state bank and a ROM-free public catalog for:

- local navigation and displaced starts;
- wild and trainer battles;
- party rotation and grinding;
- healing, resupply, storage, and recovery decisions;
- catching and evolution;
- story and collection goal selection;
- representative puzzles and field-move prerequisites.

Each scenario declares semantic initial state, allowed actions, randomization dimensions, independent
success verifier, maximum actions/frames, intervention policy, and privacy-safe result schema.
Development snapshots never become sealed-test evidence.

Infrastructure requirements:

- deterministic replay when needed, with private snapshot restore for iteration;
- randomized action timing, RNG offsets, positions, teams, HP/PP, inventory, and candidate order;
- parallel headless workers after a measured CPU/memory benchmark;
- interruption-safe episode storage on the external drive;
- dashboard aggregation across workers;
- exact exception messages and bounded failure classifications.

Exit gate:

- at least one scenario family for navigation, battle, and training can execute hundreds of episodes
  without a full-game replay;
- partitions and state lineages are explicit;
- test scenarios remain untouched during fitting;
- a failed episode identifies its exact guard and last semantic state.

Stop rule: do not add another scenario family until the first three produce learner updates and
unseen evaluation results.

Learned authority gained: none directly; this unlocks every later authority transition.

## Milestone 2 — closed-loop local navigation

Purpose: replace fixed direction strings and wall retries with reusable movement competence.

Architecture:

- title-specific observation adapter exposes map, position, passability evidence, warps, and
  relevant capabilities;
- shared planner proposes a candidate path with traversal requirements;
- closed-loop controller acknowledges each movement outcome;
- collision, turn-only input, displacement, NPC blocking, unexpected warp, and script start trigger
  replanning rather than repeated blind input;
- the model ranks destinations and recovery choices while the verifier checks arrival.

Training curriculum:

- randomized starts and destinations within towns, routes, buildings, caves, and multi-room
  corridors;
- deliberate one-tile displacements and moving-NPC blocks;
- later add ledges, Cut, Surf, Strength, doors, and story flags as explicit capabilities;
- Red development maps first, then the already-qualified Crystal corridor as an early transfer
  probe.

Provisional exit gate, frozen before evaluation:

- at least 95% arrival on unseen randomized local tasks;
- zero unbounded loops;
- median executed path no more than 1.25 times the shortest currently traversable path;
- no more than one blocked retry per 100 acknowledged movement steps, excluding deliberate
  dynamic-obstacle probes;
- at least 95% recovery from a one-step displacement;
- measurable above-zero zero-shot success on the Crystal corridor before adaptation.

Stop rule: if two iterations improve a Red route but not randomized displacement recovery, stop
patching that route and revise the representation or planner.

Learned authority gained: local destination routing and movement recovery.

## Milestone 3 — outcome-aware battle policy

Purpose: learn to win and preserve resources, not imitate an arbitrary move slot.

Work:

- audit the first live correction set and collapse repeated semantic duplicates;
- represent battle objective, legal moves, typing, status, stages, HP, PP, switching opportunity,
  capture intent, and protected-party constraints;
- retain teacher choice as one signal, not the truth;
- compare disputed choices through bounded causal replay;
- train against outcome targets such as victory, turns, damage taken, PP cost, faint risk, capture
  success, and objective satisfaction;
- introduce trainer and wild scenario randomization before any full-route authority.

Provisional exit gate, frozen before evaluation:

- 100% legal choices;
- at least 95% objective success on unseen bounded battles;
- less than 5% teacher intervention on supported unseen states;
- no regression on required-move, capture, escape, or protected-party safety cases;
- efficiency no worse than the teacher on a preregistered composite of turns, HP, and PP;
- disagreement clusters are judged by outcomes rather than forced into agreement.

Stop rule: if a label audit shows the teacher's choice is outcome-equivalent or worse, do not add it
as a correction target. Change the objective or mark the choices equivalent.

Learned authority gained: move, switch, catch, and flee choices inside bounded battles.

## Milestone 4 — efficient party development

Purpose: learn the transferable grinding, evolution, and party-rotation skill required by every
living Pokédex.

Replace the current 90%-HP/zero-faint routine with a policy that reasons about:

- expected survival on the next encounter;
- remaining useful PP and status;
- all healthy trainees, not just the current lead;
- safe reserves and escape options;
- experience yield and evolution requirement;
- travel and healing cost;
- venue encounter band and matchup distribution;
- party-wide completion goals.

The starter may remain an emergency escort, but should not be the default fighter once it has met
its role target. Rotate to another viable trainee before healing. A faint is a costly outcome, not an
automatic catastrophe; blackouts and unrecoverable losses remain hard failures.

Provisional exit gate, frozen before evaluation:

- at least five completed training battles per Center visit on the median unseen episode;
- at least three times the current experience-per-frame baseline;
- zero blackouts and bounded faint rate;
- every selected trainee gains experience or the policy explains a verified blocker;
- evolution targets complete across randomized encounter timing;
- the policy recognizes when a different venue is more efficient;
- Red trainees and a bounded Crystal trainee task use the same semantic policy interface.

Stop rule: if a change lowers Center visits by using the overlevelled starter more often, reject it;
it improved the metric by deleting the learning problem.

Learned authority gained: trainee, venue, fight/rotate/heal/stop, and evolution scheduling choices.

## Milestone 5 — online hierarchical goal loop

Purpose: connect the already-fitted goal and destination components to real decisions and persistent
memory.

The online loop must:

1. observe semantic state and collection ledger;
2. propose currently achievable goals;
3. rank goal and destination candidates;
4. invoke a learned or verified skill;
5. independently verify outcome;
6. update memory, capabilities, resources, and blockers;
7. replan after success, failure, or unexpected state.

Do not expose expected labels to the actor. A verifier may confirm results but may not replace an
actor choice.

Exit gate:

- model controls at least three consecutive heterogeneous goals in unseen Red development episodes;
- episodes include meaningful branching and changed resources;
- no expected route or objective list is passed to the actor;
- failures produce replanning rather than a scripted reset;
- teacher intervention rate and reason are visible;
- Crystal receives an early zero-shot goal-selection probe before adaptation.

Stop rule: a successful episode with only one executable candidate per decision is coverage, not
planning evidence. Do not promote on it.

Learned authority gained: goal selection, destination selection, and recovery/replanning.

## Milestone 6 — living-Pokédex dependency planner

Purpose: make collection the organizing objective rather than a postgame add-on.

The planner consumes cartridge-derived encounter, evolution, gift, trade, fossil, static encounter,
version, and prerequisite graphs. It maintains separate ledgers for seen, registered, living,
evolved, stored, traded, version-blocked, event-blocked, and level-target completion.

Red progression layers:

1. complete every species obtainable on one Red cartridge under the declared solo contract;
2. coordinate legitimate Red/Blue choices and trades for version and mutually exclusive gaps;
3. recognize event-conditioned species without fabricating availability;
4. retain a living specimen where the completion contract requires one;
5. train/evolve only as much as the current acquisition dependency requires.

The same representation must accommodate later mechanics: breeding, happiness, time of day, held
items, roaming encounters, contests, abilities, and multi-version transfers.

Exit gate:

- every missing Red target has a derived acquisition plan or an explicit external blocker;
- planner replans after a failed catch, depleted item, full box, changed evolution state, or trade;
- bounded acquisition chains complete without a hand-written species route;
- collection progress is independently verified from party and storage;
- the dashboard explains the next target and dependency chain.

Stop rule: no species-specific execution patch is accepted until the general acquisition/evolution
mechanic has been represented. Unique legendary puzzles may use game data, but the planner must
still reason about their prerequisites and one-shot risk.

Learned authority gained: collection target, dependency ordering, capture preparation, evolution,
storage, and trade scheduling.

## Milestone 7 — integrated Red curriculum

Purpose: compose learned skills before spending another clean-power run.

Progress through increasingly long authenticated development episodes:

- local task;
- one chapter;
- two heterogeneous chapters;
- early-game segment;
- midgame segment;
- League preparation and completion;
- collection chains spanning story gates;
- whole-game intervention-backed run;
- teacher-free whole-game evaluation.

Each promotion requires unseen timing/RNG perturbations and starts not used for fitting. “Seed” in
Red means controlled timing, action, and state perturbation; the cartridge has no ordinary user
seed selector.

Full clean-power authorization requires all earlier component gates plus:

- a preregistered authority map and intervention policy;
- predicted runtime and storage cost;
- exact failure diagnostics;
- a result that changes a promotion decision;
- explicit roadmap authorization.

Exit gate:

- story completion under declared learned authority across multiple unopened perturbations;
- no fixed full-route arrow sequence supplied to the actor;
- demonstrated recovery from at least one unexpected but supported state;
- collection planner advances the solo Red target rather than stopping at Hall of Fame;
- intervention and efficiency metrics remain within frozen bounds.

Learned authority gained: composed Red play.

## Milestone 8 — Crystal transfer, early and honestly

Purpose: measure whether Red knowledge reduces teaching, not build a second walkthrough.

Preserve the frozen Crystal v2 partitions. Before opening them, use only separately declared
development tasks for:

- the already-qualified local corridor;
- one battle choice;
- one trainee/venue choice;
- one goal choice;
- one collection dependency.

Compare the same shared model initialized from Red against a zero-initialized control with identical
adapters, preprocessing, updates, and budgets. Add only thin Crystal observation and mechanic
bindings; do not encode a Crystal route.

Exit gate:

- all sealed protocol preconditions hold;
- zero-shot results are committed before teaching;
- Red initialization is compared against the control at identical adaptation budgets;
- shared-policy failures are separated from missing game-specific capabilities;
- transfer claims follow the frozen paired endpoint.

Stop rule: if Crystal requires a game-specific workaround for a shared concept, first test whether
the shared representation is missing information. Do not hide failed transfer behind a second
teacher script.

Learned authority gained: cross-title reuse and bounded adaptation.

## Milestone 9 — multi-game completion platform

Purpose: scale from two games to the declared product.

Add titles by implementing the smallest required adapter for semantic observation, mechanics,
storage, acquisition data, and independent verification. Shared policies, memory, planning, and
dashboards remain game-neutral. Each new generation expands the capability vocabulary rather than
forking the agent.

Long-term completion evidence reports:

- story and title-specific completion flags;
- living-Pokédex state across versions and storage;
- recognized trades and event requirements;
- transfer performance before and after adaptation;
- teaching cost relative to earlier games;
- remaining unsupported mechanics.

## Dashboard redesign

The observatory should prioritize learning and generalization rather than elapsed route progress:

- episode throughput and worker health;
- train/development/test partition counts;
- success on seen and unseen scenarios;
- teacher interventions by reason;
- collision rate, path overhead, and recovery success;
- battle objective success and HP/PP/turn efficiency;
- experience per frame, battles per heal, rotations, faints, and blackouts;
- goal chains completed and replans;
- living-Pokédex acquisitions and blocker categories;
- Red-to-Crystal transfer matrix;
- exact source/model/data identities and authority boundaries.

Live game video remains useful, but it is supporting evidence rather than the primary progress
metric.

## Current order of execution

1. Milestone 0: failed-run postmortem and future diagnostic retention.
2. Milestone 1: scenario laboratory for navigation, battle, and training.
3. Milestones 2–4 in parallel only after the laboratory supports them; integrate one at a time.
4. Milestone 5: online hierarchy.
5. Milestone 6: living-Pokédex planner and bounded acquisition chains.
6. Milestone 8 development probes may begin after Milestones 2–5 have shared interfaces; frozen
   Crystal evaluation remains sealed until authorized.
7. Milestone 7 full Red integration only after bounded gates pass.
8. Milestone 9 follows demonstrated Red-to-Crystal transfer.

## Expected scale

The scenario laboratory and first useful learned-skill results should be measured in days, not in
one hours-long replay per change. An integrated learned Red player remains substantial work. A
multi-generation, living-Pokédex agent is a longer research program. Roadmap estimates are revised
from measured scenario throughput, never from optimism or the fact that a teacher route already
works.
