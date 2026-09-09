# Prospective story-outcome learning

## Verified first lesson — September9

Agatha's prospective V5 lesson succeeded and produced one authenticated guided
outcome. Model78 to79 retained all earlier rows; the saved model and dataset were
reopened independently. This validates the outcome-learning path, not comparative
choice quality. No historical support was relabeled. The next distinct Lance
entrance remains unqualified. See [the live-result audit](audits/red-agatha-curriculum-2026-09-09.md).

The goal remains a player that learns to complete stories and living collections,
not a fixed Red walkthrough. A forced action can teach its observed consequences
without proving that a model selected the best action.

## Contract

V5 training plans opt into `forced-singleton-story-outcome-unit-weight-v1` before
execution. They retain the completion-dose continuation, train lineage, model,
source and profile bindings. Historical V2/V3/V4 declarations and their hashes
remain unchanged. Old support runs are not backfilled.

There are two separate streams:

- Actual exploratory choices retain the existing menus, full-support logged
  probabilities, selected-arm targets and capped inverse-propensity weights.
- A forced singleton `advance_story` records the executed semantic feature
  vector and observed outcome, with no invented alternatives or probabilities.
  It contributes one unit of regression weight, not comparative policy evidence.

Only the shared outcome-regression solver combines them. Its mixed objective is
explicit in the model record; corpus inventories and reports retain separate
counts. Existing row fingerprints cannot be dropped or rewritten. A duplicate
decision cannot appear in both streams. The selection policy and utility weights
are not changed by this contract.

Admission reconstructs the semantic features, checks the exact execution interval
and frame count, and recomputes targets from observed before/after facts. Story
progress still belongs to the dependency-unlock head, not living-species gain.
Failures retain their actual costs. Interrupted or unreadable outcomes are
censored with no invented after-state or fit target; zero-input rows are excluded.
These are correlated known-training episodes, not held-out evaluation.

## Immediate engineering scope

Agatha is an opt-in extension of the existing cartridge-driven trainer skill.
The one-shot entrance walk is decoded from the map's script pointers, coordinate
table, event bit and movement buffer. Only exact declared warp arrivals change;
ordinary route drift still fails. Unsupported script shapes or already-consumed
entrance events refuse the cross-map plan. This is a narrow Gen I adapter, not
a general machine-code interpreter or a claim of ROM-hack compatibility.
The public arrival adapter also requires the existing exact supported Red ROM
fingerprint: local script grammar cannot establish arbitrary called routines'
semantics. A reviewer demonstrated this by redirecting a simulation call to a
return-only routine. Revision binding closes that gap; future hacks require an
explicit engine qualification rather than weakening the check.

The reference disassembly shows the entrance coordinate/event branch and movement
buffer in [Agatha's room script](https://github.com/pret/pokered/blob/master/scripts/AgathasRoom.asm).
Runtime coordinates and step count come from the user's cartridge, not this page.

## Mission check and next falsifier

1. Capability: learn the actual success, progress and costs of story options.
2. Authority: outcome coverage increases; no new comparative-choice or battle
   authority is conferred by a forced curriculum step.
3. Transfer: vary script pointers/counts/direction, semantic states and outcome
   statuses in ROM-free tests. Real cross-title transfer remains untested.
4. Falsifier: one prospective Agatha attempt from the retained Bruno endpoint,
   admitting only its real observed outcome; then inspect an actual later choice.
5. Timebox: the current one-hour work block, with bounded attempts and reviews.
6. Stop: preserve any failure and actual endpoint; no consumed doorway replay,
   invented alternative, historical relabeling or full-game run.

Mixed curriculum vectors currently require the model's exact feature version.
An upgrade needs explicit vector migration; existing bootstrap guards refuse
discarding curriculum rows. Current model78 already uses version3.

## Review decisions

Flash High provided a design advisory, not a source audit. Accepted: coefficient
shift risk, stream separation, real outcome/censoring checks. Rejected: changing
historical choice weights, calling unit weight measured confidence, arbitrary
70% gradient thresholds, and ranking/regret assertions without unchosen outcomes.
No leave-one-out score on this correlated corpus is called independent validation.

A read-only code reviewer found permissive extra metadata and unreadable-outcome
handling. Both were repaired with strict payload/type-sensitive identity checks
and explicit curriculum-only censoring. Codex owns implementation and verification.
