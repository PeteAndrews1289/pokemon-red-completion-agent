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
non-unassigned partition. The assignment is now connected to one deliberately narrow clean-power
branch: the post-Hideout teacher records Tower versus Eevee before acting, executes the exact bound
generated route, and consumes its measured outcome before the Tower interior continues. A private
checkpoint preflight passed that generated approach and the complete Tower chapter, but it was not
a clean-power root and cannot become data. The first genuine clean-power rehearsal then failed at
checkpoint 16, before any strategic decision. Its repaired source-bound successor cleared that gate
and then failed at checkpoint 23, also before the strategic branch. Both are retained as uncounted
negative harness evidence. All train, validation and test slots remain unopened.

That claim boundary is healthy. The exact failed schedule now clears its former Viridian Forest
gate after a trace-derived repair. The next highest-value work is publishing that source, qualifying
its regenerated rehearsal identity, auditing whether its sparse decision coverage can support
learning, and only then deciding whether learning roots should open or the campaign should expand.

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
- assignment-authenticated episode loading that rejects local-only provenance, collection/source/
  split/policy drift and premature test access;
- a source-bound rehearsal assignment that remains explicitly unassigned and uncounted;
- pre-execution strategic choice recording with one pending-decision/consumed-outcome state
  machine, so a failed or interrupted route cannot disappear from the episode;
- typed partial route-failure evidence retaining measured acknowledgements, requests, waits,
  replans, interruptions and renewals while dropping the terminal map/coordinate at the strategic
  boundary;
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
being increased by changing a string in a calibration script. After collection, the assigned
episode loader independently matches the header's collection, source bundle, source commit, split,
actor and policy to that assignment before applying the strict decision/outcome join. It refuses
local-only assignments and keeps test episodes sealed by default. Current counted status is **train
0/5, validation 0/2, test 0/5**. Two earlier source-bound rehearsals failed before the strategic
branch; the newest repaired-source prospective rehearsal identity remains unopened.

The registry's rehearsal declaration is now executable as an authenticated identity rather than
just a seed. Its derived episode and lineage stay `unassigned`, its attempt is explicitly
`counted=false`, and the binder rejects substituting a counted root into that lane. The trajectory
observer writes each choice before route execution, holds one pending decision, and accepts exactly
one matching outcome afterward. A power loss can therefore produce an incomplete rehearsal for
diagnosis, but never a silently missing decision or a consumed learning slot. The decision and
outcome must share one sink; if the decision write fails, the observer marks the episode ineligible
and refuses to write an orphan outcome.

The new full-run bridge uses that contract rather than bypassing it. `--strategic-rehearsal` loads
the committed registry, derives the sole uncounted assignment and exact 74-battle schedule, requires
clean published source, writes the assignment-authenticated header and supplies the assignment to
the teacher. At the post-Hideout boundary, the teacher plans both Tower and Eevee candidates,
records the Tower choice, executes the selected plan and consumes its route report or typed failure.
The generated Route 8 trainer remains outside the frozen battle schedule; Tower reward accounting
begins afterward so that the added encounter cannot falsify the ten-battle interior receipt.

A private captured-state preflight passed all 28 Tower checkpoints and ten mandatory Tower battles
after the generated approach, with one strategic decision, one matching outcome and zero recording
failures. Because this used an already-opened state against an uncommitted working tree, it is an
integration diagnostic only—not a source-bound public result, clean-power rehearsal or dataset row.

The first published command then failed earlier than the emulator: its 96-character rehearsal
episode name exceeded the private root's intentionally stricter 80-character directory contract.
No private episode, partial artifact or game outcome was created. The same audit revealed that the
86-character counted strategic prefix would also have failed later. Both forms now derive
78-character names, enforce the storage ceiling in the strategic protocol and cross the actual
private `begin_episode` boundary in tests. At that checkpoint no game run had begun.

The corrected namespace at published source `ab69be7` allowed the next command to create the
uncounted episode and start from clean power. It failed at checkpoint 16/312 in Viridian Forest,
long before Tower versus Eevee. The retained partial contains 2,086 records: 5 objective-selection
decisions, 1,508 executions, 16 events and 556 snapshots. It contains no strategic navigation
decision and cannot enter training. The failure is still useful because it is an authenticated
record of the teacher that would have produced the dataset.

