# Development stocktake and next-training plan — 2026-08-31

This is a planning snapshot. `MISSION.md`, `NORTH_STAR.md`, and
`ACTIVE_PRODUCT_STATE.md` remain authoritative.

## September 1 update: Celadon relocation was falsified action-free

PR 127 merged as `c9b821a5` after CI `33463086281/1` passed. The source classifier and live
materializer now share the same transition predicate: a Celadon root counts as Route 11 supply
only at the exact Center boundary with the Thunder Badge and a living Fly holder. A published V3
whole-bank census then read all 54 catalog train roots with zero controller actions and zero
emulator frames. None of the four claim-available Celadon roots qualified.

Capacity therefore remains false: 16 available roots resolve to `pokemon_mansion_1f`, zero to a
second venue, and the roster requires seven new captures across at least two venues with no more
than six from one venue. No capture, claim, outcome, prediction, fit, teacher query, authority,
sealed Red case, Crystal context, or replay was opened. Evidence:
[Celadon readiness result](evidence/red-battle-v2-celadon-relocation-readiness-result-2026-09-01.json).

The next cheapest falsifier is one published aggregate readiness census across all nine available
unsupported city roots. It will report map-level Fly, cartridge-composed ground-route, and full
Route 11 transition counts without identifying individual roots. A qualifying reusable map class
may be exposed; otherwise source supply must be redesigned. Learning counters remain **19 train ·
6 fits · 6 verified development · 4 unseen · 0 authority · 0 transfer**.

## Latest checkpoint: the whole bank is real, but the adapter exposes one venue

The train materializer no longer accepts a caller-declared partition, lineage, source digest, or
venue. It hashes owner-controlled source bytes, uniquely joins them to the exact historical
goal-manager catalog and registry, derives the train assignment and root-consumption identity, and
derives the source venue from the loaded state before any controller can act. The existing shared
capture authenticator now uses the same derivation, so generation and later freezing cannot
silently disagree about lineage.

A published whole-bank inventory then hashed 152 retained state files and recovered all 54 unique
catalog train roots. Twenty-five remain claim-available; every state is a safe non-battle boundary
with a living party member. Sixteen available roots are supported by the current materializer,
but all sixteen resolve to `pokemon_mansion_1f`. The frozen two-venue, maximum-six-per-venue roster
therefore fails before materialization despite ample raw supply.

The earlier manifest-only census also overstated reusable supply. None of its four Mansion capture
source states occurs in the exact catalog required by the current freezer. They contribute zero
to this denominator, so the honest requirement is seven new catalog-authenticated train captures,
not three. Nine available roots remain at unsupported aggregate boundaries: four Celadon
Pokecenter, two Lavender Pokecenter, and one each at Cinnabar Mart, Fuchsia City, and Indigo
Plateau lobby.

Current evidence:
[whole-bank venue result](evidence/red-battle-v2-catalog-venue-inventory-result-2026-09-01.json).
The learning board remains **19 train · 6 fits · 6 verified development · 4 unseen · 0 authority ·
0 transfer**.

## Later outcome: exact-main freezer passed; action-free census stopped

PR 123 merged as exact main `00ad6ce1`, and exact-main CI `33451480906/1` passed. A manifest-only
capacity census then found four distinct V2 fresh-train upstream states against seven required and
eight distinct V2 development states before availability checks. Duplicate train manifests do not
create new lineages; legacy V1 manifests lack the upstream-state binding required by V2. No freeze
was created and no capture state, ROM, model, claim registry, outcome, or gameplay was opened.

That old three-root deficit is superseded by the exact-catalog audit above. The next gate is an
action-free readiness inspection for one reusable non-Mansion source relocation, starting with
the four available Celadon-Pokecenter roots and existing Route 11/Diglett's Cave travel machinery.
The learning counters below do not change.

## Bottom line

Training has already begun at development scale. The evidence-backed board is:

- 19 authentic causal Red train examples;
- 6 model fits;
- 6 verified development outcomes;
- 4 unseen comparisons;
- 0 learned gameplay authority; and
- 0 Crystal transfer results.

The most recent battle fit reduced train loss from 2.0818 to 0.7190, but the candidate and frozen
prior made the same correct held-development choice. The candidate was correctly rejected. The
learning pipeline works; learned improvement has not yet been demonstrated.

