# Current audit — 2026-08-15

## Reservation identifier adjudication

Claude's immutable reservation audit found one medium-severity claim defect: the planner compared
inventory checkpoint IDs directly with prior root-lineage IDs, and its unit fixture used the same
string in both roles. Codex accepted the finding and resolved every private inventory checkpoint
through the frozen historical context catalog and the exact registry at that catalog's source
commit. The resulting path-free counts are:

| Partition | Inventory | Canonical-root matches | Legacy checkpoint-alias matches | Exact-state matches | Canonical-root or state |
|---|---:|---:|---:|---:|---:|
| development | 27 | 0 | 0 | 0 | 0 |
| train | 54 | 0 | 1 | 1 | 1 |

The alias and state match identify the same already-excluded venue-support entry. None of the
fourteen reservations overlaps prior evidence by resolved canonical root or exact state. The
reservation remains valid because the independent state-digest backstop did the real exclusion;
the old claim that checkpoint identity itself proved root-lineage exclusion was false. New code
now reports these effects separately, requires a complete unique checkpoint-to-root mapping and
keeps paths and identities private. The Red preflight also resolves every reservation through the
same historical catalog and freezes its capture-time canonical lineage into the prospective
binding. No controller, teacher, model, outcome or authority counter advanced. A future
reservation-schema revision should store that canonical lineage directly rather than preserving
the legacy alias field.

## Concrete Red preflight and independent Cave measurement boundary

Codex implemented the missing Red-to-shared party adapter and tested it against the real private
8+6 reservation plan without controller input. It derives evolution reachability from the
cartridge, registered/living needs from the coherent all-storage census, living-retention risk from
specimen multiplicity, role pressure from the declared roster, and health/PP/survival from the live
party and measured venues. The learner receives only normalized title-neutral rows and digests.
The balance contract is now consistent across inventory and projection: level floor 60, maximum
spread 5, party size 6, zero faints.

Real result: 14 reservations accounted for; 12 direct questions inspected; 2 natural-middle-PP
preparations pending; 7 bindings validated in memory. All five venue reservations produced exactly
two candidates, with one unavailable solely as `insufficient_venue_evidence`; none collapsed to a
forced one-candidate question. Snapshot/menu digests change when semantic input changes, raw and
semantic party drift fails closed, and the preflight rejects a same-shape binding built from
different candidate features. Durable catalog writes, actions, labels, predictions, outcomes,
sealed Red, Crystal and authority all remained zero.

The missing Cave evidence is now separated from learner questions by the
[prospective measurement plan](evidence/red-cave-venue-measurement-plan-2026-08-15.json). Its open
train support root is absent from all fourteen reservations and all teacher/venue-prior support. It
uses the same progress/safety/cost measurement contract as Route 11, exactly one fixed venue and one
bounded level-22-to-26 evolution. An immutable private artifact must open before input; any input
forbids retry. Candidate menus, teacher/model calls, learner outcomes, sealed data, Crystal and full
replays are structurally excluded. A real read-only preflight authenticated the state, envelope,
ROM, private plan, prior registry and ready party without mutation.

Disposition: source candidate ready for publication and independent review; live measurement not
authorized yet. Honest counters: priors 1; reservations 14; in-memory bindings 7; durable menus 0;
outcomes 0/14; fits 0; authority 0. Next: exact-head CI, Claude's adapter and one-shot boundary
audit, one Cave execution if approved, distinct-commit compatibility/composition, then the two PP
materializations and exact 8+6 freeze.

## Question-root reservation and PP-materialization boundary

Exact head `3ee15fd60df5c64fbf22695f4589a9b799efbe70` passed CI run `31900603291`.
Claude's forward H2/M2/L2 recheck killed 28/28 valid mutations and returned **APPROVE** for a
read-only non-sealed PP inventory and prospective 8+6 construction only. Codex repeated the full
81-checkpoint inventory and reproduced its prior hashes and counts: 54 train / 27 development,
30 / 14 semantic contexts, 48 / 24 apparently multi-candidate-ready, health high/low/middle and
level/none evolution routes in each partition, but high PP only in both.

