# Red-to-Crystal readiness roadmap

Status: active mission-level execution plan as of 2026-08-31, adopted after independent Claude and
Antigravity review and Codex adjudication. Read
[MISSION.md](../MISSION.md), [NORTH_STAR.md](../NORTH_STAR.md), and the generated
[active product state](../ACTIVE_PRODUCT_STATE.md) first. The active product state still controls
the immediate operation. This document defines the longer critical path from that operation to an
honest Crystal port. The reviewers' findings and Codex dispositions are preserved in the
[review adjudication](red-to-crystal-roadmap-review-adjudication-2026-08-30.md).

## Destination

The product is a hierarchical agent that can finish stories and build a declared living Pokedex
across games, versions, legitimate trades, and legitimate event inputs. Red is the first causal
curriculum. Crystal is the first test of whether the learned representation and policies transfer.
Neither game is the product, and neither should receive a hand-written end-to-end route disguised
as a model.

The intended system has five layers:

1. a title-specific observer and mechanics adapter;
2. a title-neutral semantic state, capability vocabulary, collection ledger, and memory;
3. a dependency planner that proposes honest currently achievable options;
4. learned option, battle, navigation, and party-development policies that rank or execute those
   options; and
5. independent verifiers, bounded recovery, and abstention when the current title exposes an
   unsupported mechanic.

The teacher may generate states, demonstrate a mechanic, verify an outcome, or intervene at a
declared safety boundary. It may not remain the hidden author of the final route or the expected
answer source for a supposedly learned decision.

## Honest starting point

Exact source `a358014fb2dfe4193c9474ee1cc008cd249eb03c` is green under GitHub CI run
`33329384186/1`. From that source, the final prospective R1 batch attempted untouched successor
train ordinals 8–15 exactly once each. Six settled causal examples and two ended during setup,
producing 6/8 yield in 523 seconds. Across all sixteen successor ordinals, twelve settled and four
ended during setup. Combined with R0, the private train corpus now has eighteen examples from
eighteen distinct lineages, all seven supported portable kinds, 54/54 supported candidate rows,
selected-feature rank 11/16, three successes, and fifteen failures.

The earlier R0 learner invocation remains the sole integration fit: one immutable
non-authoritative model over the original eight-row denominator, reopened byte-identically with
finite conditioning and 225/225 finite coefficients. It has not been refit or used for gameplay.

The board is therefore:

| Evidence level | Current state |
| --- | --- |
| Authentic causal Red train examples | 18/60 minimum |
| Non-authoritative integration fit | 1/1 |
| Powered Red candidate | 0 |
| Untouched Red development pass | 0 |
| Model-controlled gameplay authority | 0 |
| Crystal realized contexts or predictions | 0 |
| Demonstrated cross-title transfer | 0 |

Eighteen examples and the complete bounded successor prove that execution throughput is not the
current bottleneck. They are not enough to support a powered model-quality, gameplay, completion,
or transfer claim. The action-free clustered V2 design and independent review are complete, and
the exact census has since proved the existing bank short by 103 lineages. A bounded clean-power
supply rail is now locally implemented but unrun: twelve prospectively partitioned worlds must
first demonstrate 9/12 yield with train/development/contingency floors 2/6/1. Only admission and an
integration/yield recensus may follow. A later population plan must still fill and prove the final
36/100/3 capacity before outcomes resume.

## Evidence ladder

Every milestone promotes exactly one claim. Evidence cannot skip a rung.

```text
authenticated examples
        -> reproducible integration fit
        -> powered Red model
        -> untouched Red development advantage
        -> bounded teacher-free Red authority
        -> multi-goal living-Dex composition
        -> frozen title-neutral bundle
        -> zero-shot Crystal transfer test
        -> measured Crystal adaptation
        -> Crystal story and living-Dex completion
```

A lower rung may reveal a defect in a higher-level design, but it may not be renamed as higher-level
success. In particular, low train loss does not mean the model can play, a successful skill does not
mean the hierarchy can compose skills, and a Crystal adapter test does not mean transfer occurred.

## Phase R0 — prove the fit boundary (complete)

