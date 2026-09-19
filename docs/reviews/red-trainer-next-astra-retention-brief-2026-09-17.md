# Next Astra decision brief — trainer attack retention

This is a focused review of a **failed predeclared TRAIN gate**. Read the [warm continuation evidence](../evidence/red-trainer-warm-attack-retention-2026-09-17.json), the [corrected cold-start fit](../evidence/red-trainer-mean-return-refit-2026-09-17.json), and the [prior Astra review](red-trainer-astra-focused-review-2026-09-17.md). Keep the 52 authenticated TRAIN cases and consumed DEVELOPMENT battles in their original partitions. No gameplay, fit or promotion is requested of the reviewer.

## What changed

The target defects found in the previous review are repaired: among 80 distinct head inputs, none of the corrected soft targets prefers an action more than 0.02 below the best average return. The one cold-start 52-case fit still missed original-44 attack retention by 0.0017 (0.0571 versus 0.0554). The authorized next experiment initialized only its attack head from the older 44-context model and ran 100 attack updates on the corrected TRAIN targets; control and switch heads used the unchanged 2400-epoch schedule. Exact model and receipt hashes are in the evidence. No fresh battle was played.

The continuation failed more clearly: original-44 attack regret **0.08566**, full-52 attack regret **0.08497**, versus ceilings **0.0554** and **0.0648**. Complete-action regret **0.11260** passed its **0.1609** ceiling. Only two original attack predictions flipped. Case 34 gained 0.0189 reward; case 43 lost **1.6276**. Cases 34 and 43 have the same visible species matchup but different visible HP, level and derived move inputs, so they are not an identical-input contradiction.

The objective is now the sharper concern. Starting from the older attack weights, cross-entropy on the corrected 28 unique attack inputs improved **0.78434 → 0.77082**, while mean observed-return regret worsened **0.04475 → 0.08497** across all 52 cases. The decisive case 43 has action returns **0.9520 versus 2.5796**; the old model chose the second move at probability 0.5070, and the continuation shifted to the first at probability 0.5340. It was a fragile boundary, and the current equal-example cross-entropy does not weight this error in proportion to its lost return. This is a measured explanation of the regression, not proof of the best replacement objective.

The warm-fit receipt's recorded “initial cross-entropy” is actually the seeded random baseline, not the supplied old weights. A read-only reconstruction gives the true old-weight value above. The source diagnostic has been repaired; the original receipt is preserved unchanged.

## Questions to decide

1. Choose the smallest defensible **single** ROM-free successor: (a) freeze the older attack head while fitting the corrected control and switch heads; (b) train attack choices with an advantage-sensitive loss that weights actual expected-return gaps; or (c) another bounded method. Explain why it can preserve the case 43 distinction without tuning to that case as an identity.
2. Specify a prospective gate that still uses the original-44, all-52 and complete-action return metrics, plus an honest check for overfitting to the 52 TRAIN cases. Does the prior 0.0554 / 0.0648 / 0.1609 vector remain appropriate?
3. Decide whether a four-scenario, terminal two-member-versus-one HP pilot is worth running after that gate, and what genuinely new-origin natural trainer evidence is needed before authority can move toward the final Red player.

Requested output: one prioritized design decision, its falsifier, and whether to retire the current training recipe. The model has **not** passed a natural promotion gate. The final product remains a model-directed Red run with the declared legitimate 124-species native route before any ROM hack. Red is 96/124 and fresh acceptance 0/5; no full run is authorized by this packet.
