# Knowledge-to-action audit — 2026-08-10

## Executive verdict

Static multi-map composition is now proved, including one continuous live route. The repository can
read exact connection and warp endpoints from Red or Blue, select reachable passage coordinates,
join local searches across map boundaries, and emit controller actions without consulting a typed
Kanto corridor. A clean source-bound run executed 86 generated actions over four maps and entered
the Viridian Pokémon Center at the cartridge-declared coordinate.

That is a real architectural milestone, not learned navigation. The remaining blocker is a shared
closed-loop runtime: current NPC positions, script state, movement mode and interruptions must be
observed after every action and allowed to invalidate a static candidate. The model should learn
strategic destination and recovery choices; graph search should continue to own exact geometry.

## What is proved now

| Layer | Current evidence | Authority boundary |
| --- | --- | --- |
| Macro topology | 220 reachable maps and 78 reciprocal connections in both cartridges | Connectivity is not proof that a story- or capability-gated passage is open |
| Passage geometry | 1,484 exact connection transitions, 558 ordinary warp arrivals, 242 indexed dynamic returns and 2 scripted lift exits; full Red/Blue structures agree | Dynamic returns need retained outside-map state; lifts remain menu-scripted |
| Static terrain | 48,216 standable coordinates and 154,653 directed land edges, including 749 ledge transitions | Initial land geometry, not current object or script state |
| Stateful-mechanic inventory | 8 ledge rules, 11 land-pair rules, 3 water-pair rules, 9 Cut swaps and 25 initial boulders | Surf, Cut and Strength are facts, not executable static edges |
| Route composition | Game-neutral `RoutePlan` selects reachable endpoints and preserves every arrival coordinate | Static candidate only; it does not replan around a live change |
| Live falsification | 86 generated actions: Pallet `(12,12)` → Route 1 → Viridian → Center `(7,3)`, with all three passage arrivals verified | One clean uncounted probe; Route 1 interruption recovery reused a qualified title helper |

The public records are [the complete map extraction](evidence/map-graph-2026-08-10.json),
[the traversal extraction](evidence/traversal-rules-2026-08-10.json), and
[the composed live route](evidence/pallet-viridian-composed-route-probe-2026-08-10.json).

## Corrections made during this milestone

### `LAST_MAP` was not the previous room

The old decoder expanded a `$FF` warp into every map with a direct door into the current interior.
That happens to work for a Pokémon Center and fails for nested interiors. An Underground Path
entrance can lead into another interior before the player returns; the engine still sends the
player to the retained outdoor route, not the immediately previous underground map.

The generic router state is now `(current_map, last_outside)`. A normal warp taken from an outside
tileset updates that state; connections and interior-to-interior warps do not. A return resolves its
target only when searched. Synthetic tests prove a nested interior returns outdoors and cannot use
stale outside state as a teleport.

### The missing warp byte was actionable data

Each four-byte source warp carries a zero-based destination-warp index. The decoder previously kept
source coordinates and destination map while discarding that index, so it could not know where the
next local search began. It now resolves all 558 ordinary arrivals and retains the index on dynamic
returns. A fixture with two destination events fails if byte three is treated as padding.

### Connection records contain movement geometry, not just rendering data

The eleven-byte connection structure includes destination width and x/y alignment. Those fields
produce exact border source/arrival pairs. All 1,484 directed transitions reverse exactly across the
78 reciprocal connections, and Red and Blue compare equal at the complete object level. Independent
fixture bytes distinguish the struct stride and alignment fields.

## Code strengths

1. **The search and composition cores are game-neutral.** `global_router.py`, `local_router.py` and
   `route_plan.py` operate on opaque map ids, coordinates, actions, costs and requirements. Pokémon
   and Generation I knowledge stop at the adapter.
2. **Endpoints are retained all the way to execution.** A macro path no longer collapses to map ids;
   connection candidates, warp triggers, arrivals and destination indices survive into each segment.
3. **Warp activation is not double-counted.** The final movement onto a door is the transition input;
   a connection needs a separate border-crossing input. The plan type records that distinction.
4. **Unknown behavior fails closed.** Scripted lifts are not routed through, a missing arrival is an
   error, an empty connection band is an error, and starting on a warp trigger is refused until a
   move-away/re-entry plan exists.