Purpose: prove that the complete authenticated causal corpus can train and reproduce one model
artifact without opening a gameplay or evaluation surface.

Work:

- implement one deterministic train-only integration-fit command;
- require the already-passed readiness proof and load all eight rows without selection;
- fit the existing interpretable ridge option-value model once;
- publish it create-only to the private immutable model store and reopen byte-identical bytes;
- emit only path-free diagnostics for row count, feature support, target variation, conditioning,
  coefficient finiteness, artifact identity, and reload equality; and
- stop and reorient at the fit receipt.

Exit gate: one exact model artifact fits and reloads over the complete eight-row denominator with
zero development reads, predictions used for gameplay, controller actions, teacher queries,
authority changes, sealed Red access, or Crystal access.

Allowed claim: **the causal learning path works end to end**.

Forbidden shortcut: treating in-sample error or an interesting coefficient as model quality.

Completion checkpoint, 2026-08-30: PR 114 published the claim-first train-only fitter, exact main
`f5097982` passed push CI `33320429925/1`, and one learner invocation fit all eight authentic rows.
The private artifact reopened as identical bytes and typed model; every protected gameplay,
development, teacher, authority, sealed, and Crystal effect stayed zero. One earlier launch at an
unrelated initialized store failed before a claim or fit and is retained in the path-free receipt.
R0 may not refit. Its allowed claim is limited to **the causal learning path works end to end**.

## Phase R1 — freeze the clustered design, then build the powered Red curriculum

Purpose: replace an integration sample with enough independent, informative consequences to test a
real model.

The repository currently contains two incompatible future-scale assumptions. The active strategy
correctly retired one-clean-power-run-per-row and permits bounded short scenarios grouped by
immutable upstream lineage. The older `LivingDexCausalCurriculumDesign` still demands 90 train
and 105 development slots backed by 195 distinct physical roots and lineages. Its row-information
checks remain useful; its independence and power schedule is not silently active after the pivot.

Work:

1. **Complete:** the prospectively fixed batches attempted successor ordinals 0–15 once each.
   Twelve settled and four ended during setup; no consumed identity may retry.
2. **Complete:** the final batch measured 6/8 yield and 41.30 examples per outer hour. The full
   corpus is 18/60, covers all seven kinds and 54/54 candidate rows, has rank 11/16, and retains
   three successes versus fifteen failures without outcome-aware replacement.
3. **Complete:** the versioned action-free clustered powered V2 design is implemented and reviewed.
   It preserves 18 prefix examples; allocates 72 attempts across 36 train lineages at maximum two
   per lineage; requires 50 settled train lineages; and retains every information floor below.
4. **Complete, failed honestly:** PR `#119` published the capacity gate as exact main `f1fc3812`,
   CI `33355147814/1` passed, and one action-free census found only 14/36 train, 22/100
   development, and 0/3 contingency lineages. The 103-lineage total deficit and every support
   failure close current-bank gameplay.
5. **Next:** bind the existing clean-power episode generator to that exact census result, add
   prospective train/development/contingency ownership, and prove a bounded one-shot yield tranche
   before population-scale generation. Recensus before any outcome collection. The supply design
   must define the independent unit, maximum scenarios and influence per lineage, cluster weights,
   complete attempted denominator, attrition treatment, train/development ownership, and a fixed
   independent-lineage budget split among fit, confirmation, and unopened contingency use.
6. **Complete in the public design:** power the held-out test in independent lineage clusters under a prospectively conservative
   within-cluster correlation and observed setup attrition. Publish sensitivity at correlations
   `0.0`, `0.25`, `0.5`, `0.75`, and `1.0`; the binding certificate treats correlation `1.0` as
   the worst case unless a separate prospective pilot justifies another bound. A raw row count is
   not a power calculation. Under the existing paired alternative—candidate-only success `0.30`,
   control-only success `0.10`, alpha `0.05`, and power `0.80`—the exact sign test needs at least
   **67 independent evaluable lineage units with no forced losses, or 100 with three forced
   lineage losses**. A V2 design may choose another test or smallest useful effect only before
   outcomes open and must publish its own numeric `K_min`. If available clusters cannot support
   that design, revise the experiment before generating outcomes.
