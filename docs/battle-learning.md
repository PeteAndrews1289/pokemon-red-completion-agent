# Battle learning

## Purpose and claim boundary

The first learned specialist ranks the moves that are actually available in a battle. It is a
development step toward the learned/hybrid completion agent, not a replacement claim for the
qualified teacher.

The first labeled episode contains one root lineage whose partition was recorded as
`unassigned`. Dividing its decisions after collection cannot turn any part of it into an official
held-out test. The episode may be used to validate the reader, feature projection, optimizer, model
format, and whole-battle diagnostic grouping. Promotion requires newly recorded lineages assigned
to train, validation, and test before collection.

## Private input and output

Training opens an episode only through the validated private-artifact root. Before any row is
available, the reader:

- revalidates the separate mount and sentinel;
- rejects partial, failed, linked, extra, or unsafe-mode files;
- validates the exact canonical manifest and directory inventory;
- recomputes byte counts, record counts, and SHA-256 hashes for every stream; and
- retains one immutable in-memory view so later filesystem changes cannot alter the run.

The model, configuration, and aggregate metrics are written back to the private root as a distinct
typed artifact. The artifact uses canonical JSON rather than pickle or another executable format,
is written with private permissions, and is published by an exclusive atomic rename only after its
manifest and streams are synchronized. Model directories and common model formats remain blocked
from Git.

## Transferable feature view

The Red catalog is pinned to pret/pokered commit
`1e96034092686d006e863cace09e87273051a3d8`. It maps all 165 Red moves and all 151 canonical
species from revision-local references into shared mechanics:

- elemental types and Generation I physical/special categories;
- power, accuracy, PP, and battle priority;
- exact Generation I type effectiveness, including its historical behavior; and
- broad move effects such as status, stat changes, recoil, charge, healing, draining, trapping,
  fixed damage, and multi-hit behavior.

Each available move becomes one candidate under the fixed
`pokemon.core.battle.move-ranker.v1` schema. Candidate-relative values include STAB,
effectiveness, effective power, PP, and bounded interactions between move mechanics and the
observed battle state. Local species IDs, local move IDs, menu slots, area, coordinates, badges,
trajectory IDs, teacher identity, objectives, future outcomes, and referee-only evidence are not
model features. The chosen candidate is mapped back to its current menu slot only after inference.

## Model and diagnostic split

The baseline is a small shared linear ranker trained with listwise softmax cross-entropy. Every
candidate uses the same weights, so the model supports variable move sets and does not learn a
separate policy for “slot one” through “slot four.” Illegal and zero-PP candidates are masked before
normalization. Weights are finite, deterministic for a declared seed, and serialized as canonical
JSON.

The current diagnostic groups all turns at the same battle encounter proxy and keeps every group
inside one fold. It never performs a random decision-row split. Reported metrics include:

- exact teacher-choice agreement;
- macro F1 and per-slot recall;
- listwise cross-entropy;
- legal-choice rate;
- a fold-local majority-slot baseline; and
- in-sample training agreement as an overfitting diagnostic.

This grouped result is still interpolation evidence from one recorded playthrough. It is not a
held-out seed result, a learned battle rollout, or evidence of full-game completion.

## Promotion protocol

A promotable battle specialist requires:

1. root lineages assigned to train, validation, or test before recording;
2. all descendants of a root lineage inheriting its partition;
3. explicit battle-instance grouping and any legitimate planner goal or resource constraint that
   will also exist during inference;
4. no root-lineage or exact-snapshot overlap across partitions;
5. a frozen model and confidence threshold selected without opening the test partition;
6. zero illegal or zero-PP selections;
7. materially better held-out agreement and cross-entropy than declared baselines; and
8. battle rollouts with teacher fallback disabled, reported separately from imitation agreement.

The final test remains sealed until the feature schema, optimizer, and promotion thresholds are
frozen. Cross-game transfer will hold an entire second title out and compare reuse of the Red model
against the same architecture trained from scratch.
