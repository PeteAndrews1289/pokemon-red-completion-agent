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

## Preregistered collection

The prospective
[battle collection registry](collection-protocol.md) freezes twelve root-lineage slots before
recording: five train, two validation, and five sealed test slots. Each partition has its own
one-based slot sequence (`1/5`–`5/5`, `1/2`–`2/2`, and `1/5`–`5/5`) as well as a global
`1/12`–`12/12` sequence. Every assignment derives a deterministic private episode and root
lineage from the authenticated registry, execution identity, partition, harness seed, and complete
schedule digest.

Each full run expects the same 68 stable public adaptive-battle identities in route order. A
versioned SHA-256 derivation gives every identity a preregistered 0–255-frame timing offset. At the
first stable main battle menu, before the policy is called, the collection harness claims that
offset; the battle runtime emits the WAIT through the normal executor, rereads and revalidates the
semantic state, and then supplies the refreshed observation to the policy. Retries within the same
physical battle never reapply it. Missing, extra, substituted, reordered, partially applied, or
unfinished battles fail the planned run.

Every applied offset is privately attested with its roster ordinal, plan ID, frame count, schedule
digest, before/after policy-snapshot hashes, and the linked `WAIT` execution index when the offset
is positive. The terminal event must attest a complete 68/68 schedule. These records prove that a
scheduled run used its committed offsets rather than merely carrying the expected metadata.

The harness seed is not presented as a user-selectable cartridge seed. It is a reproducible
collection timing input that changes hidden battle RNG timing. Run, seed, partition, schedule, and
battle-plan identities remain metadata and are not move-ranker features.

The exact source/configuration commit must be committed and pushed before any execution. A
registry-declared, disjoint `--schedule-dry-run` must then successfully attest all 68 battles
before slot `01`. That rehearsal is `unassigned`, has `attempt.counted=false`, and is excluded from
every partition and performance denominator. The first Forest-lineage rehearsal exposed a
moving-NPC collision at the Route 24 entrance at checkpoint 38/312. The repaired corridor passed
clean-power qualification and cleared that checkpoint under the same schedule, but the second
rehearsal stopped at checkpoint 109/312 when a final Rock Tunnel trapping sequence fainted the
lead above the old 40-HP recovery gate. Neither attempt qualified or consumed a campaign slot; all
twelve declared slots remain pending. Clean diagnostics have since hardened the tunnel, Tower,
Sabrina recovery, and the Mansion's one-turn grinding policy. The combined source passed a new
312/312 clean-power Hall-of-Fame replay and was then committed and pushed before the rehearsal.

That published rehearsal subsequently cleared the former Route 24 and Route 25 failures but
stopped at checkpoint 109/312 when Bellsprout trapped Wartortle with Wrap. A later uncounted
candidate exposed an unsafe low-HP DUX finisher; neither attempt consumed a counted slot. The
current route removes that finisher, budgets the tunnel's potion reserve, uses type-aware Bite
against Slowpoke after required evidence, and escapes a status-locked DUX to the healthy lead. It
accepts natural evolution, uses the surplus Rare Candy for the level-41 TM40 lesson, gives moving
Celadon NPCs neutral retry windows, and applies Ice Beam plus bounded whole-battle recovery to the
Silph rival. The next uncounted rehearsal proved the DUX escape but put replacement Blastoise to
sleep and exposed that battle recovery targeted only party slot one. The current teacher carries a
second Awakening from Vermilion, preserves one for Tower, and applies both status and HP recovery to
the actual active party index under a two-potion cap. That exact source completed **312/312
checkpoints**, **36/36 objectives**, and the Hall of Fame in **771,022 actions**; its six-member
curriculum exceeded **4,000 battles**, retained the minimum level of 77, and passed the bounded
spread contract. The next uncounted rehearsal cleared Rock Tunnel but found that its extra recovery
left the Lavender restock $200 short. The teacher now sells the unused, already-proven TM28 for
$1,000 before restoring the complete downstream safety reserve; no counted slot was consumed.
That correction advanced the rehearsal to Koga Gym, where Juggler 4 fainted the low-HP lead. The
teacher now pivots to the healthiest living reserve at the observed 50-HP safety floor and ranks
that active reserve's own legal moves; this teaches party-role handoff without spending another
item.
The resulting rehearsal reached Sabrina at checkpoint 261/312. A Hyper Potion was used, but the
shared verifier allowed only 24 single-frame acknowledgements for the opponent's reply and never
observed MAIN. The item primitive now waits up to 720 cancel-safe frames; CANCEL advances text while
remaining inert on MAIN, preventing a second accidental ITEM confirmation.
The repaired rehearsal passed Sabrina and advanced beyond 1,250 balanced-team battles before one
fighter had no live preferred attack. The runtime now treats PP exhaustion or Disable as a semantic
loss-of-control signal: it switches to the safe escort when required, flees with zero faints, and
returns the decision to the portable team planner so a healing trip can be scheduled.
The repaired teacher then completed the scheduled **312/312-checkpoint** run and entered the Hall
of Fame. Promotion still failed closed: the wild curriculum lacked explicit `BattleIntent` labels,
and repeated training progress reused one event identity. The retained artifact contains roughly
848,000 successfully written records, so the correction targets semantics rather than storage:
portable training objectives on every wild decision, explicit lifecycle closure after an external
flee, step-qualified progress IDs, and a bounded episode size covering the 7,000-battle envelope.
The run remained uncounted.