7. On a passing census, generate additional short authenticated Red scenarios for missing kinds and feature directions
   inside the frozen cluster allocation. A full Red replay is not a data-loader.
8. Keep an upstream episode lineage wholly inside one partition. Byte clones, timing variants,
   rehashed states, and sibling scenarios do not become independent because their filenames differ.
9. Retain every settled, failed, and interrupted selected-arm terminal. Never manufacture an
   unselected counterfactual label or replace an awkward row.

Retain these information floors from the existing fit-readiness contract unless a stronger
prospective revision replaces them:

- at least 60 settled examples from a complete prospectively frozen attempted denominator;
- all seven Red-supported direct option kinds, with at least eight settled examples per kind;
- at least 50 distinct selected feature rows and selected-feature rank at least 16;
- at least eight verified successes and eight verified failures;
- at least five varying outcome heads, including varying `verified_success`; and
- ten genuine three-option menu templates or a prospectively justified stronger coverage design;
- at least 18 train semantic families, five locations, and three values on every declared pressure
  axis; and
- bounded lineage influence, full candidate support, no identity-bearing features, no development
  leakage, and an action-free capacity proof for the complete clustered schedule.

The complete bounded successor shows that short-scenario execution speed is not the bottleneck.
The exact capacity census now shows that independent upstream episode supply is. The next session
must qualify a census-bound multi-partition supply design and bounded yield tranche; it must not
return to teacher-route hardening, launch 103 worlds without a yield estimate, or treat additional
correlated rows as independent evidence.

Exit gate: the clustered-design power review passes, then the action-free powered-fit audit passes
that exact versioned contract over the complete train denominator. The existing row-level audit
may be reused as one component; it cannot by itself certify lineage independence.

Allowed claim: **enough Red causal information exists to fit a powered candidate**.

Forbidden shortcut: lowering the threshold after collection, counting correlated siblings as
independent, or using Crystal as extra Red training data.

## Phase R2 — fit once and test on untouched Red lineage clusters

Purpose: determine whether the title-neutral option-value representation learns anything more
useful than frozen non-learning rules.

Work:

- freeze the model configuration, normalizer, utility projection, candidate mask, cluster weights,
  and complete train denominator before fitting;
- fit only on R1 train rows and authenticate the resulting artifact;
- commit all candidate and baseline predictions before decoding development outcomes;
- evaluate on the complete prospectively frozen, lineage-disjoint Red development schedule;
- compare against the preregistered best-of-three envelope: random, cost-only, and
  myopic-completion-greedy;
- keep censored and failed cases in the declared endpoint and use the preregistered cluster-aware
  paired test and worst-case censoring analysis; and
- publish errors by option kind and support status, not private identities.

Before any development outcome opens, freeze `L_total`, the number of genuinely unused independent
lineages available to this experiment; allocate it among training, confirmatory development, and
unopened contingency; and publish the maximum confirmatory candidate count as
`floor(L_development / K_min)`. Exceeding that budget ends the lane. It never licenses reuse of a
decoded development cluster.

The existing V1 reference uses 105 unique development roots, exactly 15 contexts per supported
kind, at least 102 complete pairs, a 50% absolute candidate-success floor, and every incomplete
context scored conservatively as a candidate loss. R1 may retain that design only if capacity and
the clustered pivot are reconciled. Otherwise V2 must replace its denominator and decision rule
before any development outcome opens, preserve at least 80% power at the declared smallest useful
effect after worst-case allowed attrition, include at least 12 development semantic families, five
menu templates, five locations, two values per pressure axis, and aggregate or resample at the
independent lineage level. It may not keep `105` as a decorative row count while treating correlated
siblings as independent.

A failed development partition becomes diagnostic history. It may inform a versioned redesign, but
the same rows cannot be repeatedly tuned against and then described as untouched. A replacement
candidate needs a newly frozen lineage-disjoint development protocol.

Exit gate: the powered model beats the frozen control envelope on the complete paired endpoint,
passes support and censoring gates, and reloads exactly from its frozen artifact.

Allowed claim: **the Red-trained option-value model generalizes to unseen Red causal decisions**.