No training or emulator process is currently running.

## Exact development state

- Published green baseline: `main` at `1d9554923f7973d6c3807445c1c4fc19c65dca1b`, CI
  `33424040364/1`.
- Feature branch: `codex/battle-v2-freezer-20260831` at
  `24108ce667cd427dcb1a8f292b6a25f415f91faf`.
- Pull request 123 remains based on an older committed checkpoint. The coherent successor is now
  locally implemented and will replace that checkpoint after post-commit qualification.
- The parser defect is repaired. The V2 boundary now snapshots every retained, forbidden, and
  screened upstream/root pair under one shared claim-registry lease; derives the pressure
  inventory and deterministic roster from that one snapshot; and publishes one canonical private
  freeze before releasing the lease.
- The freezer reopens its own durable artifact, rejects roster or availability forgery, binds the
  exact retained prefix and original prior, and records zero gameplay, prediction, outcome, fit,
  authority, sealed-Red, Crystal, teacher, or replay effects.
- The focused freezer/authentication suite passes 95 tests. Ruff and focused mypy pass. A full
  pre-commit run passed 6,125 tests and exposed only source-registry rebinding plus one obsolete
  local-runtime assumption; those mechanical bindings are repaired and exact targeted gates pass.
  The definitive full result is intentionally deferred until the coherent commit exists, because
  several provenance tests authenticate committed `HEAD` rather than an uncommitted worktree.
- No V2 roster, fresh V2 outcome, or V2 fit exists.

## What is working, partial, and planned

### Working

- deterministic Red teacher and completion referee;
- typed semantic observation and sole-controller executor;
- cartridge-derived navigation and acquisition knowledge;
- authenticated short-scenario execution;
- claim-first candidate measurement and crash-safe artifact recovery;
- train-only fitting and prediction-before-development evaluation;
- honest rejection and retention of failed or flat experiments.

### Partial

- learned battle, navigation, party-development, and goal rankers;
- the V2 battle inventory/freezer and batch contract;
- multi-goal living-Pokédex composition;
- title-neutral feature and action contracts intended for Crystal.

### Planned or unproved

- a powered Red model;
- current mission-qualified teacher-free gameplay authority;
- autonomous Red story or living-Pokédex completion;
- link-trade and cross-save collection orchestration;
- Crystal zero-shot transfer or adaptation.

## Reviewer findings and Codex adjudication

### Claude — forensic/statistical review

Accepted:

1. The current tree's syntax error is a P0 blocker; no green or qualified claim survives it.
2. Eight V2 development contexts can falsify the immediate-HP representation but cannot establish
   generalization or support authority promotion.
3. Hash and catalog disjointness do not independently prove upstream lineage independence. Add a
   regression showing that timing/RNG siblings of one upstream state cannot enter separate
   partitions.
4. The fixed battle heuristic is acceptable for the V2 falsifier, but any later promotion gate
   must use the preregistered full control envelope rather than quietly comparing against only one
   convenient baseline.

### Antigravity — architecture/transfer review

Accepted:

1. Atomic claim-snapshot locking, private path-free projections, and distinct-menu freezer checks
   are the correct architectural boundaries.
2. Exact Red UI/frame mechanics remain behind title adapters, while policy inputs stay semantic.
3. Do not build raw-button policies, run Crystal prematurely, or pretend trade/event species belong
   in a solo Red executable graph.
4. Exact-main green CI and an immutable denominator remain hard prerequisites.

Rejected:

- Antigravity used a stale checkpoint for its counters and proposed rerunning R1 ordinals 8–15.
  Those ordinals are already complete, the board is 19/6/6 rather than 12/1/0, and the clean-power
  0/12 supply strategy is retired. `ACTIVE_PRODUCT_STATE.md` overrides that portion of its memo.
- Its statement that identity-free Red outcomes are inherently portable to Crystal is too strong.
  Portability is the hypothesis to test, not a current result.

## Mandatory mission check for the next session

