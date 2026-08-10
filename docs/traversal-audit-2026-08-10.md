# Knowledge-to-action audit — 2026-08-10

## Executive verdict

The cartridge-derived navigation direction is now technically credible, but it is not yet a
general player. Red and Blue produce the same complete static land graph, and one generated ledge
route has been falsified successfully in a clean, source-bound live run. The system can therefore
answer “which input crosses this ordinary tile or one-way ledge?” on a single map without consulting
a typed route.

It still cannot compile an arbitrary multi-map objective into one continuous executable plan. The
highest-priority gap is no longer another Red completion replay or another static collision table.
It is the bridge between the macro map graph, the local coordinate graph, and a closed-loop runtime
that reobserves moving objects and interruptions.

Several learned decision heads already have real Red authority in battle and team development. No
learned navigation head has this authority, and the current work does not claim that a model learned
pathfinding. That is intentional: shortest-path search over cartridge truth is a better mechanic
than asking a neural network to memorize Kanto. The model should learn decisions the graph cannot
answer—where to go, which capability to acquire, when to recover, and how to respond when execution
changes the state.

## What is proved now

| Layer | Current evidence | Authority boundary |
| --- | --- | --- |
| Macro topology | 220 reachable maps, 78 reciprocal connections, 917 ordinary warps | Connectivity only; story and field requirements are not permission |
| Static terrain | 48,216 standable coordinates in each cartridge | Initial land geometry, not current object or script state |
| Static local traversal | 154,653 directed land edges, including 749 directed coordinate ledge transitions; 1,152 otherwise-passable elevation-pair transitions removed | Walk, ledge direction and land elevation only |
| Stateful-mechanic inventory | 8 ledge rules, 11 land-pair rules, 3 water-pair rules, 9 Cut block swaps, and 25 initial boulders across 9 maps; 21 are Strength-enabled | Cut, Surf and Strength are decoded facts, not executable edges |
| Cross-cartridge comparison | Full static rule tables, initial boulders and all local graphs agree between exact-fingerprint Red and Blue | Generation I structural evidence, not cross-generation transfer |
| Live falsification | Thirteen generated Route 1 approach inputs reached a decoded ledge; `down` landed two squares away at `(28, 10)` and `up` could not reverse it | One clean uncounted probe, not completion-run authority |

The 749 figure is a count of directed coordinate transitions, not 749 unique physical ledges. The
public records are [the complete traversal extraction](evidence/traversal-rules-2026-08-10.json) and
[the source-bound live ledge probe](evidence/route1-cartridge-ledge-probe-2026-08-10.json).

## Code strengths

1. **The search core is genuinely game-neutral.** `local_router.py` knows coordinates, exact
   actions, transition kinds, requirements and costs. It imports no Pokémon or Generation I code.
2. **The title adapter fails closed.** `gen1_traversal.py` projects only ordinary land movement,
   ledges and elevation restrictions. It inventories Cut, water rules and boulders without turning
   possession of a capability into a fictional open edge.
3. **Actions and semantics remain separate.** A ledge edge says `action="down"` and
   `kind="ledge"`. An earlier draft collapsed those into “hop ledge” and lost the controller input;
   the type now makes that mistake harder to repeat. Every edge must name an action explicitly.
4. **The terrain contract now retains exact tile identity.** Walkability alone cannot distinguish a
   ledge, water boundary or elevation pair. Terrain grids also reject empty, ragged or misaligned
   coordinate planes.
5. **Parser tests use independent byte fixtures.** The traversal tables and variable object-event
   strides are exercised with literal offsets and bytes rather than fixtures built from the
   constants under test.
6. **Live evidence is bound to code.** The probe requires a clean tracked tree, proves the working
   executable source bundle equals the commit, records that commit and bundle hash, releases every
   control, and refuses a changed ROM-adjacent artifact.

## Ranked gaps and risks

### P0 — the macro and local graphs do not compose

`gen1_maps._read_warps` currently discards byte three of each four-byte warp record: the destination
warp index. That index identifies the arrival square on the next map. Connection records are eleven
bytes, but the decoder retains only the destination map and the direction bit; it discards the
alignment and coordinate data that determine where a border crossing arrives. A `MacroPath` can
therefore name the next map and departure warp while still being unable to seed the next local path.

The next implementation should retain both endpoints of every ordinary warp and the exact legal
source/arrival bands for every connection, compare the complete structures across Red and Blue,
and expose one composed `RoutePlan` containing local actions plus map transitions. A generated
Pallet → Route 1 → Viridian → Pokémon Center probe would exercise a connection and a warp in one
continuous plan.