Success publishes an immutable private qualification bound to the exact source, runtime, ROM,
schedule, episode, manifest, and 68/68 offline audit. Every counted slot reopens and re-audits that
episode before campaign sealing, while the rehearsal remains outside the attempt ledger.

A private campaign seal fixes the registry, exact pushed source commit, executable source,
behavior, objective graph, teacher execution, CPython/PyBoy runtime, ROM, and twelve-slot roster
identities before the first counted attempt. Its immutable outcome
ledger gives each assignment one attempt and records `complete`, `failed`, `interrupted`, or
`invalid` with a reason. A failure or power interruption consumes the slot; it cannot be silently
rerun after the outcome is known. Reconciliation may recover an already valid complete manifest
after a process interruption, but an orphan partial is an `interrupted` outcome. Restarting a
campaign requires a new registry version. The deterministic partial episode directory is
synchronously persisted before the emulator starts, making that one-attempt claim durable across
power loss.

After publication, the recorder rereads the private episode and proves each positive timing offset
against its exact WAIT execution, frame count, and before/after state hashes. Zero offsets must
have no execution link. The path-free `collection status` command performs the same reconciliation
without starting a new attempt.

An individual episode may be structurally qualified for its assigned data lane, but it is never
labeled promotion-eligible by itself. Promotion is a corpus-and-rollout decision after the frozen
cross-lineage protocol, not an episode property. The formal fitting lane now authenticates the
campaign seal, rehearsal qualification, exact assignment, schedule evidence, one-shot outcome,
manifest, split, and root identity for all five train and two validation episodes. It refuses to
open any test episode, fits only the train roots, and reports validation accuracy, cross-entropy,
legal-choice rate, free/forced-choice metrics, visible-state overlap, novel-visible performance,
and a validation-only confidence threshold. Its candidate remains promotion-ineligible until the
weights and threshold are frozen, the five test roots are evaluated once, and learned rollouts
pass separately. The lane is implemented but has not executed because collection is still pending.

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

After the five train and two validation outcomes are complete, the authenticated command is:

```bash
pokemon-red-completion learn battle fit --private-root /absolute/private/trajectory-directory
```

It has no test-episode argument. Test data cannot enter model fitting or threshold selection.

## Transferable feature view

The Red catalog is pinned to pret/pokered commit
`1e96034092686d006e863cace09e87273051a3d8`. It maps all 165 Red moves and all 151 canonical
species from revision-local references into shared mechanics:

- elemental types and Generation I physical/special categories;
- power, accuracy, PP, and battle priority;
- exact Generation I type effectiveness, including its historical behavior; and
- broad move effects such as status, stat changes, recoil, charge, healing, draining, trapping,
  fixed damage, and multi-hit behavior.

