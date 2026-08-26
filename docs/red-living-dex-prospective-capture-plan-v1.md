# Red prospective living-Pokédex capture plan V1

Status: published ROM-free feasibility plan. Source `ca7340d4` merged through PR 66 as main
`f9f3310e` and passed exact-main CI `32956496929/1`; see the
[qualification](evidence/red-living-dex-prospective-capture-plan-v1-qualification-2026-08-26.json).
It is subordinate to
[MISSION.md](../MISSION.md), [NORTH_STAR.md](../NORTH_STAR.md), the generated
[active product state](../ACTIVE_PRODUCT_STATE.md), and the published
[shared capture contract](living-dex-purpose-built-capture-contract.md).

## Result first

The abstract Red schedule satisfies the shared 10+5 curriculum contract, but Red cannot execute it
yet. The exact ten-slot train menu has a worst-case-after-any-two-censors probability of
**2144/2187 = 98.0338%** of selecting at least four distinct option kinds. Family and location
scope reserves pass. Seven portable kinds have implemented, independently tested Red provider
contracts; this does not authenticate a runtime binding for any new setup.

Only one of the fifteen requested menus is co-located at an existing physical skill boundary.
Fourteen need a reusable composition seam that can execute an authenticated route to a destination
semantic skill and then independently verify that skill. That seam does not exist. The pilot is
therefore **plan-valid but execution-blocked**.

The ROM-free implementation candidate for that seam is specified in
[routed semantic goal composition V1](routed-semantic-goal-composition-v1.md). It is not credited
here until its own publication, exact-head CI, and qualification are complete.

Trade is a separate full-product gap. The current `GoalKind`/Red binding layer has no repeatable
semantic trade executor. The first calibration pilot intentionally excludes trade because its
frozen minimum is four kinds, not all eight. A passing pilot cannot promote living-Pokédex or
cross-version authority until trade is implemented and evaluated later.

## Exact abstract schedule

The source of truth is
[`red_living_dex_capture_plan.py`](../src/pokemon_red_completion/red_living_dex_capture_plan.py).
Names below are logical scopes, not maps, species, items, routes, coordinates, or private roots.
Actual title bindings remain private and must prove one-to-one scope joins later.

| Slot | Partition | Complete planned menu | Family scope | Location scope | Existing local intersection |
| --- | --- | --- | --- | --- | --- |
| T00 | train | acquire · develop · explore | A | T0 | wild corridor |
| T01 | train | evolve · develop · manage storage | A | T0 | none |
| T02 | train | acquire · manage storage · unlock access | A | T1 | none |
| T03 | train | develop · manage storage · unlock access | A | T1 | none |
| T04 | train | evolve · resupply · explore | B | T2 | none |
| T05 | train | resupply · unlock access · explore | B | T2 | none |
| T06 | train | acquire · evolve · explore | B | T3 | none |
| T07 | train | acquire · manage storage · resupply | C | T3 | none |
| T08 | train | evolve · manage storage · unlock access | C | T4 | none |
| T09 | train | develop · resupply · explore | C | T4 | none |
| D00 | development | acquire · manage storage · resupply | D0 | D0 | none |
| D01 | development | evolve · manage storage · unlock access | D1 | D1 | none |
| D02 | development | acquire · unlock access · explore | D2 | D2 | none |
| D03 | development | evolve · develop · resupply | D3 | D3 | none |
| D04 | development | develop · manage storage · explore | D4 | D4 | none |

All fifteen slots are preregistered and must terminally account. Train family groups have sizes
4/3/3, so deleting any two slots still leaves all three groups. Development has five unique family
and five unique location scopes; deleting any one still leaves four. Train/development scopes are
disjoint. The behavior commitment remains the shared system-random rank policy; 2144/2187 is its
prospective uniform-row marginal, not a model-quality estimate.

## Implemented provider-contract audit

| Portable kind | Existing Red semantic boundary | Physical boundary scopes | Pilot use |
| --- | --- | --- | --- |
| acquire | wild-corridor area survey and capture | wild corridor | scheduled |
| evolve | targeted Diglett-to-Dugtrio team provider | Pokémon Center | scheduled |
| develop | local encounter dose and balanced-team provider | wild corridor / Pokémon Center | scheduled |
| manage storage | verified box switch | storage PC | scheduled |
| resupply | exact verified Mart purchase | Mart clerk | scheduled |
| unlock access | dependency-legal bounded story objective | story objective boundary | scheduled |
| explore | verified wild survey or route goal | wild corridor / route start | scheduled |
| trade | **missing repeatable semantic executor** | none | not scheduled; mission blocker later |

The audit credits only concrete provider classes already independently tested by the Red goal layer;
their fully qualified source identities are recorded in the public qualification. It does not call
those classes runtime-authenticated until a setup supplies and verifies a real binding. Raw
callables, teacher steps, routes relabelled as destination outcomes, and synthetic test executors do
not count.

## Why routing is the smallest pilot blocker

Moving the setup state to a Mart makes resupply available but does not make storage, evolution, or
acquisition available. Moving it to a PC has the inverse problem. Simply declaring those menu rows
would produce unavailable or synthetic arms. The missing abstraction is one selected semantic
option that owns this sequence:

1. authenticate a frozen route from the common decision boundary to the destination boundary;
2. execute that route under hard action/frame limits and verify the exact terminal;
3. reobserve Red and ask the already-existing destination provider for the declared goal kind;
4. execute exactly that destination binding once;
5. expose a combined report whose verifier requires both the route terminal and the destination
   provider's independent success verdict.

The route may not become an `explore` label when the selected semantic destination is resupply,
storage, evolution, or another kind. The destination provider—not the route—owns the model-facing
kind and outcome. This is reusable beyond Red because later title adapters need the same
route-then-semantic-skill composition, while supplying their own routes and observations.

## Frozen authority boundary

This plan was built without ROM/private capture access. It performed **setup actions 0 · setup
frames 0 · behavior draws 0 · learner claims/actions/labels/outcomes 0 · predictions 0 · teachers
0 · fits 0 · authority 0 · transfer 0**. Its public qualification contains only semantic kind and
aggregate scope counts, contract digests, the exact probability, and explicit zero/private-field
counters.

The plan does not authorize a routed skill, setup runner, protected setup campaign, capture
inventory, selected-arm outcome, model fit, sealed Red evaluation, Crystal execution, promotion,
or replay.

## Next gates

1. **Complete:** publish this exact feasibility result and reorient.
2. **Active:** implement and adversarially qualify only the generic routed-semantic-goal
   composition seam.
3. Re-run this ROM-free feasibility audit. The pilot blocker closes only when every scheduled kind
   can bind through genuine local or routed semantic execution without changing the schedule.
4. Separately freeze and qualify the durable Red setup runner and private route/terminal bindings.
5. Run every setup slot once, census complete captures, then collect randomized outcomes under a
   new gate.
6. Before any living-Pokédex or cross-version authority claim, implement and evaluate semantic
   trade; do not let an initial non-trade calibration fit erase that mission requirement.
