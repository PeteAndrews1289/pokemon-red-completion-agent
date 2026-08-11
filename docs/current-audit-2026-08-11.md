# Current capability and code audit — 2026-08-11

## Executive verdict

The project has a strong deterministic Pokémon Red teacher, several learned decision components,
and a much more credible transfer architecture than a scripted playthrough. The newest work closes
two important knowledge/data boundaries:

1. ordinary retail Red/Blue acquisition reach is now exact rather than a lower bound; and
2. strategic navigation choices can now be collected without teaching a model Red's arrow
   sequences.

The agent is **not** yet a learned open-world Pokémon player. The completion teacher still owns most
navigation invocation and title-specific mechanics. Three explicitly unassigned live calibrations
now prove the strategic binding and recording seam. The third is the first genuine branch whose
teacher choice rejects the minimum-route-cost baseline. Train and validation still contain zero
strategic navigation records. No numeric navigation feature schema is frozen, and no strategic
navigation model has shadow or causal authority. Counted v95 remains **0/10**.

The split is no longer an open design question. A second prospective registry preassigns five
whole power-on train roots, two validation roots and five sealed test roots, with a distinct
uncounted rehearsal. Exact assignment identity is now required before a decision may claim any
non-unassigned partition. All strategic slots remain unopened.

That claim boundary is healthy. The next highest-value work is no longer another isolated route
mechanic; it is collecting genuine multi-destination decisions across independent roots and using
them to test whether a portable destination ranker learns more than route cost or candidate shape.

## What is now proved

### Cartridge knowledge

- Red and Blue independently decode 220 maps, 78 reciprocal connections, 917 warps and 48,216
  standable squares.
- Six tunnel entrances in both cartridges derive their retained outside-map context from exact,
  bounded script writes to `wLastMap`; the long Route 7→Route 8 underground traversal no longer
  depends on a handwritten return-context table.
- Joint map/local search carries exact coordinate, locomotion mode and retained outside-map state.
  The Red/Blue Pallet→Pewter audit rejects an impossible topology-only Route 2 shortcut and derives
  the nine-map Viridian Forest route at cost 317 with 314 acknowledgement contracts.
- Acquisition joins wild encounters, fishing, evolution, ten in-game trades and 30 scripted
  opportunities per title. Exact existential reach is 135 species solo and 139 with a trade
  partner. Choice groups are retained; Mew is not treated as ordinarily obtainable.

The source-bound public records are the
[joint route-pricing audit](evidence/joint-route-pricing-audit-2026-08-11.json) and
[acquisition audit](evidence/acquisition-routes-2026-08-11.json).

### Navigation mechanics

The game-neutral planner/executor has source-bound Red evidence for:

- exact multi-map land routing with acknowledgement, retry, interruption and replan;
- current visible occupancy before input;
- land/Surf mode changes and title-adapter field-menu execution;
- two successive Cut mutations from reread live terrain;
- the complete Victory Road Strength switch/hole chain;
- trainer-sight hazards distinct from occupancy and engagement;
- bounded recovery through an unavoidable trainer battle and its defeated-trainer field dialogue;
- one story passage in closed, unknown and open states;
- natural Repel expiry and renewal inside a continuing puzzle search; and
- combined local/macro route pricing rather than map-first approximation.

These results falsified several earlier abstractions: boundary returns are not uniform, one-frame
inputs can phase-lock, off-screen sprite facing is stale, an object can be hidden rather than absent,
and a story gate can close a statically walkable floor. The emulator corrected the abstraction; it
did not merely replay a route.

### Strategic navigation data boundary

Source checkpoints `33dd0d8`, `f43219d`, hardening commit `bcd9935`, route-binding commit
`bf3fc76`, collection-audit commit `92a8b80` and shared-evidence commit `ba2c224` implement:

- genuine candidate sets of at least two destinations;
- a reviewed cross-title vocabulary for need, origin and destination semantics;
- availability, route cost, step, transition, field-action and mode-change projections;
- model-facing input with no destination binding, map id, coordinate or arrow action;
- exact selected-plan/report consistency checks;
- typed replan, interruption, renewal and failure outcomes;
- one consumed outcome per decision;
- deterministic-teacher success labels separated from learned-policy outcomes and failed-choice
  evidence, so a learned action can never certify its own imitation target;
- external interruption censoring, including power loss;
- authenticated private trajectory decision/outcome records;
- a strict reader that rejects identity leakage, schema drift and join tampering;
- recursively immutable in-memory policy examples after canonical parsing; and
- whole-root split and semantic-coverage audits;
- authenticated loaded-episode auditing without discarding replan, interruption, resource or
  failure semantics; and
- route-cost-only plus semantic-need/candidate-shape baselines before feature freezing.

The first end-to-end live calibration starts from post-Pokédex Pallet with two real safe-hub
destinations. Home costs 15 with 14 route steps; Viridian Center costs 87 with 86 route steps. A
deterministic lowest-cost teacher selects home, the exact bound plan reaches Red's house with 14/14
movements acknowledged and controls released, and the identity-free trajectory projection contains
no route binding, map id, coordinate or arrow label. The source-bound
[calibration receipt](evidence/pallet-strategic-safe-hub-route-probe-2026-08-11.json) is explicitly
unassigned and ineligible for model development. It proves plumbing, not useful supervision.

