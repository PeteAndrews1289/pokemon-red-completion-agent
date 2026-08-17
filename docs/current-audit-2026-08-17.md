# Current audit — 2026-08-17

## Executive result

The project has now performed its first genuine completion-aware Red model training. A fresh
switch-assisted pilot measured all **48/48 candidate trials**, producing **8 train and 4 untouched
development questions** with zero invalids. One separately published offline fitter updated the
model on train only and compared the frozen base and updated scorers once on development.

The result is directionally strong: development accuracy moved **1/4 → 4/4**, cross-entropy
**17.377 → 0.365**, and mean probability on the best measured outcome **0.250 → 0.711**. Three
discordant correctness pairs favored the update and none favored the base. Training loss moved
**8.703 → 0.141**. The development sample is only four questions, its exact two-sided paired
p-value is 0.25, and one winner-probability estimate regressed. This earns a larger development
experiment, not a benchmark claim or live authority.

Honest board: **train 8/32 · development 4/16 · fits 1/2 · unseen comparisons 1/2 · live authority
0 · transfer 0**.

## Scale-design update

The inventory blocker described below has since been resolved action-free. After all three
consumed repeatable pilots are excluded, the current implementation finds 24 train roots and 15
development roots. Its V2 design selects 24+12 questions from 36 unique roots/states and produces
93 candidate trials. Nine roots settle a captured control pulse with exactly one no-input frame;
the prelude rejects any party, collection, story, bag, money, map, position or battle change.

An initial V1 selection passed the old binary diversity checks while choosing 21 trainee and three
venue questions in train. That is too imbalanced to spend controller time on. The versioned V2
selector preserves V1 artifact reconstruction and instead solves the globally feasible margins:
train 14 trainee / 10 venue, development 6 / 6, and three development questions for every
completion goal. The rehearsal used zero controller, teacher, model, sealed Red, Crystal or replay
access, so the honest learning board above does not move. The next gate is publication, green CI,
one external clean-source plan and routine unsealed collection under standing approval. See the
[path-free scale design](evidence/repeatable-party-scale-design-v2-2026-08-17.json).

## What actually ran

The consumed pilot used published source
`8c45bd112d037cf3f0ec8bbcbba5b1ee72077a7a`, green GitHub CI run `32002135258` attempt 1, and
plan SHA `476d3e9e9df2b75e6d6e231d70f40f5571f69a2ae91590e064eb7b311f20652d`. It used 33,638
controller actions and 2,911,184 frames. Candidate widths were two and six; both partitions
contained trainee and venue choices, all four completion goals, both health and PP bands, positive
and negative survival margins, and level/no-evolution routes. It opened no teacher label, model,
sealed Red case, Crystal case, or full replay. That exact plan must not retry.

The fitter was published separately at
`eb3d5372a792140f79ce0c37f7b1c654837fdd77`; GitHub CI run `32031773663` attempt 1 passed. Before
reading outcomes it authenticated the pilot manifest and every stream, reconstructed the same 12
private menus and 48 assignments from bound cartridge inputs, verified the recorded prospective
audit, and required the untouched teacher-initialized base model. The fit identity, dataset
digests, split, source and defaults—200 epochs, learning rate 0.01, prior anchoring 0.1—were durably
recorded before the development comparison.

The immutable private output has manifest SHA
`961597323a8e0af507dd7edd835228a9b781370f1ad04ffd097483e5cd60fa5a`. The updated model file SHA
is `3a4a75491eab12cdfc0a77451cdaaac7c619620aa8b8c6669791f19f1aac6c7d`; its canonical model SHA
is `6b6982e8a514754a44c58e6b70f2ef0d1a94d2225f02893d128971527e752b8b`. A typed reload confirmed
eight verified-outcome training examples. The private model stays outside Git.

## Why the evidence is valid

1. **One intervention.** Every new label came from `switch-assisted-fixed-dose-v1`. Historical
   direct-combat outcomes were excluded rather than pooled.