Forbidden shortcut: promoting from train loss, aggregate accuracy alone, optional stopping, or a
control chosen after seeing results.

## Phase R3 — give the model bounded gameplay authority

Purpose: move from predicting a good option offline to actually choosing and completing supported
gameplay objectives.

The runtime contract is hierarchical:

1. the dependency planner proposes every honest candidate;
2. a hard semantic mask removes known-illegal or known-unsafe candidates;
3. the model ranks the remaining title-neutral options;
4. the selected typed skill executes with closed-loop observation;
5. an independent verifier records the terminal consequence; and
6. the agent replans or abstains rather than silently falling back to the teacher.

Authority advances separately through shadow, intervention-backed, and teacher-free stages for:

- navigation and displacement recovery;
- battle choices, switching, capture, and escape;
- party development, venue choice, rotation, recovery, and evolution;
- storage, resupply, and acquisition execution; and
- high-level goal choice and replanning.

The detailed prospective skill gates remain in
[the model-first roadmap](model-first-roadmap.md). The promotion board must expose successes,
failures, abstentions, teacher interventions, collision/path overhead, battle HP/PP/turn costs,
experience per frame, battles per heal, rotations, faints, blackouts, and unsupported states.

The model first "plays" at the first teacher-free bounded promotion in this phase. R0 and R2 train
and validate a decision policy; they do not themselves play the cartridge.

Exit gate for the hierarchy: on unseen Red development episodes the model completes at least three
consecutive heterogeneous goals with changed resources or state, receives no expected route or
objective list, replans after a supported failure, and reports every intervention or abstention.

Allowed claim: **the model controls the named bounded Red skills and multi-goal decisions**.

Forbidden shortcut: a deterministic skill succeeding while the teacher still chooses every goal,
or a successful episode whose menus each contain only one executable candidate.

## Phase R4 — make the living Pokedex the organizing objective

Purpose: prove that story progress, acquisition, development, storage, and external requirements
are one dependency problem rather than separate scripts.

Work:

- derive Red encounter, evolution, gift, static encounter, fossil, trade, version, one-shot,
  legendary, puzzle, and prerequisite facts from cartridge or authenticated game data;
- build a 151-target completion catalog above the existing 124-registration/120-living single-save
  subgraph; every species excluded from that subgraph must become an explicit version, link-trade,
  mutually exclusive choice, or legitimate-event dependency rather than disappearing from the
  graduation denominator;
- maintain distinct seen, registered, living, stored, evolved, traded, version-blocked,
  event-blocked, and unsupported ledgers;
- classify every declared Red target as currently executable, dependency-blocked, version/trade
  blocked, legitimate-event blocked, or unsupported;
- make the model choose among planner-proposed collection, story, training, storage, resupply, and
  exploration options while typed skills perform mechanics;
- complete unseen bounded chains spanning acquisition, evolution, storage, access unlocks, and
  recovery from a failed catch, depleted resource, full box, or changed evolution state; and
- represent unique legendary puzzles as prerequisite graphs with one-shot risk, not as unexplained
  species-specific button strings.

Red's existing solo contract is an executable subplan, not the final living-Pokedex denominator.
The full 151-species collection requires explicit version, second-save, trade, mutually exclusive,
and event inputs. The agent must ask for or schedule those legitimate external capabilities; it
must never pretend a single cartridge can produce an impossible specimen. A complete teacher for
Blue is not required: shared policies, collection planning, and mechanics remain reusable, while a
thin version adapter exposes different availability facts and a typed trade endpoint. Nonrepeatable
static encounters, gifts, fossils, and branching evolutions must carry explicit one-shot inventory
and irreversible-risk facts into planning and verification.

Exit gate for Crystal entry:

- every Red target has a derived plan or typed external blocker;
- representative unseen chains from all shared collection families complete under declared model
  authority;
- party and storage independently verify retained living specimens; and
- the dashboard can explain the next target, dependency chain, resource risk, and blocker.

This gate deliberately does not require polishing every Red edge case before testing Crystal.
Waiting for a perfect Red walkthrough would optimize for Red before testing transfer. Official Red
story and living-Pokedex graduation continues, but the Crystal falsifier opens once the shared
system has earned the R2-R4 evidence below.