The accepted implementation adds strict private-inventory deserialization plus a non-executing
question reservation plan. Input files are authenticated before use. Teacher-prior and venue-prior
support roots/states are excluded, roots/states/envelopes cannot repeat, and each partition must
meet the exact readiness-shaped source constraints. The real private plan reserves 8 train and
6 development roots, split 4/4 and 3/3 across trainee/venue choices, with all four completion goals,
three health bins, two evolution-route kinds and eight/six distinct semantic signatures. Plan
digest: `9097f73eecaf0e38949fb6e76b0cc7a3c8bafa50c353b60a87f77e5519f4e30d`.

The local gate passes 3,550 non-integration tests, three intentional deselections and one expected
failure, Ruff, mypy over 227 source files, privacy/documentation checks and all four generated-
registry checks. Working source bundle:
`d4c7953af2cada31f1fd4cf45d14939d42d270383d36efa8793aa5389a16439f`.

The PP protocol digest is
`fcc0d4ae4260dee271bc4affe7af1187031d7382c8a4ff5568e7ba569c1cee87`. Exactly one source in each
partition is reserved to stop at the first natural post-battle middle-PP state. It forbids memory
edits, healing before capture, candidate outcomes, teacher queries, predictions/fits, sealed access
and replacement. A faint, persistent status or unintended party/storage/story mutation aborts the
identity. Any surviving state must be newly authenticated and inventoried before candidate
projection.

Disposition: **source roots reserved; catalog not frozen**. The
[public receipt](evidence/party-development-question-reservation-2026-08-15.json) exposes no private
root/state/path or candidate values. Priors 1; reservations 14; menus 0; outcomes 0/14; fits 0;
controller/teacher 0; sealed/Crystal 0; replay 0; authority 0. Remaining blockers are concrete Red
bindings, two PP materializations and a second compatible venue prior. The stale Cave result is not
silently promoted.

## Claude approval and one-prior composition

Exact head `3a24a2e688ba890c045f163db3734b6cad2034ec` and CI run `31896779190` were immutable and green.
Claude reproduced the source qualification under Python 3.11.15 and 3.14.3: 43 elements, seven
exact waivers, identical aggregate digests, 7/7 independently recomputed historical/current waiver
pairs and 42/47 valid mutations killed. The prior blockers—on-path projector coverage, whole-class
venue/grinding semantics and aggregate-field rederivation—were closed.

Codex accepted Claude's **APPROVE** verdict at its narrow boundary and composed exactly one private
Route 11 prior. Its registry file digest is
`102fc95256673d5b9696a152928b0edcf3d2480b6519102fadd62d19ddc2a618`; the tracked
[public summary](evidence/red-route-11-venue-prior-composition-2026-08-15.json) is path-free. The
composition accepted one venue observation, rejected the stale Cave sibling and made zero ROM
reads, emulator starts, controller actions, teacher queries or outcomes.

Disposition: prior composition complete. Claude's H2/M2/L2 forward conditions were accepted and
are closed locally at exact source `16ed83d`. Eight module-assignment elements cover all
execution-bearing modules; a simulated committed `MINIMUM_FIGHTABLE_SHARE` mutation fails after
loaded/current agreement; PEP 695 minimal pairs isolate only `type_params`; and a sentinel pins the
closure call from `attest` independently. Python 3.14 passes 55 focused tests and Python 3.11 passes
54 with one expected skip. The full gate passes 3,508 tests, three deselections, one expected
failure, Ruff, mypy over 223 files, public/docs and four generated registries. Source bundle:
`ce43f6d9978d02fe36bf3f1fbb4b1aa7e78b67aab135f6c7893167d1745a67e4`.

