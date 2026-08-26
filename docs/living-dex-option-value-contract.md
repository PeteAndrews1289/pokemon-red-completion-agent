# Living-Pokédex observed-arm option-value contract

Status: ROM-free shared contract implemented on 2026-08-25; Red adapter boundary implemented on
2026-08-26. This document is subordinate to
[MISSION.md](../MISSION.md), [NORTH_STAR.md](../NORTH_STAR.md), and the generated
[active product state](../ACTIVE_PRODUCT_STATE.md).

## Purpose

The old dependency ranker reduced every collection decision to acquire-versus-evolve and treated
failure of the selected action as evidence that the unexecuted action was preferable. That is not a
causal target. The replacement contract learns only from the arm actually executed and keeps
success, collection progress, downstream unlocks, and costs as separate observed quantities.

The shared implementation is
[`living_dex_option_value.py`](../src/pokemon_red_completion/living_dex_option_value.py). It is a
game-neutral policy and learning boundary. Red and Crystal must supply separate private adapters;
neither may alter the feature names, normalizations, outcome names, or fitting objective.

## Candidate menu

A decision contains two or more executable options and may retain additional hard-masked rows for
diagnosis. Menus may be binary when the game genuinely offers only two meaningful choices, but the
architecture accepts any menu size. Current portable option kinds are:

- acquire;
- evolve;
- trade;
- develop a specimen or party prerequisite;
- manage storage;
- resupply;
- unlock access through a story, field, or puzzle prerequisite;
- explore to resolve missing world knowledge.

Concrete species, maps, coordinates, items, routes, title identifiers, private roots, and binding
identities remain behind `binding_ref`. They are deliberately absent from `policy_dict()`, model
features, dataset hashes used for fitting, and model records.

Unavailable and unknown options are preserved with an identity-free reason but receive zero
behavior probability and cannot be selected. Symbolic living-Pokédex invariants remain hard rules;
the model never learns whether it is acceptable to destroy the only required specimen.

## Normalization V1

Every scalar is finite and lies in `[0, 1]`. Adapters must derive values from live semantic state
and a declared scenario budget rather than from title identity or hand-authored teacher utility.

### Context pressures

- `collection_pressure`: missing required retained specimens divided by the declared living
  collection target.
- `dependency_pressure`: blocked immediate collection successors divided by the current incomplete
  dependency frontier.
- `access_pressure`: incomplete targets currently blocked by access/story/field prerequisites,
  divided by all incomplete targets.
- `resource_pressure`: one minus the fraction of the declared lower-bound consumable requirement
  currently held.
- `storage_pressure`: one minus usable storage headroom divided by declared usable capacity.
- `party_pressure`: normalized readiness deficit against the next declared execution requirement.
- `knowledge_pressure`: unresolved availability or mechanic dependencies divided by the incomplete
  dependency frontier.

Zero denominators produce zero pressure. Every denominator and cap used by an adapter must be
recorded in private execution provenance and summarized without identities in development reports.

### Candidate features

- `completion_gain`: one when the atomic option can add and retain a currently missing required
  specimen, otherwise zero. Compound options must be decomposed unless their maximum completion
  unit count is prospectively declared and used as the denominator.
- `dependency_unlock_gain`: immediate blocked successors the option can make executable divided by
  the current blocked frontier.
- `travel_effort`: authenticated semantic-route action estimate divided by the per-decision action
  budget.
- `execution_effort`: non-travel action estimate divided by that same budget.
- `resource_cost`: required consumable units divided by currently usable units.
- `storage_cost`: net slots consumed divided by current usable headroom.
- `party_risk`: prospectively estimated probability of a faint, blackout, or declared safety-bound
  breach.
- `irreversibility_risk`: fraction of declared one-shot or irreversible constraints exposed by the
  option. An actual living-collection invariant violation is hard-masked rather than represented as
  ordinary risk.
- `uncertainty`: one minus confidence that prerequisites, cost estimates, and execution bindings are
  complete.

All ratios are capped at one. The model also receives fixed semantic-kind indicators and declared
context-by-candidate interactions. It does not receive candidate position.

Adapters must not use row position as a semantic priority. They must produce a replayable neutral
ordering (or a replayable randomized ordering) because the deterministic V1 selector resolves exact
score ties by the lowest row index. Fixed acquire-first or title-specific ordering would otherwise
become a hidden policy during ties.

## Observed outcome

One settled outcome records only the selected arm:

