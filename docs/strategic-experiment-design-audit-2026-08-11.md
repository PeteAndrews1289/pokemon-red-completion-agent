# Strategic experiment-design audit — 2026-08-11

## Verdict

The repaired full-game rehearsal remains valid engineering qualification, but the newly regenerated
counted campaign must not open yet. Its current three-decision design cannot support the intended
claim that a learned strategic scorer generalizes and beats the route-cost-only baseline.

This is not a defect in the destination-label contract. The model-facing rows remain identity-free,
successful deterministic-teacher choices are the only imitation targets, failed routes remain
outcome evidence, and external interruption remains censored. The problem is experimental power
and context diversity.

## What the completed roots actually contain

A read-only audit of the three authenticated historical train episodes found nine successful rows
but only:

- **3 candidate-order-invariant policy contexts**;
- **4 ordered policy inputs**, because assignment permutation changed only one context's order; and
- **3 distinct selected-candidate feature rows**.

The exact source-bound fingerprints and multiplicities are preserved in the
[public duplication receipt](evidence/strategic-context-duplication-audit-2026-08-11.json).

Each root repeats Tower versus Eevee, Koga versus Warden, and Dojo versus Sabrina. Battle-timing
variation changes the route execution lineage, but it does not create a new strategic question.
Decision IDs are unique because they include episode and lineage identity; that prevents record
collision but does not make the policy inputs statistically independent.

The old 5-train/2-validation protocol would therefore produce nominal counts of 15 and 6 while
retaining only the same three unordered contexts in both partitions. Such validation measures
reproducibility and candidate-permutation handling, not generalization to an unseen choice.

## Why six validation rows cannot carry the claim

The observed cost-only baseline is 2/3. If six rows were treated as independent Bernoulli trials
against a fixed null probability of 2/3, even a perfect 6/6 scorer has one-sided exact tail
probability

```text
(2/3)^6 = 0.0878
```

Pairing scorer and baseline predictions is the correct direction, but it does not rescue this
benchmark. Repeating the three contexts twice gives a perfect scorer only two row-level wins over
the baseline and no losses; exact two-sided McNemar probability is 0.5. Collapsing repeated rows to
their proper unique-context unit leaves one baseline-discordant context, which cannot establish an
improvement at any conventional threshold.

Adding candidates is useful only when every option is genuine. It enriches ranking loss and can
create more meaningful teacher-versus-cost comparisons, but it does not turn correlated candidates
or repeated roots into independent validation contexts.

## Revised admission contract

Before another counted full-game root opens, the project must implement and preregister all of the
following:

1. **Permutation-invariant context fingerprints.** Remove private identity and `binding_index`,
   canonicalize candidate order, and report unique and replicated policy contexts. Any exact
   train/validation context overlap must fail model-development admission.
2. **A context registry.** Preassign strategic situations—not repeated copies of one full-game
   route—to train, validation and sealed test before fitting a model. Context families that differ
   only by candidate order stay in one partition.
3. **Genuine candidate density.** Prefer three to five feasible destinations at real objective
   boundaries. No unreachable filler may be added merely to lower chance accuracy.
4. **Enough distinct situations.** Initial target: at least 24 train, 12 validation and 12 sealed
   test contexts, with at least six preregistered validation contexts where the deterministic
   teacher and cost-only baseline disagree. Repeated timing roots are robustness replicates and do
   not increase this count.
5. **Paired primary evaluation.** Compare scorer and registered baseline on the same unique held-out
   contexts with an exact paired test and confidence interval. Report all-context accuracy and a
   separately declared baseline-challenge stratum; do not select either after model results exist.
6. **Efficient scenario execution.** Collect short, source-bound strategic scenario episodes from
   authenticated boundaries instead of spending roughly 47 million frames to reproduce three
   identical labels. Full clean-power runs remain end-to-end causal qualification, not the main way
   to manufacture ranking rows.

The numerical targets are minimum design thresholds, not a promise of significance. A model can
still fail. They ensure only that the benchmark is capable of distinguishing a useful scorer from
the baseline if the effect exists.

## Ordered implementation

1. Add the context fingerprint and overlap/power fields to the strategic audit, with mutation-tested
   fail-closed admission.
2. Inventory genuine decision boundaries already present in the completion teacher and identify
   three-to-five-candidate sets without changing the selected completion route.
3. Define the context/scenario registry and short authenticated execution lane; retain whole-lineage
   provenance and sealed test access.
4. Run an uncounted scenario-suite rehearsal and audit diversity, cost-baseline discordance,
   candidate balance, joins and failure handling.
5. Freeze the new registry, collect train and validation once, then fit the first scorer.
6. Use full-game shadow and bounded causal control only after the held-out context benchmark passes.

The already qualified 703,275-record rehearsal is preserved. It proved the teacher, recorder,
planner and full-game route can complete together. It is not relabeled as evidence that the current
six-row validation design is adequate.
