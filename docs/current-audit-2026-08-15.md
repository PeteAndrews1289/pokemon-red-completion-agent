# Current audit — 2026-08-15

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
