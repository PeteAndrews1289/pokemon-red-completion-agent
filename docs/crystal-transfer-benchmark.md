# Crystal transfer benchmark

## Current decision

Crystal is an early falsifier of shared Pokémon knowledge, not a second walkthrough. The first
question is deliberately narrow: do the frozen Red goal-manager weights make better zero-shot
choices than the same model with zero weights on genuinely unseen Crystal contexts?

The active prospective plan is
[`configs/crystal-goal-manager-transfer-v3.json`](../configs/crystal-goal-manager-transfer-v3.json),
SHA-256 `b7d7337161bdad1440b9c0ee8f95b8ec23e27973ee0571242eac5fc742668ad7`.
It contains 27 adaptation slots and 54 sealed-test slots, no cartridge capture, label, prediction,
private path or ROM byte. It explicitly sets private-context authorization to false and requires
independent reviews from Claude and Antigravity before that changes.

The older protocols are history:

- V1 named international Crystal 1.0 and was retired at zero access when the owner supplied 1.1.
- V2 named Crystal 1.1 but used ordinary convex adaptation and a `wins >= 6, losses = 0` endpoint.
  It is retired with 0 zero-shot contexts, 0 adaptation examples, 0 sealed contexts and 0
  predictions opened.

V2 was not merely small. A same-title pilot over already-open Red development evidence showed that
ordinary fitting made Red-initialized and zero-initialized candidates choose identically after 9,
18 and 27 examples. Its endpoint therefore erased the distinction it was intended to test. The old
zero-loss conjunction also had only 34.2% power at a useful 0.70/0.10/0.20 win/loss/tie effect.

## What is implemented without opening Crystal evidence

The reusable substrate remains valuable:

- Crystal projects story, registration, living ownership, evolution, team readiness, safety,
  supplies, storage, control and world knowledge into the same nine normalized pressures used in
  Red.
- The model-facing projection excludes title, species, move, map, coordinate, item, raw address,
  private binding and candidate position.
- Private capability masks cover capture, storage, level/item/happiness/time/trade evolution,
  breeding, time of day, field moves, static and roaming encounters, and puzzle interaction.
- Bank-aware coherent readers validate party, Pokédex, storage and inventory state before exposing
  semantic observations.
- The source model and normalizer are authenticated, candidate menus are identity-free, and the
  plan requires at least three available candidates per context plus answer-position diversity and
  context-dependent reversals.
- `adapt_from_prior` now keeps each candidate anchored to its own initial weights. Red and scratch
  candidates use the same examples, order, optimizer, normalization and prior strength; only the
  prior center differs.
- The V3 generator and parser reproduce one canonical public plan and reject changes to
  authorization, power, endpoint, prior comparison or V2 zero-access history.
- The canonical file embeds every one of the 81 assignments. Adaptation and sealed partitions each
  exhibit all 36 possible pairwise candidate-order reversals, so a later code change cannot silently
  reshuffle the preregistered schedule.

This is a preregistration substrate, not a completed transfer runner. V3 still needs its private
catalog materializer, complete prediction commitment, one-shot outcome evaluator and reviewer
approval. No V3 context may be materialized or opened until those gates exist and both reviewers
approve the exact published commit.

## Pinned target boundary

The target remains Pokémon Crystal international v1.1:

| Identity | Frozen value |
| --- | --- |
| Game ID | `pokemon.mainline:crystal:gbc:international:rev1` |
| Header title | `PM_CRYSTAL` |
| Size | 2,097,152 bytes |
| Revision | 1 |
| SHA-1 | `f2f52230b536214ef7c9924f483392993e226cfb` |
| Source authority | [`pret/pokecrystal`](https://github.com/pret/pokecrystal) at `7a7881d0d62e0ddbd82dcf10e7116807487ac651` |
| Generated-symbol authority | commit `cc6fc04f19c645f5c40f64f8d88b2ab42c7bdde8` |
| Symbol file | `pokecrystal11.sym` |
| Symbol-file SHA-256 | `8a8b7a675bbb0e7b2e18d1604ecae68ac18aa0bd8f879cc58351489352bf8ef3` |

The lawful ROM's path, bytes and exact SHA-256 stay private. Historical uncounted qualifications
proved coherent banked observation and one shared closed-loop starting corridor without creating a
transfer context, label or prediction. Those engineering qualifications are not transfer evidence.

## The 81-slot V3 experiment

| Partition | Contexts | Per goal kind | Role |
| --- | ---: | ---: | --- |
| Adaptation | 27 | 3 | Nine disjoint three-label folds for the mandatory secondary analysis |
| Sealed test | 54 | 6 | Primary zero-shot paired comparison and fold-assigned secondary evaluation |

Every sealed context is assigned to exactly one fold; each fold receives six sealed contexts. The
primary candidates see no Crystal label. The secondary candidates see only their fold's three
declared adaptation labels. The selected answer must appear in varied positions, candidate position
is not a feature, partitions may not overlap, policy contexts must be unique and every menu must
contain at least three available candidates.

The fixed order is:

1. publish and externally review the exact code, plan and path-free catalog contracts;
2. freeze the complete adaptation and sealed catalogs before any prediction or label;
3. commit frozen-Red and zero-weight predictions for all 54 sealed questions;
4. collect all 27 adaptation labels without opening a sealed label;
5. fit each Red-prior and zero-prior fold from the same three examples and commit predictions for
   its six assigned sealed contexts;
6. open every sealed context once, preserving success, failure and interruption; and
7. score the primary and mandatory secondary analyses without optional stopping.

Any schema, candidate, normalizer, optimizer, prior strength or endpoint change after step 2 retires
the entire V3 identity.

## Powered primary endpoint

The candidate is the frozen authenticated Red model. The control has the same architecture,
normalizer, hard masking and candidate menus with all-zero weights. On each of 54 independent
sealed contexts, a paired win means only Red is correct and a paired loss means only the control is
correct. Missing predictions are incorrect.

The decision rule is a one-sided exact sign test conditional on discordant pairs at
`alpha = 0.05`; Red must have more wins than losses and `p <= 0.05`. At the declared smallest useful
effect — win 0.50, loss 0.20, tie 0.30 — 51 contexts are sufficient for 80% power and 54 provide
82.3248% power. There is no zero-loss requirement.

The mandatory secondary report compares prior-preserving Red and zero initialization after three
labels per fold. It publishes paired wins, losses, ties, accuracy and per-goal-kind results, but it
cannot replace or rescue the zero-shot primary endpoint.

## Dashboard boundary

The Pokémon Learning Observatory remains a view-only loopback dashboard. It can show live frames,
semantic state, exact numerators and denominators, independent evaluation units, candidate-count
coverage, interventions and failures. It has no controller endpoint. No Crystal progress bar should
move merely because the plan exists; V3 remains at zero until the reviewed runner performs an
authorized operation.

## Claim boundary

A successful primary endpoint would establish only that frozen Red goal-selection weights improve
zero-shot Crystal goal choices under this benchmark. A successful secondary result would show that
the advantage survives a tightly matched three-label adaptation. Neither establishes Crystal story
completion, battle or navigation transfer, living-Pokédex completion or a universal Pokémon player.

A failure is equally informative if the receipt separates observation, availability masking,
ranking, binding, execution and verification. It must not be hidden by a second Crystal teacher
script or a changed endpoint.