Allowed claim: **the Red hierarchy can plan and execute representative living-Dex work and can
explain the whole Red target space**.

Forbidden shortcut: a species-by-species macro or marking an unavailable target complete.

## Phase R5 — freeze the portable bundle and qualify Crystal entry

Purpose: make the Red-to-Crystal boundary testable before any Crystal outcome can influence it.

Freeze and authenticate:

- feature names, order, ranges, normalization provenance, and supported projection;
- option kinds, outcome heads, utility calculation, candidate masking, and abstention rule;
- model weights and artifact loader;
- semantic capability vocabulary, memory, collection ledger, and dependency-plan schema;
- typed skill inputs, terminals, verifiers, and recovery reasons; and
- the exact Red evidence supporting each granted authority.

The learner-facing bundle contains no species, map, route, ROM-address, private-path, episode,
partition, or opportunity identity. Title-private bindings remain behind the adapter.

Qualify the Crystal side without gameplay or labels:

- the revision-bound Crystal observer produces typed semantic state;
- the adapter projects supported candidates into the exact frozen Red contract;
- unknown or unavailable mechanics fail closed through typed masks and abstention;
- Gen-II additions—day/night, friendship, breeding, genders, held items, phone/weekly events,
  roaming encounters, berries, and Crystal-specific puzzles—are represented as capabilities, not
  guessed through Red defaults;
- the same portable bundle reloads unchanged in both title runtimes; and
- a dashboard can report support, abstention, realized outcomes, interventions, and transfer
  comparisons without exposing ROM-derived state.

The existing unopened Crystal V3 protocol is historical design evidence, not the test for the new
living-Dex option-value bundle. It binds the older goal manager and scores every missing prediction
as incorrect without separating supported from unsupported mechanics, so Codex retires it
unopened for this mission. A newly versioned, prospectively reviewed protocol must use new
identities. No identity is reused merely because it was never executed.

The transfer protocol must compare frozen Red initialization against the exact R2 best-of-three
control envelope **and** a zero-initialized identical architecture on the same prospectively frozen
Crystal contexts. Red transfer is claimed only if frozen Red beats both: the envelope controls for
heuristic-reachable structure, while zero initialization controls for architecture and feature
projection alone. All predictions commit before outcomes, no adaptation occurs during zero-shot,
no optional stopping is allowed, and adaptation receives a separate lineage-disjoint partition.

Crystal evaluation has two prospectively separated endpoints:

- on shared, adapter-declared **supported** mechanics, an abstention or missing prediction is a
  candidate failure; and
- on prospectively declared **unsupported** Gen-II mechanics, a typed abstention is correct boundary
  behavior while an attempted action is a failure.

Unknown capability state is reported separately and cannot be relabeled after outcomes. The
adapter must be able to name gender requirements, held-item acquisition/equip/trade requirements,
phone events, weekly events, renewable berry sources, roaming encounters, and puzzle interaction
before the protocol can classify either endpoint. It may not let global abstention inflate the
supported score.

### Definition of Crystal-ready

The repository is ready to port only when all of these are true:

1. R2 produced a powered, untouched-lineage Red development pass.
2. R3 granted bounded teacher-free authority for the shared navigation, battle/capture,
   party/resource, and goal/replanning surfaces used by the transfer test.
3. R4 classified the complete Red target space and completed representative multi-step living-Dex
   chains under that hierarchy.
4. The exact title-neutral model, schemas, normalizer, masks, abstention rule, skill contracts,
   planner, memory, and collection ledger are frozen and byte-reloadable.
5. The Crystal observer and adapter pass ROM-free and read-only compatibility tests without a
   Crystal route or label.
6. A powered zero-shot protocol, frozen controls, adaptation partition, stop rules, and claim
   boundary have passed statistical and architecture review.
7. The live dashboard reports the evidence ladder, authority matrix, abstentions, blockers, and
   transfer counters.
8. Crystal gameplay contexts, outcomes, labels, predictions, and adaptation remain zero until the
   explicit port decision.

At that point the project can answer “what transferred?” rather than merely “can we make Crystal
run?”

## What happens immediately after the port