- verified success;
- retained living-Pokédex completion gain;
- newly executable dependency-frontier gain;
- controller-action and emulator-frame fractions of their declared budgets;
- consumable, party-health, and storage costs;
- any irreversible loss.

Readable unchanged and partially changed ledgers are settled evidence. An external interruption,
failed observer, or failed provenance join is censored: the attempted decision remains in the
dataset, but every target is absent and the row is excluded from fitting.

The complete pre-action behavior distribution is logged. Every executable option must have positive
probability and every masked option must have zero probability. Fitting uses capped inverse
propensity weights and the selected candidate vector only. No success/failure class balance is
required, and no outcome-dependent row selection is permitted.

Feature mean and scale use the same capped propensity weights as the ridge objective. ROM-free
qualification must distinguish this from unweighted standardization as well as distinguishing the
reciprocal probability and cap themselves.

This correction covers action selection *within a logged menu*. It does not correct which contexts
or menus the scenario generator emits. The cap deliberately trades variance for bias, and the
initial estimator is neither self-normalized nor doubly robust. Censoring is assumed not to hide
outcomes systematically after conditioning on the logged pre-action state; because long or risky
actions may violate that assumption, every calibration report must include the censoring rate and
a prospective censoring-versus-context/outcome-risk diagnostic.

## Model and claims

The initial model is intentionally inspectable: a regularized linear multi-outcome estimator with
separate heads for benefits and costs. A declared utility combines predicted outcomes only when the
planner must choose. This keeps value tradeoffs auditable and lets a later Crystal adapter reuse the
same outcome heads without inheriting Red-specific utility labels.

Prediction error on observed development arms is a calibration diagnostic, not proof that the policy
plays well. Policy quality requires paired realized-outcome evaluation against random and cost-only
baselines on the same reset/RNG conditions. Sample counts and thresholds must be prospectively
powered from repeatable pilot variance. Teacher agreement is not an authority metric.

The fit report's before/after weighted mean-squared errors are in-sample arithmetic diagnostics.
They may detect a broken fit but may never be cited as generalization, policy improvement, or
gameplay competence.

V1 has 24 features plus an intercept for each of nine outcome heads. The minimum eight-example Red
batch is therefore an underdetermined integration and variance pilot even with ridge regularization;
it cannot support coefficient interpretation, policy-superiority inference, or promotion.

## Current integration boundary: prospective decision-rich captures

The exhaustive legacy-bank census failed the unchanged coverage gate with five train and three
development complete menus. That bank is retired. The active successor is the shared
[purpose-built capture contract](living-dex-purpose-built-capture-contract.md): pre-register a
nonadaptive 10-train/5-development setup campaign, tolerate at most two/one censored setups,
separate deterministic setup provenance from learner supervision, and prove selected-arm kind,
family, and location coverage rather than offered-menu decoration. No setup run is open until that
ROM-free contract is published and the project reorients.

## Previous integration boundary: inventory the legacy bank

The Red adapter, selected-arm collector, calibration coverage gate, and durable materializer
implement items 1–4 below at the ROM-free contract boundary. The next lane must inventory their
authentic repeatable Red inputs without acting, then publish the exact 8+4 plan before collection:

1. enumerate genuine multi-family menus from ledger, dependency, reachability, resource, party, and
   storage state;
2. prove every feature normalization and hard mask before selection;
3. issue exactly one system-random commitment bound to the frozen scenario, partition, and complete
   menu; persist it before controller input; prohibit reissue; then sample with a replayable,
   genuinely non-uniform full-support behavior policy that exercises the declared importance-
   weight cap;
4. execute one selected semantic skill and settle it through the independent ledger observer;
5. generate a small calibration batch without consuming sealed or benchmark roots, and report both
   context/menu sampling coverage and censoring diagnostics;
6. stop before a powered benchmark, Crystal execution, or authority promotion.

Raw callable fixtures are explicitly synthetic and cannot satisfy fit readiness. Counted settled
rows must trace to the existing Red dual-capability or bounded goal-skill semantic runtimes. The
published materializer mutation-tests claim-before-randomization, single commitment issuance,
commitment-before-input persistence, masked/nonselected exclusion, fresh observation binding, and
no retry after claim. The action-free inventory must now prove 8 train scenarios across 4 genuine
option kinds and 3 train families plus 4 family-and-location-disjoint development scenarios, or
stop without lowering that gate. See the
[Red adapter design](red-living-dex-observed-arm-adapter.md) and
[materializer qualification](evidence/red-living-dex-durable-materializer-qualification-v1-2026-08-26.json).
