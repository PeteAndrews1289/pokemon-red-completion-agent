# Current Audit — 2026-08-13

## Outcome

The project is ready for an independent pre-test review. It is not yet entitled to claim that the
model generalizes.

The v2 strategic collection contains 36 authenticated, counted examples: 24 train and 12
development validation. Every scenario contributed exactly one successful teacher destination
choice. All 36 assignment IDs and candidate-order-invariant contexts are unique; train and
validation do not overlap; no failed or interrupted choice became an imitation target. The 12
sealed test scenarios remain unopened.

The first strategic destination model is fitted and frozen privately. It reached 91.7% on train
and 58.3% on development validation. The unique cheapest-route baseline reached 54.2% and 33.3%,
respectively. On validation, the model gained three choices over route cost and lost none. The
paired exact two-sided p-value is 0.25, so the correct conclusion is “promising enough for a sealed
test after external audit,” not “statistically proven.”

## What was audited

- All counted episode manifests were authenticated and loaded against an independently rebuilt
  scenario/capture/source assignment.
- Coverage is exact: 36 declared non-test scenarios, 36 loaded episodes, 36 unique assignments.
- The partition audit reports 24 unique train contexts, 12 unique validation contexts, zero
  overlap, zero target conflicts and no missing validation need vocabulary.
- Validation offers 12 unique cheapest-route comparisons, including eight baseline disagreements.
  A perfect scorer could achieve exact p = 0.0078125; the actual model does not.
- The frozen feature schema has 92 columns. It excludes map and destination identity, coordinates,
  objective identity, binding index and candidate position.
- A single shared MLP scores every candidate, and the unit suite checks that permuting candidates
  permutes probabilities and the selected answer.
- Training rejects non-train rows. Model selection rejects any non-validation row, including a
  sealed-test row. Model files are digest-authenticated and schema checked.
- Unseen portable semantic tags receive zero fitted input weights instead of random behavior.
- A targeted mutation pass killed 7/7 probes covering partition leakage, positional shortcuts,
  unseen-tag initialization, baseline direction, exact-p accounting and feature-order drift.

## Audit findings and limits

The main residual risk is experimental, not a known implementation failure. Development validation
was used to choose among seven small regularization/width configurations. It therefore cannot be
treated as an untouched final estimate. The sealed test is the only remaining unbiased comparison.

The model also has narrower experience than its 92-column schema suggests. Every current decision
uses `advance_story + reach_next_challenge` from `overworld + safe_hub`. Those constant context
features correctly carry zero learned weight. A model that understands collection, healing,
training or evolution still requires new demonstrations; Red's current result is one learned
destination-ranking seam, not a general Pokémon player.

The model has not received live authority. Exact movement remains deterministic, and the teacher
still owns destination selection. After sealed offline testing, the next causal step is shadow
scoring on live choices, followed only later by bounded model authority with no teacher fallback.

## Evidence

- [Counted collection audit](evidence/strategic-counted-collection-audit-2026-08-13.json)
- [Model development receipt](evidence/strategic-navigation-model-development-2026-08-13.json)
- [Targeted mutation audit](evidence/strategic-navigation-model-mutation-audit-2026-08-13.json)
- [Claude pre-test handoff](claude-pre-test-audit-handoff-2026-08-13.md)