The trace showed Weedle at 6/27 HP after the scripted sequence, while Squirtle was level 8 at 14/25
HP and Tackle had zero PP. The generic battle finisher kept confirming the exhausted move. A
one-shot Bubble fallback reproduced the failure because subsequent turns returned to Tackle. The
durable repair selects a usable attack on every actionable battle-menu turn and leaves transient
faint/victory dialogue to bounded confirmation. The final state was level 9, 15/27 HP, status-free,
with 28 Bubble PP; the historical gate nevertheless required 19 HP. That gate now expresses the
real safety invariant: a living status-free lead may traverse the authenticated HP-preserving
corridor to Pewter's mandatory heal, while poison still requires the conservative reserve. An exact
in-memory replay under schedule `1710001` now clears checkpoint 17 with 5 decisions, 1,340
executions and 16 events. It opens no episode and consumes no split.

Published repair `1904b59` passed exact-commit CI. Its regenerated clean-power rehearsal cleared
Forest, Brock and Route 3 trainer 0, then failed during trainer 1 at checkpoint 23. The second
retained partial contains 3,472 records: 7 decisions, 2,339 executions, 23 events and 1,102
snapshots. It still contains no strategic navigation decision. The battle trace shows a three-
Pokémon trainer reducing Squirtle to 7 HP; the teacher consumed its one surplus Potion, retained the
twelve-Potion route floor, and resumed Tackle. Squirtle fainted at 0/35 while the final opponent had
2/30 HP. Bubble remained at 30 PP.

This was another authored-policy defect rather than inadequate inventory: trainer 1 was the only
required Route 3 trainer excluded from the Bubble set. An in-memory exact-schedule counterfactual
that removes that one exception reaches checkpoint 24 with 7 decisions, 2,345 executions and 23
events. The source now derives the Bubble set from all required Route 3 trainer indexes, retaining
the Potion floor, battle recovery and victory contracts.

## Code and CI audit

At this checkpoint the repository contains 152 source modules and 176 test modules. The local CI
equivalent produced:

- **2,604 passed, 3 deselected integration tests, 1 expected failure**;
- public-artifact scanning with no ROM, private path or secret leakage;
- documentation link validation;
- exact prospective-registry regeneration;
- Ruff clean;
- mypy clean across its declared 154-source-file scope; and
- GitHub Actions green through the preceding published checkpoint; exact-commit CI remains a
  required publication gate for the repaired rehearsal in addition to this local result.

The prospective v95 identities after the strategic data seam are:

| Field | Value |
| --- | --- |
| Registry SHA-256 | `1212dfa5bd23deda55b22aee593d1e32cdbe20abf40bce9202040c26d41243cb` |
| Source bundle SHA-256 | `990d365bf093e1b85765ea99673d92e1aae0c491d6ddc671d81bcb331e6a8bd1` |
| Teacher execution SHA-256 | `09086e68615f50e101b2c094c7dc4d779ac33d621fe76faf4f98db8c10fde9d7` |
| Slot assignment SHA-256 | `d90a5476e21f184950235edfe1f3fe64351ab3917ecb3c93820f22fb91581524` |

The collection registry remains prospective. Regeneration caused by source changes does not open or
consume v95; counted runs remain 0/10.

The separate strategic registry is also prospective:

| Field | Value |
| --- | --- |
| Strategic registry SHA-256 | `9694bcab348d378d282c1b717d2842487709e43e765d71124583f160a8bca2d0` |
| Decision-contract SHA-256 | `d62f16a23ad54742c97a52ffaa50b0617042d5e35518af4ae61b623631e539a6` |
| Strategic teacher execution SHA-256 | `b144ade83a6522aec776477ed1c64d756f305ef3651b2f8793c48003549c1e2e` |
| Rehearsal assignment SHA-256 | `20d1a55e79799b8b8a478265c917bded28cfc319e1785f5ba8bb15a95c3edb86` |
| First train assignment SHA-256 | `eb150e9709921d35cb11f195e28ec6d1c0c015e0e48ecdad0ae43825748c34b5` |