2. **Train/development separation.** The model update consumed only eight train roots. The four
   development roots were used once for base-versus-update comparison and never for tuning.
3. **Identity-free learner rows.** Candidate features contain completion, party, evolution,
   resource and risk semantics—not species, slot, map, path or private filesystem identity.
4. **Exact assignment reconstruction.** Every retained outcome had to match the independently
   rebuilt scenario, binding, candidate feature digest, assignment and evidence digest.
5. **No teacher labels.** Targets came from prospectively ordered measured outcomes. Teacher query
   and teacher-choice-target counters stayed zero.
6. **No silent authority.** The model artifact says `verified_outcome_preference`, but the goal
   manager and executor have not granted it live control. Authority remains zero.

## What the result does and does not mean

The updated scorer correctly ranked all four small development menus, where its teacher-derived
base ranked only one. This is the first evidence that the v2 completion-aware features contain a
learnable signal beyond the old prior. It is also the first time the active lane's model-fit and
unseen-comparison counters can honestly advance.

Four questions cannot estimate broad reliability. The paired correctness test has only three
discordant pairs, so even a clean 3–0 result gives p=0.25. The 4/4 result can also hide a brittle
feature shortcut that a broader set of party states would expose. No claim about long-horizon
training efficiency, evolution completion, living-Pokedex planning, Red story completion, or
Crystal transfer follows from a one-battle local ranking dose.

## Remaining risks

- **Coverage is the bottleneck.** After every consumed pilot is excluded, the current pool contains
  two unused train and four unused development roots. Reaching 32/16 total requires at least
  twenty-two new train and eight new development roots.
- **The scale dataset must stay independent.** Timing permutations of the same state are useful
  robustness probes but do not replace independent root lineages for the main count.
- **One probability regressed.** Correct top-1 choices improved, but the update reduced winner
  probability on one of four menus. The larger comparison must retain per-menu paired diagnostics.
- **Venue-performance features are intentionally blank.** Direct-combat priors remain invalid for
  switch assistance. New yield, safety and recovery evidence must be measured under the new
  intervention before those features return.
- **The dose is local.** One completed battle tests a causal preference cheaply; it does not prove
  efficient multi-battle rotation, evolution scheduling, storage use or collection progress.
- **The scorer is offline.** A later benchmark must precede any shadow-to-live promotion, and a
  separate title-neutral protocol must precede Crystal execution.

## Exact next gate

1. Add at least twenty-two authenticated train roots and eight authenticated development roots to
   the non-sealed Red inventory; retain the two/four existing unused roots.
2. Generate an action-free plan for 24 additional train and 12 additional development questions.
3. Audit root/state disjointness, both choice kinds, completion-goal coverage, candidate widths,
   semantic diversity, capability feasibility, intervention identity, and private-data leakage.
4. Stop if the count can be met only by reusing consumed roots, weakening menus, overleveling,
   teacher labels, fixed-route knowledge, stale priors, or game-identity features.
5. Under standing routine-development approval, collect once the rehearsal passes. Retain every
   failure; do not rerun the consumed 8+4 plan.
6. Update on train only and compare once on untouched development. Do not tune after seeing the
   development result.
7. If the larger comparison preserves gain, freeze a benchmark promotion design and a separate
   Crystal development transfer protocol. Otherwise revise the representation before more data.

Sealed Red, Crystal execution, live party-development authority and full-game replay remain
prohibited. Standing approval removes routine development approval waits; it does not authorize
destructive operations, protected one-shot access, purchases or credentials, or material scope
expansion.

The path-free public result is the
[initial-fit receipt](evidence/repeatable-party-outcome-initial-fit-v1-2026-08-17.json). Local
qualification before the fit passed **3,965 non-integration tests**, with 3 integration tests
deselected and 1 expected xfail, plus Ruff, mypy across 236 source files, documentation, privacy and
product-focus checks.