Publication, exact-head CI and Claude's narrow immutable-delta recheck remain mandatory before
catalog reuse. Priors 1; menus 0, outcomes 0/14, fits 0, sealed/Crystal 0, replay 0 and authority 0.

## Route 11 closure rejection and remediation

Exact head `7f4d8de` passed GitHub CI, then Claude performed the required read-only audit under
Python 3.11 and 3.14. After correcting its own mutation harness so mutants—not the target checkout—
were actually imported, it killed 34 of 43 mutations and returned **REJECT**. Two changed projector
functions and two new choice-set helpers were live under `run_red_team_balancing` but outside the
attestation. `TrainingVenue.__post_init__` and `GrindingArea.identity` could change without stopping
composition. The operational boundary re-derived `current_elements_sha256` but trusted supplied
`unchanged_elements_sha256` and `waiver_allowlist_sha256`. Nine individual test mutations survived.

Exact source `41f6fff` closes the accepted findings. Forty-three exact elements cover the complete
venue/grinding contracts, six candidate entry points, their same-module transitive call closure,
candidate/domain types and external team-policy functions. Seven exact waivers replace the previous
three without a module-wide exception. A loaded closure check refuses undeclared dependencies, and
the operational boundary independently re-derives current, unchanged and waiver identities.
Dedicated falsifiers cover each learning-eligibility flag, loaded walker identity, list/tuple tags,
non-empty PEP 695 type parameters and unsupported AST scalars. Comments remain non-semantic;
docstrings remain committed.

Python 3.11 and 3.14 agree on the 43-element digest
`f2cb0aa8bd469c38b24b97f1139208601c96d1011fe28dcf6898abba06c330c5`
and seven-waiver digest `5558e7ae6d70bb50fbd63d3397c3f378c9b24683c286a71c4962c6ddf131c65d`.
The full local tree passes 3,503 tests, three skips and one expected failure; Ruff, mypy over 223
files, documentation/public-artifact checks and all generated registries pass. Executable bundle:
`4db4c1eefb97eaf0b740857aa81e2fd3292b82693af54877f6e9711b3e5913aa`.

Disposition: **repair complete locally; exact-head CI and Claude delta re-audit pending**. No prior,
menu, outcome, fit, controller, teacher, sealed case, Crystal context, replay or authority advanced.

## CI portability audit and repair

The approved `fetch-depth: 0` workflow change fixed CI's inability to read historical source. The
next exact run reached that source and failed 33 qualification tests because Python 3.11 and 3.14
produce different `ast.dump` text for the same semantics. This was an interpreter portability
defect in the attestation, not evidence that Route 11 behavior, the teacher or a model had run.

Source `f2ecc7961c811d57d5572366dd7ec8a879e3c502` replaces `ast.dump` hashing with a schema-tagged,
typed recursive AST document. Every semantic field is committed; only empty `type_params` fields
introduced by newer Python are omitted, and unknown scalar types fail closed. Exact waiver hashes,
walker identity, attestation aggregates, registry goldens and encounter-execution goldens were
regenerated. Source bundle:
`c158aaffa4906ebb77263644f421947aac3e5c1c096aae36c10b8b1be7d9c2cf`.

The same canonical golden was reproduced under Python 3.11 and Python 3.14. Python 3.11 passed 36
focused tests; Python 3.14 passed 85 focused tests. The full tree passed 3,489 tests, three skips,
one expected failure, Ruff, mypy across 223 files and every registry check. The remaining gate is
one exact publication-head CI run followed by Claude's adversarial source audit. Protected counters
remain unchanged: priors 0, menus 0, outcomes 0/14, fits 0, controller/teacher 0, sealed/Crystal 0,
replay 0 and authority 0.

## Three-agent role and execution-plan audit