## Ranked gaps

### P0 — the repaired rehearsal must reach and exercise the strategic branch

The schema, live binding, split registry, strict assigned-episode loader, pre-execution observer and
audit are ready, but the useful dataset denominator remains zero. The
safe-hub calibration answers an easy route-cost question; the Fuchsia calibration is a genuine
branch that still agrees with cost; and the Celadon calibration proves one semantic choice can
reject a much shorter route. All three are development roots and none can enter training or
validation. Synthetic choices such as selecting between two arbitrary Viridian buildings would
make the counter rise without teaching a real decision. Use the preassigned whole roots to
instrument branches where the teacher genuinely weighs progression, recovery, resupply, training,
collection or optional reward destinations. Preassignment and output authentication are complete;
one full-run branch is instrumented. Two clean-power attempts failed before that branch and taught
the teacher how to handle exhausted PP and a bad early move policy safely. Publish the current
repair and run only its regenerated uncounted assignment next.

The execution-side failure prerequisite is now closed. `execute_route` attaches a typed semantic
reason and measured partial trace to its error, including the acknowledged prefix before a
replanner fails. The strategic conversion verifies the failed initial plan against the selected
binding, retains portable counts/receipts, and excludes the last map and coordinate. The bridge
calls this seam around Tower versus Eevee and consumes the success or failure before the chapter
continues or raises. The remaining risk is empirical: the repaired clean-power root must first
survive the complete teacher and reach that branch in a state compatible with the captured-state
preflight.

Do not freeze numeric features first. Collect the semantic/raw route projections, inspect their
coverage and correlations, then preregister normalization and baselines. Otherwise the schema will
encode assumptions rather than observed decisions.

### P0 — generated navigation owns one branch, not the completion run

Individual mechanics and routes are strong, and the generic router has now completed a nine-map,
174-step strategic route through an unavoidable trainer battle. The exact rehearsal path can now
dispatch that approach inside the full teacher, but this is one conditional branch. The completion
teacher still does not broadly dispatch generated routes, and the final post-switch Victory
Road→Indigo path remains authored. A model choosing an objective or destination still does not mean
the generic navigator executed it throughout the game.

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

1. **Publish the bridge.** Commit and push the exact source/registries, then require green CI for
   that commit before any private clean-power execution.
2. **Qualify the rehearsal.** Run only root `1710001`; preserve a failed partial episode and never
   edit source during the run or substitute a train/validation/test root for debugging.
3. **Audit before opening learning roots.** Authenticate the episode, verify its decision/outcome
   join, and measure candidate coverage, route-cost and shape baselines, interruptions and terminal
   state.
4. **Resolve the density decision.** One Tower-versus-Eevee choice per whole run may be too little
   supervision. If so, add genuine recovery, resupply, training, collection and optional-reward
   branches, then preregister a fresh campaign instead of changing the current one after exposure.
5. **Collect the learning roots only if coverage is adequate.** Execute all five train roots and
   both validation roots once. Preserve failures and censor external interruption; do not open the
   five test roots.
6. **Audit before featurizing.** Publish counts by need tag, candidate count, selected index,
   availability, route cost, replan reason, interruption and outcome. Measure route-cost-only and
   candidate-shape baselines.
7. **Freeze and train.** Preregister normalization, a shared permutation-equivariant candidate
   scorer, train-only selection and validation criteria. Keep the deterministic teacher in
   collection authority.
8. **Shadow, then act.** Run fresh shadow roots, followed by a bounded causal route-choice trial
   with exact binding, no disagreement fallback and an independent outcome referee.
9. **Close completion routing.** Add broader non-trainer menu/script recovery, more
   story/special-object predicates, the generated post-final-switch Indigo route and systematic
   mutation scoring.
10. **Test transfer.** Implement the thin Crystal adapter and compare frozen-Red zero-shot, fixed
   few-shot adaptation and from-scratch training under the same route-choice metrics.
11. **Expand completion.** Only after the play/transfer gates, add autonomous storage, evolution,
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