### P0 — current obstruction is not initial cartridge obstruction

`map_object_events` reads initial ROM objects. It does not say which objects are hidden by event
flags, where a wandering NPC is now, or where a Strength boulder moved. `RawGameState` exposes map,
coordinate, badges, party moves and story-event bytes, and the address catalog knows toggleable
object flags, but the ordinary state reader does not expose a traversal overlay or current sprite
coordinates.

The executor needs a narrow runtime traversal observation: current movement mode, visible object
coordinates and stable input readiness. It should plan a short prefix, execute one edge, reobserve,
and either continue or replan. Wild battles and moving people are state transitions, not reasons to
copy another fixed route exception.

### P1 — Surf is a movement mode, not an edge label

The water-pair exception table is decoded, but the main water collision rules, entry/exit stances,
badge-plus-known-move capability and live walk/bike/surf state are not combined. Surf should be the
first field capability implemented after route composition because its movement-mode abstraction
is common across later games.

### P1 — Cut mutates the map

The nine block replacements are known. A Cut plan still needs the current block grid, facing and
interaction stance, badge-plus-known-move evidence, post-action tile recomputation and the fact that
the mutation is map-state dependent. Representing Cut as a permanently available edge would be
incorrect.

### P1 — Strength is a puzzle state space

Twenty-one initial boulders are pushable, but a useful planner needs current boulder coordinates,
the game's two-attempt push behavior, player and object collision, holes/switches, and a state key
that changes after every push. This belongs in a bounded puzzle search, not a static capability mask.

### P1 — story scripts still overapproximate the world

Static headers connect places whose doors or gates may be closed by story state. Event flags and
semantic facts should filter passage availability through title-specific predicates. Unknown script
conditions must remain unavailable rather than becoming a high-cost fallback.

### P2 — two local-routing APIs coexist

`navigation.GridMap` still serves older skills, while `local_router.LocalGraph` carries exact actions,
transition kinds and capabilities. Extending both would create two sources of movement truth. Keep a
compatibility adapter for existing bounded skills, but make the cartridge-aware graph the single
new route representation.

### P2 — the probe uses chapter-private execution helpers

The ledge probe legitimately reused the qualified opening and Route 1 wild-flee machinery, but it
imports private helpers from `play.py`. The composed-route milestone should extract a public,
game-neutral closed-loop overworld executor rather than grow another chain of probe-only imports.

### P2 — the new decoder has not yet received a mutation score

The fixtures are materially better than the earlier decorative suites, but this project has already
learned that green tests can survive broken readers. Before generated routing receives completion-run
authority, mutate table offsets, strides, direction bytes, tile-pair application, warp destination
indices and connection alignment fields and require each mutation to fail.

## Ordered next milestones

1. **Decode complete passage geometry.** Retain destination warp indices and connection alignment;
   prove Red/Blue equality and independently fixture every byte stride.
2. **Compose and execute one multi-map route.** Add a game-neutral `RoutePlan`, a short-prefix
   closed-loop executor, dynamic blocker observations and bounded wild-interruption recovery. Prove
   Pallet → Viridian Center live without typed route directions.
3. **Add Surf as a stateful mode.** Decode land/water eligibility, derive the capability from badge
   plus party moves, observe live movement mode, and falsify board/move/disembark behavior.
4. **Add Cut as a block-state transition.** Rebuild the affected local graph after the observed
   mutation and prove one reversible-by-map-reload tree crossing.
5. **Add Strength as bounded puzzle search.** Observe boulder positions, plan legal pushes, and prove
   a captured-state Victory Road subproblem before touching a completion run.
6. **Filter story-gated passages.** Start with a small gate whose closed and open states can both be
   established and observed independently.
7. **Collect navigation decision data.** Record semantic destination candidates, route edges,
   action affordances, interruptions and outcomes. Do not train on repeated raw movement frames as
   though shortest-path arithmetic were strategy.
8. **Run the Crystal microbenchmark.** Only after the route-plan and runtime-observation contracts
   are game-neutral should Crystal supply its own thin adapter for one battle, one local route and
   one training choice.

## Admission gate for completion-run routing

Generated routing should remain outside a Red completion run until all of the following are true:

- passage endpoints compose across at least one connection and one warp;
- the executor reobserves every step and has bounded interruption handling;
- dynamic objects cannot be treated as permanent terrain or silently ignored;
- required field capabilities are derived from observed badge and party state;
- every unknown story or puzzle condition fails closed;
- the relevant parser mutations are killed; and
- at least two clean source-bound live routes pass without typed direction fallbacks.

That gate keeps the new layer useful for the final model rather than turning it into another brittle
Red answer key.
