# Current Audit — 2026-08-13

## Outcome

Claude's independent review found two real pre-test design defects. Both were caught before any
sealed scenario was opened. The model-capacity defect is repaired; the sealed-test design defect is
measured and remains a hard stop.

The v2 collection is unchanged: 24 authenticated train choices, 12 development-validation choices,
36 unique candidate-order-invariant contexts, no partition overlap and no failed or interrupted
choice promoted as an imitation label. Test remains **0/12 opened**.

The original eight-hidden-unit MLP is now a preserved, superseded development candidate. Its roughly
753 fitted parameters were inappropriate for 24 training examples, and seven validation-compared
trials made its 7/12 validation result weak evidence. It has not been deleted or retroactively
relabelled.

The replacement is a shared linear candidate scorer with **five fitted coefficients**. Model family,
feature subset and regularization are selected using training only: leave one of the 24 training
decisions out, fit on the other 23, and repeat. The best leave-one-out score was 17/24 from a
24-feature alternative. A one-standard-error simplicity rule admitted models at or above 61.6% and
selected the five-feature relative-route scorer at 16/24 rather than the larger alternative.
Validation was not accepted by the selection API.

Only after that choice was fixed was development validation evaluated. The linear scorer reached
**10/12 (83.3%)** versus cheapest route at **4/12 (33.3%)**, with six paired wins, zero losses and
exact two-sided p = 0.03125. This is substantially better development evidence, not a final
generalization result. The validation set has been inspected repeatedly and cannot become a sealed
estimate again.

## Claude finding 1: capacity and selection

The repair removes the high-capacity-only trial grid from the active fit path. The six training-only
feature families now cover one cost-rank coefficient, five relative-route coefficients, seven
candidate-tag coefficients, two combinations, and all 24 training-active columns. Five L2 values are
compared inside leave-one-out training evaluation. The final scorer uses:

- route-cost relative rank;
- route-step relative rank;
- map-transition relative rank;
- field-action relative rank; and
- movement-mode-change relative rank.

There is no shared intercept because it would cancel across candidates. Disabled columns are
serialized with exactly zero weight, feature order is authenticated, candidate permutation still
permutes probabilities, and the loader dispatches between the preserved MLP format and the new
linear format without weakening digest checks. A second adversarial pass killed 13/13 mutations
covering partition boundaries, true leave-one-out construction, the simplicity rule, serialized
weights, exact-p arithmetic and declared-versus-eligible test semantics.

Frozen linear model canonical digest:
`753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1`.
An independent refit after all source restoration reproduced both the private model and public
development receipt byte for byte.

## Claude finding 2: sealed-test capability

The committed v2 generator deliberately created six cost-baseline challenge hypotheses in
validation and **zero in test**. A perfect scorer needs at least six teacher-versus-baseline
disagreements for a two-sided paired exact p below 0.05. The current test specification guarantees
none, so spending it now could produce an evaluation that is incapable of answering its own
question.

A new ROM-free audit inspected only committed scenario metadata. It accessed no private capture,
episode, live route cost or model prediction. Ten of the twelve public test frontiers are
structurally eligible for a local non-teacher alternative, but eligibility is only a design option;
it is not a measured baseline disagreement. The original sealed design therefore remains blocked.

A replacement one-shot plan is now frozen without modifying the historical v2 registry. It gives
the twelve source test frontiers new evaluation-case identities and places all ten eligible cases at
the declared non-teacher region. It binds the exact five-parameter model, source bundle, development
receipt and source scenario registry. It also declares ties incorrect, consumes failed or interrupted
opened cases, forbids omissions and reruns, and requires every result to be published. Plan digest:
`ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b`.

This plan repairs prospective capability; it does not manufacture measured disagreements. Those
remain unknown until the frozen plan passes external audit and the owner authorizes private access.

## Stop line and next work

Do not open, preflight, materialize or score a private test capture yet. The safe order is:

1. independently audit the linear implementation, train-only selection receipt and structural
   test-design receipt;
2. audit the replacement plan, its ten structural challenge hypotheses and all conservative scoring
   rules;
3. publish the exact source and require green CI;
4. obtain explicit owner authorization for the frozen plan; and
5. only then measure baseline disagreements and execute the one-shot comparison, publishing every
   result whether favorable or unfavorable.

A 12-case test can establish a very large paired effect but will still have a wide uncertainty
interval. A later, larger cross-context evaluation is required for a precise performance estimate.

## Evidence

- [Counted collection audit](evidence/strategic-counted-collection-audit-2026-08-13.json)
- [Superseded MLP development receipt](evidence/strategic-navigation-model-development-2026-08-13.json)
- [Linear model development receipt](evidence/strategic-navigation-linear-development-2026-08-13.json)
- [Linear byte-reproduction audit](evidence/strategic-navigation-linear-reproduction-audit-2026-08-13.json)
- [Sealed-test design audit](evidence/strategic-sealed-test-design-audit-2026-08-13.json)
- [Replacement sealed-plan freeze](evidence/strategic-sealed-evaluation-plan-freeze-2026-08-13.json)
- [Original targeted mutation audit](evidence/strategic-navigation-model-mutation-audit-2026-08-13.json)
- [Linear and sealed-design mutation audit](evidence/strategic-linear-and-sealed-design-mutation-audit-2026-08-13.json)
- [Linear pre-test audit handoff](claude-linear-pre-test-audit-handoff-2026-08-13.md)
