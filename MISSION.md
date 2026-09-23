# Mission

Every agent and every contributor reads this first. If a proposed change does not serve the goal
below, it does not belong in this repository — however good it looks on its own terms.

Then read [NORTH_STAR.md](NORTH_STAR.md). It turns this mission into mandatory task filters,
time boxes, stop rules, and a full-run gate. Authority flows from mission to north star to the
generated [active product state](ACTIVE_PRODUCT_STATE.md), then the model-first roadmap; no newer
checkpoint can reverse that order. The active state is the compact answer to what work is allowed
now and which measured learning output must result.

## The goal

**Create a model that can actually play Pokémon.**

Not a model that completes Pokémon Red. Not a route that reaches the Hall of Fame reliably. A model
that plays the game: chooses what to do, reacts when things differ from what it saw in training, and
carries that competence into games it has never seen.

Concretely, success is:

1. **A shared, registered Pokédex across mainline titles.** One accumulating registry of species
   verified as caught/owned through capture, evolution, gifts or legitimate trades across runs.
   Each species needs global credit once, not a simultaneous living specimen of every form.
   Per-save Pokédex registration and physical party/box inventory remain separate facts.
2. **Ideally 100% completion of each title.** The dex is the spine, because collecting everything
   forces the system to exercise the whole game rather than the shortest path through it.
3. **Transfer.** Knowledge earned in one generation reduces the teaching required for the next.

The delivery gate revised by Pete on September 15 is **complete Red's legitimate native route
before any ROM hack**: a fresh start-to-finish, model-directed run, concurrent Champion and
Hall-of-Fame evidence, and the declared 124-species selected Red route registered in that run's
save. A fixed walkthrough with random timing or a stitched checkpoint demonstration does not
satisfy this gate. Deterministic mechanics may support the player, but consequential progression
and resource decisions must belong to the model under declared authority.

An additional **Blue run is planned**, contributing missing species to the same shared registered
Pokédex rather than repeating completed lines solely for global credit. Its scheduling is separate
from Red's unchanged native-route gate. Species requiring unavailable trading, event access or
other external means may instead be obtained legitimately in a later title; do not block Red on them.
Version, cable-trade and event dependencies remain explicit legitimate gaps; shared credit never
fabricates a local Red flag. Mew is deferred until a later legitimate source. Red/Blue link play
may be attempted after model completeness, but an unavailable emulator link does not block the
ROM-hack gate: record the dependency and earn it in a later title instead. The final player and
official completion run may not cheat or edit a save. Training may use disclosed, isolated state
interventions, including money overrides, to teach or test a mechanic without a resource bottleneck.
Such assisted results are not legitimate funding, fresh-run completion or ordinary economy labels;
the model must never receive an action that can perform the intervention itself.
After that gate: a compatible unfamiliar Red ROM modification, then Crystal, continuing the
shared registered Pokédex through at least Emerald. Report initial transfer and adaptation
separately. Red experience should reduce teaching, not guarantee immediate success.

## Explicit scope revision — September 9, 2026

Pete retired the living-specimen completion requirement and the level-100 stretch target.
After story completion, catch a useful missing line, evolve only as far as needed for missing
registrations, deposit when it is no longer needed, and pursue the next gap. No arbitrary
completion level is required. Before the story ends, develop a capable team as necessary.

A shared ledger prevents Blue and later runs from repeating already-credited evolution lines
solely for global completion. An already-recorded species may still be needed for the current
team or as a prerequisite for a new branch. Duplicate captures are allowed without an intrinsic
duplicate penalty; first-time credit is not awarded twice and actual resource costs remain visible.
No automatic releases or destructive save edits are authorized by this change.

The new goal does not retroactively alter old learning receipts, rewards or contracts. The
versioned registered-only runtime and shared ledger must be integrated before new collection
runs. [Scope and migration plan](docs/shared-pokedex-registration-plan.md).

## Why the Pokédex, and not just beating the game

Beating Pokémon Red is easy and we can already do it. The current teacher finishes the game
repeatedly with Champion and Hall-of-Fame evidence. That result is worth almost nothing as
*training data*, and the measurements prove why.

A recorded run finished the game with a level-87 Blastoise that erased the Champion's entire
six-Pokémon team in **six turns — one apiece**. The other five party members never entered the
battle. Every recorded decision in that fight was "use the strongest move," and it was always
correct. There is nothing in that data for a model to learn.

Collecting the Pokédex cannot be done that way. It requires encounter tables, every evolution
method, capture judgment, storage management, trading, version differences, and the areas a
completion route deliberately skips. Those are the skills that transfer — and later generations
stack breeding, held items, day/night, and abilities on the same foundations.

**So the Pokédex is not a stretch goal bolted onto a completion project. It is the thing that forces
the system to learn to play.**

## What this rules out

- **Optimizing Red completion reliability.** More seeds passing a fixed route produces more of the
  same empty demonstrations. Reliability of a teacher that makes no interesting decisions is not the
  bottleneck; the decisions are.
- **Overleveling.** A party far above its opposition removes every decision from every battle. It is
  the same failure as the single carry, wearing a six-member costume.
- **Route tricks that do not generalize.** A fixed walk string, a cursor exception, or a
  species-specific hack solves Red and teaches nothing. Prefer the reusable concept even when it is
  more expensive.
- **Metrics that cannot embarrass you.** Twelve committed receipts reported the *Champion's* party
  levels as our own for five evaluation versions, because the number looked like what everyone hoped
  for and nobody checked it. Prefer measurements that can come back wrong.

## How to tell whether work serves the goal

Ask: *does this increase the number of real decisions in the demonstrations, or the breadth of
mechanics the system exercises?*

If neither, it is probably Red maintenance. Red maintenance is sometimes necessary — a route that
cannot finish produces no data at all — but it is never the objective.