The current work no longer treats Codex, Claude and Antigravity as interchangeable assistants.
[The active handoff](current-agent-handoffs.md) assigns one source owner and two non-overlapping
falsification lanes. Codex implements, integrates, validates, publishes and adjudicates. Claude
attacks provenance, mutation resistance, leakage, statistics and claim boundaries on immutable
commits. Antigravity attacks mission value, sample efficiency, title neutrality, transfer and
living-Pokédex coverage. Reviewers remain read-only by default; consensus does not grant authority.

The operational bridge is now explicit: CI repair and green head; Claude requalification; one
private Route 11 prior; PP-diversity search or a separately reviewed materialization plan; 8+6
question freeze; dual catalog review; one-shot outcome collection; one descriptive fit; then
expansion toward the 120-pair party gate and a Crystal falsifier. The first fit cannot promote
authority. Every phase records a capability, authority boundary, transfer test, cheapest falsifier,
time box and stop condition. This is coordination maintenance for a named learned experiment, not
another development subsystem.

## Historical Route 11 evidence compatibility repair

Claude returned **REJECT** on the first concrete venue-prior composer. The measured Route 11 trial
and its ratios were truthful, but five surrounding claims were not sufficiently proved: the
historical source and bundle could be forged; an observation from `00499bc` was assigned a current
operational contract; the stale Cave sibling count was a literal; statelessness was inferred from a
missing factory; and seven of nine operational mutations survived the focused suite.

Exact source `0d89d85edbe19ff639f5983123759787c87292e7` implements the remediation. A typed
source-compatibility attestation now reconstructs the historical and current executable bundles,
extracts 19 exact AST elements from each commit, compares the loaded runtime to the current commit,
and fires exactly three committed waivers. Those waivers cover only `fresh_walk_to_grass`,
`run_red_team_balancing`, and the default-zero additions to `TeamTrainingExecutionSummary`. A stale
or extra waiver fails. The operational contract has independent golden coverage for policy,
encounter execution, recovery, battle timing, accounting, measured evidence and walker identity.
Trial 1 is parsed as a stale Cave observation and must satisfy its own objective, battle, faint,
evolution, transition and accounting facts before it can be rejected.

Local results: 3,488 passed, three skipped, one expected failure; Ruff clean; mypy clean across 223
source files; collection, goal-manager and strategic registries reproduce exactly. Committed source
bundle: `419a12882defaa678dc9f5a876f9cd43985e6d79784b917b91022145e30cf117`.
This is a remediation candidate, not an approval. GitHub CI and Claude's exact-commit mutation
re-audit remain open. No registry has been materialized and every protected counter remains zero.

## Completion-constraint adjudication and causal-mask update

Exact source `587fb18` upgrades the prospective party binding/catalog to v5 and its menu document
to v4. A candidate's availability and unavailable reason must align exactly: available means no
reason; unavailable means one typed, title-neutral cause. The adapter emits
`insufficient_venue_evidence` for a viable venue without compatible frozen prior evidence. The
ordered cause vector is public only as portable vocabulary and is committed into the menu digest;
changing it after freeze invalidates the binding.

Claude independently verified exact source `587fb18` and passed 59 focused tests in a temporary
copy. Mutations that removed the cause from the menu digest, invented a default cause, changed the
adapter's cause or emitted no cause were killed by semantic tests. The three agreement guards were
mutually redundant rather than decorative: each survived alone, but removing all three together
failed. No causal-reason drift channel was found. Claude returned **APPROVE** for source
qualification and input materialization/freeze only, conditioned on verifying every real mask as
`insufficient_venue_evidence` or adding the missing producer before freeze.

The full gate passed: 3,435 tests, three intentional integration skips, one expected failure, Ruff,
mypy over 222 source files and all generated registries. Source bundle:
`8f474e2fee84038face3b51ddd642252b5c7ad98e84c12522aeaac7201cb7fc2`.

The source audit also changed the disposition of Antigravity's product review. The requirements
were valid, but four were already implemented:

- `GoalSituation`, `GoalStateEvidence`, `PokemonRedGoalStateAdapter` and goal offers expose
  resource/storage pressure and typed causal availability;
