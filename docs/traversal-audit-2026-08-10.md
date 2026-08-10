# Knowledge-to-action audit — 2026-08-10

## Executive verdict

Static composition and closed-loop land execution are proved across two continuous live routes.
The repository reads connection and warp endpoints from Red or Blue, joins local searches across map
boundaries, turns each edge into an exact observation contract, and refuses to count an input until
live state acknowledges it. A failed step can invalidate its target coordinate and produce a new
cartridge-derived route without consulting a typed Kanto corridor.

The 86-step Center control handled three natural wild interruptions with no retry or replan. The
Mart falsification handled one wild, a disclosed artificial first-step blocker, and the naturally
moving Route 1 youngster; it acknowledged 108 steps from 112 requests and entered the Mart after two
replans. This is land-navigation infrastructure, not learned navigation. The model should learn
strategic destination and recovery choices; graph search should continue to own exact geometry.

Stateful Surf is now proved by a third source-bound route. The graph searches `(coordinate, mode)`,
derives shore and water edges from cartridge data, requires an observed badge plus living move
holder, and delegates only the title-specific menu sequence. The live round trip exited Cinnabar
Center, boarded at `(13,11)`, crossed two genuine water-travel edges to `(16,11)`, disembarked and
returned to `(12,11)` in land mode. It acknowledged all 13 route steps.

## What is proved now

| Layer | Current evidence | Authority boundary |
| --- | --- | --- |
| Macro topology | 220 reachable maps and 78 reciprocal connections in both cartridges | Connectivity is not proof that a story- or capability-gated passage is open |
| Passage geometry | 1,484 exact connection transitions, 558 ordinary warp arrivals, 242 indexed dynamic returns and 2 scripted lift exits; full Red/Blue structures agree | Boundary returns need a separate outward action and adjacent exterior arrival; lifts remain menu-scripted |
| Static terrain | 48,216 standable coordinates and 154,653 directed land edges, including 749 ledge transitions | Initial land geometry, not current object or script state |
| Stateful mechanics | 8 ledge rules, 11 land-pair rules and 3 water-pair rules feed executable land/water mode graphs; 9 Cut swaps and 25 initial boulders remain decoded inventory | Surf is live-qualified; Cut and Strength are not yet executable state transitions |
| Route composition | Game-neutral `RoutePlan` selects reachable endpoints and flattens every edge into exact source/expected state | Macro path cost is still selected before local path cost |
| Closed-loop execution | Game-neutral runtime acknowledges coordinates and map transitions, bounds readiness/retries/interruptions, discovers blockers and replans | Blockers are inferred from failed movement, not read as a complete visible-object overlay |
| Live falsification | Center: 86/86 steps, 3 wilds, 0 replans. Mart: 108 acknowledged steps/112 requests, 1 wild, 2 replans. Surf: 13/13 steps, exact land→water→land round trip | Three clean uncounted Red probes; current objects, Cut, Strength and story gates remain outside authority |

The public records are [the complete map extraction](evidence/map-graph-2026-08-10.json),
[the traversal extraction](evidence/traversal-rules-2026-08-10.json),
[the control route](evidence/pallet-viridian-composed-route-probe-2026-08-10.json), and
[the replanning route](evidence/pallet-viridian-mart-closed-loop-replan-probe-2026-08-10.json), and
[the Surf round trip](evidence/cinnabar-cartridge-surf-route-probe-2026-08-10.json).

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

### A map change and an arrival coordinate are not atomic

The first Mart probe reached map 42 while its coordinate bytes still held Viridian `(19, 29)`. The
original executor treated that mixed observation as drift and failed closed. Gen I publishes the
destination map before refreshing the destination coordinates, so cross-map acknowledgement now
enters one bounded settling phase after seeing the target map and requires the exact decoded arrival
afterward. A ROM-free staged-transition test preserves the timing boundary.

### A boundary return is not activated by entering its warp square

The original composer treated every warp alike: the final step onto the recorded coordinate was the
cross-map transition. Live Red reached Cinnabar Center `(7,3)` and stayed inside. One additional
Down action fired the return and landed at exterior `(12,11)`, one square beyond the destination
door event. Boundary return records now carry an outward action derived from cartridge map geometry;
the composer reaches the warp first, executes that separate action, and adjusts the dynamic arrival.
Internal and ordinary warps retain their prior enter-to-trigger behavior.

### Blocker discovery must follow action settling