The second calibration starts from an authenticated post-Safari state with two real progression
destinations. Koga's Gym carries `challenge`/`story_progress` semantics at cost 21 and 20 route
steps; the Warden/Strength objective carries `acquire_resource`/`story_progress` at cost 24 and 23
steps. The qualified completion order selected the Gym, exact binding reached `FUCHSIA_GYM` after
20/20 acknowledged movements, and the run recorded zero replans, interruptions or renewals. Its
[genuine-branch receipt](evidence/fuchsia-strategic-objective-route-probe-2026-08-11.json) is also
unassigned and promotion-ineligible. It proves that semantic branches can be captured live, but a
single choice that also agrees with minimum route cost is not a train/validation dataset.

The third calibration starts from the authenticated post-Hideout Celadon checkpoint. The
story-critical Pokémon Tower route costs 178; the optional Eevee pickup costs 60. Qualified
completion semantics reject the minimum-cost candidate, bind the Tower plan and traverse
`CELADON_POKECENTER → CELADON_CITY → ROUTE_7 → UNDERGROUND_PATH_ROUTE_7 →
UNDERGROUND_PATH_WEST_EAST → UNDERGROUND_PATH_ROUTE_8 → ROUTE_8 → LAVENDER_TOWN →
POKEMON_TOWER_1F`. The live executor acknowledged 174/174 movement requests, handled one
unavoidable Route 8 trainer engagement and reached `(17,10)` with zero replans. The
[non-cost calibration](evidence/celadon-strategic-objective-route-probe-2026-08-11.json) remains
unassigned and promotion-ineligible. Its six failed precursor attempts are separately preserved in
the [failure lineage](evidence/celadon-strategic-objective-route-failures-2026-08-11.json); none
emitted a public success receipt or a training record.

The older `navigation_dataset.py` is explicitly labeled individual-direction control diagnostics,
reports zero strategic decisions and remains ineligible for promotion.

### Prospective strategic collection protocol

The canonical
[strategic collection registry](../configs/red-strategic-navigation-collection-v1.json) fixes the
whole-root split and perturbation schedule before collection: 5 train, 2 validation, 5 sealed test,
plus one uncounted rehearsal. Each assignment is derived from the registry SHA, harness seed,
distinct 74-battle schedule, frozen teacher execution and partition. The decision contract hashes
the complete portable tag/outcome vocabulary and the fields forbidden from policy input.

The binding layer now refuses arbitrary counted provenance. A `train`, `validation` or `test`
decision requires its exact committed assignment; episode, lineage, partition, actor and policy
must all agree. The learning accessor refuses test roots. This prevents the collection counter from
being increased by changing a string in a calibration script. Current status is **train 0/5,
validation 0/2, test 0/5, rehearsal 0/1**.

## Code and CI audit

At this checkpoint the repository contains 152 source modules and 173 test modules. The local CI
equivalent produced:

- **2,571 passed, 3 deselected integration tests, 1 expected failure**;
- public-artifact scanning with no ROM, private path or secret leakage;
- documentation link validation;
- exact prospective-registry regeneration;
- Ruff clean;
- mypy clean under the declared scope; and
- GitHub Actions green through the preceding published checkpoints; the final evidence/documentation
  commit was subjected to the same local gate before publication.

The prospective v95 identities after the strategic data seam are:

| Field | Value |
| --- | --- |
| Registry SHA-256 | `cf238c5147bc2087146999a93d20092572860f3a45d517ce1077691d5f2d27df` |
| Source bundle SHA-256 | `5dada17bf6debbf1b566004e64c276fad0f15b131f1c4586f1d0f2e737866e2d` |
| Teacher execution SHA-256 | `c4607c031128f2e31f87fe804856e74e369fd3e851634885e7c71e78897933f8` |
| Slot assignment SHA-256 | `421aa6ecb6a11b3f34a63e6ad27833c758a2a8c7d3ea64111bf04fc5a1244b2d` |

The collection registry remains prospective. Regeneration caused by source changes does not open or
consume v95; counted runs remain 0/10.

The separate strategic registry is also prospective:

| Field | Value |
| --- | --- |
| Strategic registry SHA-256 | `b83d0b650801058db17d5ec250b0ec3b72d5db566cf5274cac3644a14ac830c2` |
| Decision-contract SHA-256 | `d62f16a23ad54742c97a52ffaa50b0617042d5e35518af4ae61b623631e539a6` |
| Strategic teacher execution SHA-256 | `ec32fec4e8fddd11383ee60ebfdff7e86fa2e1af616fddef659b2f60777640a5` |
| First train assignment SHA-256 | `9dfba88942adc178fe12b897d2a847ceea735a8b9a7251a44403fa17f037d88e` |

## Ranked gaps

### P0 — the collection harness is not yet connected to the full teacher

