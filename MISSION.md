# Mission

Every agent and every contributor reads this first. If a proposed change does not serve the goal
below, it does not belong in this repository — however good it looks on its own terms.

Then read [NORTH_STAR.md](NORTH_STAR.md). It turns this mission into mandatory task filters,
time boxes, stop rules, and a full-run gate. Authority flows from mission to north star to the
active model-first roadmap; no newer checkpoint can reverse that order.

## The goal

**Create a model that can actually play Pokémon.**

Not a model that completes Pokémon Red. Not a route that reaches the Hall of Fame reliably. A model
that plays the game: chooses what to do, reacts when things differ from what it saw in training, and
carries that competence into games it has never seen.

Concretely, success is:

1. **A living Pokédex across every mainline title.** One accumulating registry of caught species,
   filled by however many runs, versions, and trades it takes. A single cartridge cannot hold a
   complete Pokédex; completion is a property of the collection.
2. **Ideally 100% completion of each title.** The dex is the spine, because collecting everything
   forces the system to exercise the whole game rather than the shortest path through it.
3. **Transfer.** Knowledge earned in one generation reduces the teaching required for the next.

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
