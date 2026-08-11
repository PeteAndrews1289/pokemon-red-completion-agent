# Current capability and code audit — 2026-08-11

## Executive verdict

The project has a strong deterministic Pokémon Red teacher, several learned decision components,
and a much more credible transfer architecture than a scripted playthrough. The newest work closes
two important knowledge/data boundaries:

1. ordinary retail Red/Blue acquisition reach is now exact rather than a lower bound; and
2. strategic navigation choices can now be collected without teaching a model Red's arrow
   sequences.

The agent is **not** yet a learned open-world Pokémon player. The completion teacher still owns most
navigation invocation and title-specific mechanics. No strategic navigation records have been
collected, no numeric navigation feature schema is frozen, and no strategic navigation model has
shadow or causal authority. Counted v95 remains **0/10**.

That claim boundary is healthy. The next highest-value work is no longer another isolated route
mechanic; it is collecting genuine multi-destination decisions across independent roots and using
them to test whether a portable destination ranker learns more than route cost or candidate shape.

## What is now proved

### Cartridge knowledge

- Red and Blue independently decode 220 maps, 78 reciprocal connections, 917 warps and 48,216
  standable squares.
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
- one story passage in closed, unknown and open states;
- natural Repel expiry and renewal inside a continuing puzzle search; and
- combined local/macro route pricing rather than map-first approximation.

These results falsified several earlier abstractions: boundary returns are not uniform, one-frame
inputs can phase-lock, off-screen sprite facing is stale, an object can be hidden rather than absent,
and a story gate can close a statically walkable floor. The emulator corrected the abstraction; it
did not merely replay a route.

### Strategic navigation data boundary

Source checkpoints `33dd0d8`, `f43219d` and hardening commit `bcd9935` implement:

- genuine candidate sets of at least two destinations;
- a reviewed cross-title vocabulary for need, origin and destination semantics;
- availability, route cost, step, transition, field-action and mode-change projections;
- model-facing input with no destination binding, map id, coordinate or arrow action;
- exact selected-plan/report consistency checks;
- typed replan, interruption, renewal and failure outcomes;
- one consumed outcome per decision;
- successful-choice imitation targets separated from failed-choice outcome evidence;
- external interruption censoring, including power loss;
- authenticated private trajectory decision/outcome records;
- a strict reader that rejects identity leakage, schema drift and join tampering;
- recursively immutable in-memory policy examples after canonical parsing; and
- whole-root split and semantic-coverage audits.

The older `navigation_dataset.py` is explicitly labeled individual-direction control diagnostics,
reports zero strategic decisions and remains ineligible for promotion.

## Code and CI audit

At this checkpoint the repository contains 146 source modules and 168 test modules. The local CI
equivalent produced:

- **2,538 passed, 3 deselected integration tests, 1 expected failure**;
- public-artifact scanning with no ROM, private path or secret leakage;
- documentation link validation;
- exact prospective-registry regeneration;
- Ruff clean;
- mypy clean under the declared scope; and
- GitHub Actions green on the two strategic-navigation checkpoints.

The prospective v95 identities after the strategic data seam are:

| Field | Value |
| --- | --- |
| Registry SHA-256 | `8f8041a708e7cc131255ee7cf0f9bee4b8a7b79755a3cd056bb004e08fb0fce1` |
| Source bundle SHA-256 | `a8ff02b3f24110527afc7a24356c59d2e2eed252468af122bae60c30fd43d354` |
| Teacher execution SHA-256 | `dc749d106a42cb276f819674d2ca496351692ea65716bb232eddcb371ea76f33` |

The collection registry remains prospective. Regeneration caused by source changes does not open or
consume v95; counted runs remain 0/10.

## Ranked gaps

### P0 — no strategic navigation data exists

The schema is ready, but its honest denominator is zero. Synthetic choices such as selecting
between two arbitrary Viridian buildings would make the counter rise without teaching a real
decision. Instrument branches where the teacher genuinely weighs progression, recovery, resupply,
training, collection or optional reward destinations.

Do not freeze numeric features first. Collect the semantic/raw route projections, inspect their
coverage and correlations, then preregister normalization and baselines. Otherwise the schema will
encode assumptions rather than observed decisions.

### P0 — generated navigation does not own a completion run

Individual mechanics and routes are strong, but the completion teacher does not broadly dispatch
the generic router. The final post-switch Victory Road→Indigo path remains authored. A model choosing
an objective or destination still does not mean the generic navigator executed it throughout the
game.

### P1 — semantic passage coverage is incomplete

Only one ordinary story predicate is source-bound. Special rivals/bosses, puzzle scripts, locked
doors and shared menu/script interruption recovery remain partial or title-authored. Unknown state
correctly fails closed, which is safer than guessing but still limits generated authority.

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

1. **Instrument genuine decisions.** Add strategic recording around real generated-route branches
   in uncounted teacher/captured-state runs. Require at least two semantically relevant candidates
   and record every consumed success, failure or interruption once.
2. **Build disjoint lineages.** Collect multiple train roots and at least one untouched validation
   root. Preserve state/source/manifest identities and reject root overlap.
3. **Audit before featurizing.** Publish counts by need tag, candidate count, selected index,
   availability, route cost, replan reason, interruption and outcome. Measure route-cost-only and
   candidate-shape baselines.
4. **Freeze and train.** Preregister normalization, a shared permutation-equivariant candidate
   scorer, train-only selection and validation criteria. Keep the deterministic teacher in
   collection authority.
5. **Shadow, then act.** Run fresh shadow roots, followed by a bounded causal route-choice trial
   with exact binding, no disagreement fallback and an independent outcome referee.
6. **Close completion routing.** Add shared menu/script recovery, more story/special-object
   predicates, the generated post-final-switch Indigo route and systematic mutation scoring.
7. **Test transfer.** Implement the thin Crystal adapter and compare frozen-Red zero-shot, fixed
   few-shot adaptation and from-scratch training under the same route-choice metrics.
8. **Expand completion.** Only after the play/transfer gates, add autonomous storage, evolution,
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
stateful routing, privacy-safe artifact handling, and an unusually honest admission ledger. The next
portfolio milestone is the first real strategic-navigation dataset and a held-out Crystal transfer
result—not another claim based on a single Red route.