This is outside the readiness critical path but fixes the intended direction:

1. **Crystal zero-shot:** run only the frozen shared-mechanic protocol. Compare frozen Red weights,
   zero initialization, and the exact R2 best-of-three envelope on identical contexts. Score
   supported performance and unsupported-mechanic abstention separately.
2. **Crystal adaptation:** after the zero-shot terminal is immutable, train only on the separate
   adaptation partition. Measure teaching/data cost relative to a from-scratch control.
3. **Gen-II capability expansion:** add the smallest title-specific observers and typed skills for
   day/night, friendship, breeding, held items, genders, phone/weekly events, roaming encounters,
   and version/trade dependencies. Do not write a full Crystal teacher.
4. **Crystal composition:** repeat bounded skill and hierarchy promotion before story and living-
   Pokedex graduation.
5. **Platform test:** retain every shared interface that transferred and version only the pieces
   that genuinely required Gen-II information. That delta is the evidence that the next game
   should require less teaching.

## Critical path and forecast discipline

```text
R0 fit boundary
   -> R1 powered causal data  [largest current uncertainty]
   -> R2 untouched Red advantage
   -> R3 bounded model authority
   -> R4 living-Dex hierarchy
   -> R5 portable freeze + Crystal entry qualification
   -> Crystal zero-shot
```

R0 should fit inside one focused session. The remaining duration may not be honestly converted to
calendar time until R1 records settled examples per attempted context and examples per wall-clock
hour from the next bounded batch. R1 is expected to dominate the near-term schedule. R2 is a finite
fit-and-evaluation gate once data exist. R3 and R4 are several bounded promotion cycles, not one
overnight replay. Every forecast update must cite measured throughput and the remaining exit-gate
denominator.

## Session reorientation and anti-drift rules

Every work session begins and ends with the same short record:

1. **Mission:** transferable story plus living-Pokedex agent; Red is curriculum, Crystal is the
   first falsifier.
2. **Current rung:** the one evidence claim this session is allowed to promote.
3. **Reusable capability:** what becomes more general if the work succeeds.
4. **Authority delta:** which choice moves from teacher/fixed logic to the model; `none` is valid
   but must be explicit.
5. **Cheapest falsifier:** the smallest bounded test that can reject the idea.
6. **Measured denominator:** current/required examples, episodes, comparisons, or supported kinds.
7. **Stop condition:** what ends the lane without another patch.
8. **Next gate:** exactly one follow-on decision, not a backlog disguised as an active task.

Operational rules:

- only one learning lane is active at a time;
- no second maintenance session is allowed without a new learning or generalization result;
- a full replay is a final integration exam, never the ordinary training loop;
- unexpected failures remain in denominators and evidence;
- reviewers challenge milestone claims, not every implementation commit;
- Claude owns statistical power, partition integrity, leakage, and claim-boundary challenges;
- Antigravity owns hierarchy, adapter, abstention, portability, and Crystal-mechanics challenges;
- Codex implements and adjudicates against source, tests, evidence, and the mission; reviewer votes
  do not replace evidence; and
- every milestone updates the active state, handoff, narrative, dashboard, and reviewer log before
  the next protected operation.

## Dashboard through Crystal readiness

The dashboard should show one compact mission board rather than route theater:

- current evidence rung and exact next promotion;
- causal train attempts/settled/censored, lineages, cluster weights, kind coverage, feature rank,
  target variation, and examples/hour;
- model/artifact identity, fit status, reload status, and frozen baseline identities;
- untouched Red comparisons, confidence/power status, and errors by supported kind;
- authority matrix for shadow, intervention-backed, teacher-free, and abstain-only skills;
- navigation, battle, party, resource, goal-chain, and recovery metrics;
- living-Pokedex target counts by acquired, living, planned, dependency-blocked, trade/version-
  blocked, event-blocked, and unsupported;
- portable-contract freeze status and Crystal adapter compatibility;
- Crystal access, prediction, outcome, adaptation, and transfer counters, all zero before R5 exits;
  and
- a visible “does not prove” statement for the current rung.

Live game video remains useful for diagnosis and storytelling. It is not the promotion metric.