The schema, live binding, split registry and audit are ready, but the useful dataset denominator
remains zero. The
safe-hub calibration answers an easy route-cost question; the Fuchsia calibration is a genuine
branch that still agrees with cost; and the Celadon calibration proves one semantic choice can
reject a much shorter route. All three are development roots and none can enter training or
validation. Synthetic choices such as selecting between two arbitrary Viridian buildings would
make the counter rise without teaching a real decision. Use the preassigned whole roots to
instrument branches where the teacher genuinely weighs progression, recovery, resupply, training,
collection or optional reward destinations. Preassignment is complete; full-run instrumentation and
the one allowed rehearsal are next.

Do not freeze numeric features first. Collect the semantic/raw route projections, inspect their
coverage and correlations, then preregister normalization and baselines. Otherwise the schema will
encode assumptions rather than observed decisions.

### P0 — generated navigation does not own a completion run

Individual mechanics and routes are strong, and the generic router has now completed a nine-map,
174-step strategic route through an unavoidable trainer battle. The completion teacher still does
not broadly dispatch it, and the final post-switch Victory Road→Indigo path remains authored. A
model choosing an objective or destination still does not mean the generic navigator executed it
throughout the game.

### P1 — semantic passage coverage is incomplete

Only one ordinary story predicate is source-bound. Unavoidable trainer battles and their field
dialogue now resume through a narrow adapter, but special rivals/bosses, puzzle scripts, locked doors
and broader non-trainer menu/script interruption recovery remain partial or title-authored. Unknown
state correctly fails closed, which is safer than guessing but still limits generated authority.

### P1 — acquisition knowledge is ahead of acquisition behavior

The graph knows what a cartridge can produce. It does not yet autonomously catch the full set,
rotate boxes/party, replenish capture resources, schedule every evolution, coordinate trades or
manage multiple save lineages. The stretch goal of 100% completion requires those execution layers.

### P1 — transfer is still a hypothesis

Red/Blue equality is valuable within Generation I, but it is not a held-out-generation result. The
Crystal benchmark contract exists; the thin Gen II navigation adapter and measured zero-shot,
few-shot and from-scratch comparison do not.

### P2 — type and module-size debt remain

Mypy intentionally ignores 44 named legacy chapter modules. That is transparent and better than a
blanket ignore, but it remains real debt around duplicated emulator-state protocols and optional
RAM values. The new strategic dataset module is also large because it contains the in-memory model,
private-episode reader and strict canonical parser. If it expands during collection, split parsing
from dataset/split audits before adding model code.

## Ordered roadmap

1. **Connect the full-run collector.** Emit a choice and exactly one consumed outcome around genuine
   teacher/generated route branches, using only the committed rehearsal assignment at first.
2. **Qualify the rehearsal.** Run root `1710001`, audit candidate coverage, route-cost and shape
   baselines, interruption handling and terminal joins. Fix the harness without consuming a train
   or validation root.
3. **Collect the learning roots.** After the rehearsal freezes the harness, run all five train roots
   and both validation roots once. Preserve failures and censor external interruption; do not open
   the five test roots.
4. **Expand semantic coverage.** Include progression, recovery, resupply, training, collection and
   optional-reward choices, with both cost-aligned and non-cost-minimizing teacher decisions.
5. **Audit before featurizing.** Publish counts by need tag, candidate count, selected index,
   availability, route cost, replan reason, interruption and outcome. Measure route-cost-only and
   candidate-shape baselines.
6. **Freeze and train.** Preregister normalization, a shared permutation-equivariant candidate
   scorer, train-only selection and validation criteria. Keep the deterministic teacher in
   collection authority.
7. **Shadow, then act.** Run fresh shadow roots, followed by a bounded causal route-choice trial
   with exact binding, no disagreement fallback and an independent outcome referee.
8. **Close completion routing.** Add broader non-trainer menu/script recovery, more
   story/special-object predicates, the generated post-final-switch Indigo route and systematic
   mutation scoring.
9. **Test transfer.** Implement the thin Crystal adapter and compare frozen-Red zero-shot, fixed
   few-shot adaptation and from-scratch training under the same route-choice metrics.
10. **Expand completion.** Only after the play/transfer gates, add autonomous storage, evolution,
   trade and multi-save orchestration toward the living-Pokédex and 100% goals.

## Portfolio narrative

The strongest job-hunting story is not “I scripted Pokémon Red.” It is:

> I built an evidence-driven hybrid agent that completes Pokémon Red, progressively replaced
> teacher decisions with authenticated learned components, and used cartridge parsing plus live
> emulator falsification to separate transferable strategy from title-specific mechanics. When the
> system exposed misleading labels or brittle assumptions, I preserved the failures, corrected the
> abstraction, and tightened the evaluation contract instead of rerunning until success.

The concrete proof points are reproducible completion, causal learned battle/training authority,
identity-free candidate models, exact cartridge-derived world/acquisition knowledge, closed-loop
stateful routing, a 174-step story route that beat the shortest-path baseline, privacy-safe artifact
handling, and an unusually honest admission ledger. The next portfolio milestone is the first real
strategic-navigation dataset and a held-out Crystal transfer result—not another claim based on a
development calibration.