- collection observation and the Red PC specialist cover party, all boxes, active-box capacity,
  deposit/withdraw/switch work, capture stock and immediate capture slots;
- `ResourceEconomyState` normalizes reserve renewal/affordability while live Red resupply skills
  privately check `player_money` and exact cost;
- campaign/Pokédex contracts model version exclusions, explicit trade links, externally unreachable
  species and consolidation; and
- `EvolutionSemantics.feasible_now` is already a party-model feature for level, item, trade and
  conditional evolution routes.

The genuine missing seam was explaining a masked party candidate. Exact `587fb18` closes it. A new
completion-context subsystem would duplicate working layers without increasing learned authority.
Autonomous cross-save acquisition and consolidation remain later product work; they are not evidence
that the 8+6 party-input catalog must be blocked.

No experiment counter advances: concrete menus 0, priors 0, outcomes 0/14, fit false, controller
and teacher 0, sealed Red and Crystal 0, replay 0, authority 0. Next: compatible prior composition,
depleted-PP context discovery/materialization, and exact 8+6 input freeze. Execution remains
closed. See the [causal-mask qualification](evidence/party-development-causal-reason-qualification-2026-08-15.json).

## Prospective outcome-join hardening update

Exact source `85ae8786412846667b9082dc6f1b344e580cef4d` closes the last known
question-to-result mutation gap. It passed 3,432 non-integration tests, three integration
deselections, one expected failure, Ruff, mypy across 222 source files, public-artifact,
documentation and all generated-registry gates. The final source-bundle digest is
`76c43d93b68596efffffb753e979c42fec2cf2d0b1046db2f941f34cd5313da1`.

The generic outcome contract now supports an optional prospective-binding digest without changing
historical v1 rows. A bound row is v2. For party development, that digest commits the exact ordered
feature contract, completion objective, candidate feature rows and availability mask, source,
semantic snapshot, and shared/per-venue evidence. The adapter requires the typed binding, preserves
masked candidates and rejects a well-typed mismatch immediately.

Claude's audit of the first join (`75edcb1`) found four gaps in test distinguishability rather than
a known production bypass. The final commit adds independent oracles for the immediate join guard,
objective contribution, frozen feature-name contract and unavailable-candidate path, plus direct
sensitivity checks for candidate rows and both shared and venue-specific evidence. Its exact
recheck approved materialization and found one S4 oracle gap; a 3,433rd publication-tree test now
distinguishes the frozen vocabulary from a live constant.

Antigravity approved the hardened binding and raised five product constraints. The newer audit
above records the corrected disposition: four already existed at the proper hierarchy levels, and
exact `587fb18` closes the genuine causal-mask gap. The original review is preserved in
the [join-hardening receipt](evidence/party-development-prospective-outcome-join-hardening-2026-08-15.json).

The finding does not advance the experiment counter. Concrete Red menus and venue priors remain
zero; outcomes remain 0/14; no controller, teacher, fit, prediction, sealed Red, Crystal, replay or
authority occurred. The next bounded step is compatible evidence and PP-
diverse non-sealed context discovery. Only after those exist may the
exact 8+6 inputs be materialized and frozen. Execution remains closed.

## Construction checkpoint update

Exact source `4b4e267dea06599c2f17a6b2570bc9091440bc33` implements the missing
title-neutral menu adapter and venue-evidence registry. It passed 3,415 non-integration tests, three
integration deselections, one expected failure, Ruff, mypy across 222 source files and every
privacy/documentation/generated-registry gate.

This closes the code-shape part of risks 1 and 2 below, not their concrete-data part. The reusable
adapter binds every private fact that can affect projection into one semantic snapshot. Trainee
comparisons hold one evidence-backed venue fixed; venue comparisons become unavailable when their
prior is missing or bound to an obsolete operating contract. Prospective rows now authenticate the
snapshot and registry as well as the menu. Root/state overlap with prior-support evidence and
cross-snapshot menu reuse are rejected.