Counter is cataloged explicitly, but a selectable Counter candidate fails closed until the
semantic observation exposes prior-turn received damage. A zero-PP Counter remains present only as
a masked, unusable candidate.

Each available move becomes one candidate under the current
`pokemon.core.battle.move-ranker.v2` schema. Candidate-relative values include STAB,
effectiveness, effective power, PP, bounded interactions between move mechanics and the observed
battle state, and `constraint.matches_required_move`. The policy context contains goal `win`, a
move policy of `any_usable` or `exact_required`, and either no required move or its semantic
reference. The same context available at inference is retained with each example and supplied to
the projector.

An `exact_required` decision is a forced choice; an `any_usable` decision is a free choice. The
constraint feature lets the model represent the distinction rather than learning it from hidden
route identity. Local species IDs, local move IDs, menu slots, area, coordinates, badges,
trajectory IDs, teacher identity, objective IDs, future outcomes, and referee-only evidence are
not model features. The chosen candidate is mapped back to its current menu slot only after
inference.

The loader retains schema-v1 support for historical diagnostic artifacts. New recordings and
models use v2. The published 72.5% receipt is a historical v1 single-lineage diagnostic and must
not be retroactively presented as v2 context-stratified evidence.

The recorded `teacher_recovery_marker` values, `none` and `bounded_recovery`, are descriptive
metadata only. The marker is validated when context is loaded but is not projected as a model
feature. It does not encode a typed recovery budget or action envelope and cannot qualify a
recovery-policy learner.

## Model and diagnostic split

The baseline is a small shared linear ranker trained with listwise softmax cross-entropy. Every
candidate uses the same weights, so the model supports variable move sets and does not learn a
separate policy for “slot one” through “slot four.” Illegal and zero-PP candidates are masked before
normalization. Weights are finite, deterministic for a declared seed, and serialized as canonical
JSON.

The current diagnostic groups all turns at the same battle encounter proxy and keeps every group
inside one fold. It never performs a random decision-row split. Reported metrics include:

- exact teacher-choice agreement;
- free-choice and forced-choice decision counts and accuracies;
- the count of decisions whose policy context was not observed;
- macro F1 and per-slot recall;
- listwise cross-entropy;
- legal-choice rate;
- a fold-local majority-slot baseline; and
- in-sample training agreement as an overfitting diagnostic.

This grouped result is still interpolation evidence from one recorded playthrough. It is not a
held-out seed result, a learned battle rollout, or evidence of full-game completion.
The [first aggregate diagnostic](evidence/private-battle-imitation-diagnostic-2026-07-30.json)
reports 72.5% teacher-choice agreement across 422 decisions under the historical v1 schema while
retaining those limits. In future v2 reports, forced-choice accuracy measures compliance with a
declared move constraint and cannot inflate or replace the autonomous free-choice result.

## Promotion protocol

A promotable battle specialist requires:

1. root lineages assigned to train, validation, or test before recording;
2. all descendants of a root lineage inheriting its partition;
3. explicit battle-instance grouping and any legitimate planner goal or resource constraint that
   will also exist during inference;
4. no episode, manifest, assignment, schedule, or root-lineage reuse across partitions;
5. a frozen model and confidence threshold selected without opening the test partition;
6. separately reported free-choice, forced-choice, and novel-visible-state metrics;
7. zero illegal or zero-PP selections;
8. materially better held-out agreement and cross-entropy than declared baselines; and
9. battle rollouts with teacher fallback disabled, reported separately from imitation agreement.

Cross-partition overlap in policy-visible semantic snapshot hashes is reported, not treated as
hard leakage by itself: distinct hidden timing/RNG histories can produce the same visible state.
The audit still fails copied episode identities, manifests, assignments, schedules, or root
lineages. Reports disclose visible-overlap counts and performance on novel visible states so the
reader can judge how much evaluation state was genuinely new without permitting outcome-dependent
replacement of a slot.

The final test remains sealed until the feature schema, optimizer, and promotion thresholds are
frozen. Cross-game transfer will hold an entire second title out and compare reuse of the Red model
against the same architecture trained from scratch.