| Question | Decision |
| --- | --- |
| Reusable capability | Produce an outcome-blind, crash-safe battle scenario batch that can be reused behind a title adapter. |
| Learned authority target | Move one bounded legal battle choice from frozen prior/teacher control toward an outcome-trained ranker. No authority is granted in this session. |
| Transfer test | Preserve only identity-free supported features and later compare the frozen Red representation against a zero-initialized learner in Crystal. Crystal remains unopened now. |
| Cheapest falsifier | Repair import, prove sibling-lineage rejection, and run one action-free all-or-stop 7+8 census. |
| Time box | One focused session, at most eight hours, before reorientation. |
| Stop condition | Stop if the tree is not green or the census cannot supply the exact diverse 7+8 roster. Do not shrink, replace, clone, or rerun contexts. |

## Ordered next steps

### Session A — restore an executable and trustworthy freezer

1. Move the dangling parser export inside `__all__`.
2. Run parse/import and focused tests before making any broader claim.
3. Finish the inventory/freezer authentication joins already present in the uncommitted diff.
4. Add the timing/RNG-sibling lineage regression.
5. Commit the coherent V2 freezer change so committed-source provenance tests can authenticate the
   exact implementation.
6. Run the full ROM-free suite, Ruff, mypy, docs, public-artifact, registry, and product-focus gates;
   update PR 123 and obtain green exact-head and then exact-main CI.

No ROM, outcome, prediction, fit, sealed Red case, Crystal context, or full replay belongs in this
session.

### Session B — action-free capacity decision

1. Inventory eligible private captures without opening outcomes.
2. Require exactly one retained V1 train context, seven fresh train contexts, and eight jointly
   held development contexts.
3. Enforce independent upstream lineage, venue, level-margin, party/type, three-action-menu, prior
   margin, and hidden-contrast diversity.
4. Freeze all 7+8 or stop. Never shrink or substitute after seeing capacity.

### Session C — qualify the smallest aggregate executor

1. Reuse the V1 claim-first, candidate-branch, durable terminal, and recovery mechanisms.
2. Freeze exact train-only fit settings and the full future control envelope.
3. Publish exact source and require green CI before controller input.

### Session D — collect outcomes and fit once

1. Measure every supported candidate for all seven fresh train contexts.
2. Fit once on the retained-plus-seven train denominator from the original prior.
3. Commit all eight development predictions before opening any development outcome.
4. Measure the complete development denominator and reorient immediately.

Interpretation is fixed:

- no discordance or advantage: retire the immediate-HP move representation and redesign horizon,
  status/setup effects, switching, items, or capture-aware actions;
- positive descriptive signal: preserve it, but design a separately frozen powered untouched-Red
  benchmark before authority promotion.

### After battle V2

1. Apply the short-scenario loop to navigation recovery and party development.
2. Build powered, independent Red evidence for the supported families.
3. Grant one bounded skill teacher-free authority only after an untouched outcome gate.
4. Compose heterogeneous goals and representative capture/evolve/store/trade chains.
5. Freeze the supported portable bundle.
6. Qualify and only then open the Crystal zero-shot transfer protocol.

## Time estimates

These are focused-work estimates, not promises. The fit computation itself takes seconds or
minutes; data eligibility and evaluation integrity dominate the schedule.

| Milestone | Best case | Likely | If the census or representation fails |
| --- | ---: | ---: | ---: |
| V2 data collection can begin | 1 day | 2–3 days | 1–2 weeks after redesign |
| Next legitimate V2 fit and development result | 1–2 days | 3–5 days | 2–3 weeks |
| First new bounded model-selected gameplay development test | 1 week | 2–4 weeks | 1–3+ months |
| Powered untouched-Red advantage | 2–3 weeks | 6–10 weeks | 3–6+ months |
| Mission-qualified bounded teacher-free authority | 3–4 weeks | 8–12 weeks | 6+ months |
| Honest Crystal gameplay entry | 2–3 months | 4–6 months | 9–12+ months |

The powered schedule is uncertain because the earlier capacity census exposed a 103-lineage
deficit and the clean-power supply attempt yielded 0/12. The current small battle V2 experiment is
the cheaper test of whether the representation is worth scaling before another large supply
investment.

## Direct answer: when does training begin?

It already began: six non-authoritative fits exist. The next legitimate V2 fit is likely **three to
five focused days away** if the 7+8 census passes. If by “training” we mean a powered model with
enough independent evidence to earn gameplay authority, the honest unit is **weeks, not days**, and
the date cannot be firm until independent scenario supply is solved.