5. **Tests target prior blind spots.** Literal cartridge fixtures exercise nonzero warp indices,
   connection byte positions, several warp events, reciprocal endpoints and nested returns. Real-ROM
   equality is supporting evidence rather than the decoder's only test.
6. **The live receipt is source-bound.** It proves clean tracked source, executable bundle identity,
   released controls and unchanged RAM/RTC/state artifacts.

## Ranked gaps and risks

### P0 — runtime observation is still fragmented

The live probe verifies ordinary-map intermediate coordinates and every transition, but delegates
Route 1 battles and swallowed inputs to an existing title-specific helper. Several chapter-private
functions already implement pieces of observe/act/acknowledge/retry. They should become one public
executor that consumes a `RoutePlan`, executes one edge, reobserves, and emits a progress receipt.

### P0 — initial objects are not current blockers

`map_object_events` gives ROM initial positions. It does not say which objects are hidden by flags,
where a wandering NPC stands now, or where a boulder has moved. The planner currently blocks every
initial event for the probe; that conservative snapshot happened not to affect the chosen route.
A live overlay must expose visible current blockers and trigger short-suffix replanning.

### P1 — passage availability lacks semantic predicates

Static headers join locations even when a guard, locked door, one-way script or field capability
prevents traversal. Generation-specific predicates should filter the game-neutral edges from
observed badge, party-move, event and movement-mode facts. Unknown requirements remain unavailable.

### P1 — Surf is a movement mode

The water-pair table is decoded, but boarding, water movement, disembarking and live mode are not.
Surf is the best next capability because a mode-transition abstraction should transfer to later
games more cleanly than another Red corridor.

### P1 — Cut and Strength change state

Cut replaces blocks and requires graph recomputation. Strength moves objects and needs bounded
puzzle search over player/boulder state. Neither should be represented as a permanently open edge.

### P2 — route optimization is still layered, not globally joint

The macro router minimizes passage costs first; the composer then minimizes local approach cost
within that selected macro path. A later planner should compare total local-plus-passage cost across
macro alternatives. This is not needed for the proved Pallet route, but it matters for recovery
detours, Surf avoidance and story-gated alternatives.

### P2 — mutation coverage is targeted rather than scored

The new independent fixtures kill the known destination-index, stride, alignment and return-state
mutations. The repository does not yet publish a systematic mutation score for the complete passage
and composition layer. Add that before completion-run authority.

## Ordered next milestones

1. **Extract the shared route executor.** One planned action at a time; observe readiness and exact
   movement/map acknowledgement; bound waits and retries; record progress without title-specific
   route labels.
2. **Add live blocker overlays and replanning.** Observe visible objects, reject unintended door
   warps, and recompute a short suffix when the requested edge is not consumed.
3. **Run a second composed-route falsification.** Choose a route or timing lineage that exercises a
   moving blocker or wild interruption, and require no typed direction fallback.
4. **Implement Surf as mode state.** Derive capability from badge plus a living party move, observe
   board/move/disembark transitions, and falsify them live.
5. **Implement Cut and Strength separately.** Rebuild after Cut; search bounded push state for
   Strength; never conflate possession with an open passage.
6. **Filter one closed/open story gate.** Establish both states independently and prove the same
   passage changes availability without changing static topology.
7. **Collect strategic navigation examples.** Store candidate destinations, semantic need, route
   cost, interruption and outcome. Do not label every shortest-path frame as a learned decision.
8. **Run the Crystal microbenchmark.** Add a thin adapter only after the executor contract is title
   neutral, then compare frozen-Red zero-shot, preregistered few-shot and from-scratch baselines.

## Admission gate for completion-run routing

Generated routing remains experimental until all of the following are true:

- at least two clean source-bound continuous routes pass without typed direction fallbacks;
- every action is acknowledged from live coordinates/map state before the plan advances;
- current blockers trigger bounded replanning rather than permanent-terrain assumptions;
- wild and menu/script interruptions use shared bounded semantic recovery;
- required field capabilities come from observed badge, party and movement-mode state;
- unknown story and puzzle requirements fail closed;
- relevant decoder/composer mutations are killed; and
- public evidence remains bound to clean executable source and exact cartridge fingerprints.

This keeps the route layer transferable. Red supplies an adapter and evidence, not the answer key
the model is expected to memorize.