No Red menu has been materialized and the frozen registry has zero entries. The Route 11 V2 receipt
is a candidate for one typed prior. The old Cave outcome used the pre-repair traversal behavior, and
the post-repair Cave qualification did not measure full training yield/recovery, so Cave cannot yet
be represented as a current complete prior. PP remains high-only. Outcomes remain 0/14; no fit,
teacher query, sealed access, Crystal context, replay or authority occurred. External audit of exact
`4b4e267` is the next gate. See the
[path-free source qualification](evidence/party-development-title-neutral-input-contract-2026-08-15.json).

## Outcome

The repository now has a provenance-bound, inventory-backed party-learning boundary aligned with
the stated end product: an agent that can complete Pokémon games while building and retaining a
living Pokédex. Exact source `7190be6b979e51534f033b5ac9c1782093de996d` passed 3,394 local
non-integration tests, 220-source-file mypy, Ruff, public-artifact, documentation and generated-
registry gates.

The exact historical v1 model and the three lineages that established/evaluated it are embedded in
the completion-aware v2 prior. A read-only pass inventoried 81 open Red checkpoints. Prospective
catalog rows and per-partition diversity gates now prevent outcome reuse, prior overlap, mutated
menus, missing venue evidence and duplicate-save inflation. This is still pre-collection:
completion-aware outcomes are 0/14 and fitting has not begun. No new Red candidate executed, no
teacher label was requested, no sealed case or Crystal context opened, and no authority changed.

Claude approved the boundary for documentation and catalog construction, with one S3 finding:
inventory PP was divided by a theoretical 256-point storage ceiling. Exact fix `f1cb3a4` now
reconstructs each observed moveset's own Gen I maximum, including its packed PP Up count and the
cartridge's seven-point per-use bonus cap. The corrected inventory has 30 train / 14 development
semantic contexts and only the `high` PP bin in both partitions. That is a useful failure: the 81
states do not yet satisfy the two-PP-bin gate, and the dashboard says so before collection. The
corrected publication tree passed 3,398 non-integration tests, three integration deselections, one
expected failure and every local quality/privacy gate.

## What the audit found

The historical team-development model is valid evidence of teacher imitation, but it is not an
adequate outcome learner. Its 27 features describe levels, health, PP and encounter bands. They do
not describe evolution distance/method, living-retention risk, collection progress, party-role
completion, emergency escort, survival margin or travel/recovery/reliability cost.

The remaining goal-manager party roots are byte-independent but mostly share the same six-member
roster and level pattern. Their principal variations are health and status. Repeating the old
two-venue race across those roots would create counts faster than semantic coverage and could train
the current Cave/navigation behavior as if it were a universal venue preference.

## Implemented boundary

- The v1 schema/model is unchanged and remains reproducible.
- Teacher-free trainee and venue menu projection preserves counterfactuals even when hidden identity
  prevents a valid teacher label.
- V2 has 66 identity-free features: the exact 27-feature v1 prefix plus 39 completion semantics.
- The v1 MLP embeds exactly: all initial scores and probabilities are identical; new input weights
  begin at zero.
- A 15-criterion objective orders blackout safety and completion retention before primary-goal
  progress, collection/evolution/role gains and efficiency.
- Only complete measured menus produce targets. Censored and partial evidence cannot.
- Tied winners use a target distribution rather than an arbitrary winner.
- Train-only outcome updates remain anchored to the frozen prior.
- Consumed outcome roots/states are stored in the model and duplicate consumption fails closed.
- Development compares prior/update on the same decisions and reports a paired exact test over
  discordant correctness pairs plus winner-probability change.
- Model artifacts authenticate by file digest and round-trip under a versioned schema.

## First-fit gate

The code will not call a catalog fit-ready until all of these are true:

- at least 8 independent learner-eligible train preferences;
- at least 6 untouched learner-eligible development preferences;
- at least two completion goals in each partition;
- trainee and venue menus in each partition;
- at least one menu with three or more candidates;
- at least two health bins, PP bins and evolution-route kinds; and
- complete prospectively frozen evidence for every candidate in every venue menu.

This gate authorizes only a descriptive first learning curve. It does not replace the Milestone 4
promotion gate: 120 paired unseen Red episodes, explicit safety/efficiency/evolution requirements and
the later 54-context Crystal initialization comparison.

## Risks still open

1. The generic title-neutral projection contract is implemented, but no concrete private Red
   snapshot has yet been projected into a frozen v2 candidate menu; inventory readiness remains a
   diagnostic estimate.
2. The venue-prior registry type is implemented but its concrete registry is not frozen. Every
   available venue must be supported by evidence that
   predates its candidate outcome, and the current trial may never describe its own input.
3. No PP-depleted context exists in the current 81-state pool. Search already-authenticated,
   non-sealed captures first; if none qualify, preregister a separate bounded materialization step
   rather than spending a candidate outcome to manufacture its own readiness evidence.
4. The exact 8-train/6-development catalog is not selected. Candidate-menu widening must represent
   genuine alternatives rather than copied saves, arbitrary permutations or continuous-value
   variations of one semantic decision.
5. Six development outcomes allow a narrow descriptive comparison, not a general transfer claim.
   Report paired discordant correctness and winner-probability changes exactly; do not convert an
   underpowered result into promotion language.
6. The current dashboard is a truthful readiness page, not a live training page. It must advance
   only from authenticated prospective outcomes and model artifacts.
7. The representation remains Red-only evidence. Crystal stays untouched until the prospective Red
   curriculum has produced and passed its bounded outcome gate.

## Ordered next work

1. Preserve Claude's narrow approval and the closed PP-calibration finding. Run a final serialized
   recheck on a clean exact commit; use Antigravity as an independent second reviewer for the final
   frozen catalog, not as automatic authority.
2. External-audit the exact title-neutral adapter, then use it read-only to materialize private Red
   bindings plus identity-free trainee/venue menus whose exact feature and availability hashes match
   the prospective catalog.
3. Compose and freeze the venue-prior registry from evidence that predates every outcome. Begin
   with Route 11 only; keep Cave unavailable until post-repair evidence measures the full contract.
4. Inventory already-authenticated non-sealed PP-depleted contexts. If the archive has none, freeze
   a bounded PP-context materialization plan with no learner outcome or teacher target.
5. Select the smallest exact 8-train/6-development catalog that genuinely passes every partition
   and semantic-diversity gate. Do not use the near-duplicate Cinnabar roots merely to reach a count.
6. Publish exact-source path-free catalog and one-shot collection plans, require both external
   reviews, green CI and read-only preflight, then execute each train candidate once with immediate
   private durability. Keep development outcomes untouched until the train model is frozen.
7. Fit from the authenticated prior, evaluate paired development evidence and hold authority. Do
   not open the 120-episode promotion gate, sealed Red or Crystal from this first curve.
8. Keep living-Pokédex requirements in every adapter/menu now. Resume executable capture, storage
   and trade expansion after the Milestone 3 unseen battle gate rather than silently deferring it.

Canonical path-free receipts:

- [`party-development-completion-v2-source-qualification-2026-08-15.json`](evidence/party-development-completion-v2-source-qualification-2026-08-15.json)
- [`party-development-v2-prior-initialization-2026-08-15.json`](evidence/party-development-v2-prior-initialization-2026-08-15.json)
- [`party-development-v2-checkpoint-inventory-2026-08-15.json`](evidence/party-development-v2-checkpoint-inventory-2026-08-15.json)
- [`party-development-v2-readiness-2026-08-15.json`](evidence/party-development-v2-readiness-2026-08-15.json)