A direction request may already be in flight while Red still publishes its source coordinate. The
executor previously reached the two-request threshold before its retry settling wait and could ask
the planner to blacklist the valid destination. It now waits, reobserves readiness and the exact
coordinate, and only then infers a blocker. The live probe also showed that 1/1-frame controller
pulses can phase-lock between joypad polls, so the field-route harness uses the repository's proven
8/16-frame timing.

## Code strengths

1. **The search and composition cores are game-neutral.** `global_router.py`, `local_router.py` and
   `route_plan.py` operate on opaque map ids, coordinates, actions, costs and requirements. Pokémon
   and Generation I knowledge stop at the adapter.
2. **Endpoints are retained all the way to execution.** A macro path no longer collapses to map ids;
   connection candidates, warp triggers, arrivals and destination indices survive into each segment.
3. **Warp activation is represented by kind.** Ordinary enter-to-trigger warps consume their final
   approach movement. Boundary returns first reach the recorded coordinate and then execute the
   cartridge-derived outward action. Connections retain a separate border-crossing input.
4. **Unknown behavior fails closed.** Scripted lifts are not routed through, a missing arrival is an
   error, an empty connection band is an error, and starting on a warp trigger is refused until a
   move-away/re-entry plan exists.
5. **Tests target prior blind spots.** Literal cartridge fixtures exercise nonzero warp indices,
   connection byte positions, several warp events, reciprocal endpoints and nested returns. Real-ROM
   equality is supporting evidence rather than the decoder's only test.
6. **The live receipts are source-bound.** They prove clean tracked source, executable bundle
   identity, released controls and unchanged RAM/RTC/state artifacts.
7. **Interruption policy stays outside the router.** The neutral runtime sees a typed interruption;
   the Gen I adapter authenticates and flees only wild battles. Trainers and unknown battle states
   remain fatal rather than becoming a hidden navigation policy.

## Ranked gaps and risks

### P0 — visible objects are still inferred rather than observed

`map_object_events` gives ROM initial positions. It does not say which objects are hidden by flags,
where a wandering NPC stands now, or where a boulder has moved. The planner currently blocks every
initial event, then treats two unconsumed movement requests as evidence that the requested target is
currently unavailable. That recovered from Route 1's youngster, but it cannot distinguish a moving
person from a closed gate or permanent collision. Add direct visible-object projection where the
revision exposes it, while retaining bounded failed-step discovery as a safe fallback.

### P1 — passage availability lacks semantic predicates

Static headers join locations even when a guard, locked door, one-way script or field capability
prevents traversal. Generation-specific predicates should filter the game-neutral edges from
observed badge, party-move, event and movement-mode facts. Unknown requirements remain unavailable.

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

1. **Project visible dynamic objects.** Prefer observed occupancy over failed-input inference where
   revision-decoded state supports it, and separately classify permanent/story-gated blocks.
2. **Implement Cut and Strength separately.** Rebuild after Cut; search bounded push state for
   Strength; never conflate possession with an open passage.
3. **Filter one closed/open story gate.** Establish both states independently and prove the same
   passage changes availability without changing static topology.
4. **Jointly price macro alternatives.** Compare local approach plus passage cost before selecting
   the map path; the current layered optimizer can miss a cheaper recovery detour.
5. **Collect strategic navigation examples.** Store candidate destinations, semantic need, route
   cost, interruption and outcome. Do not label every shortest-path frame as a learned decision.
6. **Run the Crystal microbenchmark.** Add a thin adapter only after the executor contract is title
   neutral, then compare frozen-Red zero-shot, preregistered few-shot and from-scratch baselines.

## Admission gate for completion-run routing

Generated routing remains experimental until all of the following are true:

- at least two clean source-bound continuous routes pass without typed direction fallbacks (met for
  ordinary land routes);
- every action is acknowledged from live coordinates/map state before the plan advances (met for
  those routes);
- current blockers trigger bounded replanning rather than permanent-terrain assumptions (met by
  failed-step discovery; direct occupancy remains open);
- wild and menu/script interruptions use shared bounded semantic recovery (wild met; menu/script
  remains open);
- required Surf capability and land/water mode come from observed badge, party and locomotion state
  (met for the qualified Cinnabar round trip; other field mechanics remain closed);
- unknown story and puzzle requirements fail closed;
- relevant decoder/composer mutations are killed; and
- public evidence remains bound to clean executable source and exact cartridge fingerprints.

This keeps the route layer transferable. Red supplies an adapter and evidence, not the answer key
the model is expected to memorize.
