# Red multi-goal calibration execution

## Purpose

Execute the nine prospectively frozen Red train interventions without letting a model, teacher,
operator or prior outcome change which option runs. This is a fast calibration loop for semantic
goal selection. It is not an independent evaluation, authority promotion or Crystal transfer gate.

## Frozen denominator

The private plan SHA-256 is
`1fc47b008d5159ea42d81286f1989be4ca3e70d9d99a1427507c87d4a02b3267`. It binds four physical
roots and nine single-decision arms:

| Semantic option | Trials |
| --- | ---: |
| Advance story | 4 |
| Develop team | 2 |
| Evolve species | 1 |
| Manage storage | 2 |

Every arm is restored from its root's identical captured state. Recovery and restoration remain
deterministic safety behavior and are not learned arms in this campaign.

The historical JSON field `selected_candidate_index` is an available-menu ordinal, not an index
into all nine question rows. The execution policy resolves that ordinal through the frozen
question's `available_indices`, verifies the resolved row has the frozen semantic kind, and only
then binds it. The trajectory and terminal record retain the resolved full-question index. The
independent reader reconstructs this mapping rather than trusting the executor.

## First production result and repair

Main `24d8671a` passed CI run `33818021962`. The production preflight returned `trial_ready` for
four roots and nine trials with zero actions, frames, predictions, teacher queries, and private
path fields. Trial 0 then failed before any decision or execution record because the first runner
incorrectly treated the available-menu ordinal as the full-question index. Its failed terminal is
at step zero. An action-free replay reproduced the exact mismatch without controller input.

Trial 0 is permanently invalid and must not retry. Its four root claims remain a valid reservation
for this exact campaign. A successor runner may authenticate those reservations by recomputing
their campaign-bound execution identity, but it may not overwrite them. Trials 1–8 remain
unclaimed and form the usable denominator after the index repair. The path-free evidence is in
[the trial-0 failure result](evidence/red-multi-goal-calibration-trial-00-failure-2026-09-03.json).

The index repair merged as main `06d602bb` under green CI `33821766312`. Trial-1 preflight passed
at zero effects, and its `develop_team` arm completed in 2,009 actions / 162,918 frames with semantic
change and no specimen loss. The resolved full-question index was 3. Independent admission then
found a reader-only contract mismatch: goal-manager choices are standalone decision records, so
the specialist controller rows correctly carry `decision_id: null`. They are not inside a
`RecordingExecutor` decision scope. All 2,009 row indices and their 162,918-frame sum match the
terminal report.

The gameplay episode is immutable and must not replay. The admission repair requires null links on
every controller row and rejects any non-null forged link. It also authenticates the claim's source
as published ancestry and checks the claimed runner digest against the exact historical Git blob,
so a repaired reader never rewrites execution provenance. After that source is published and green,
reopen and admit the existing episode; only then continue trial 2. See the
[trial-1 execution result](evidence/red-multi-goal-calibration-trial-01-execution-2026-09-03.json).

## Claim order

Before the first controller input, the runner must:

1. authenticate the clean published execution source, exact private plan, historical freezer,
   model, catalog, context plan, runtime, skill manifest, ROM, inventory result and private store;
2. reobserve the selected root without input and reproduce its frozen question, menu and binding
   manifest;
3. verify that all four physical roots are either unclaimed or carry one identical, recomputable
   reservation for this exact campaign (including a predecessor runner);
4. durably reserve all four roots for the campaign; and
5. durably claim the selected trial before beginning its private episode.

A crash while reserving roots may finish that reservation only for the same campaign and runner.
A crash after a trial claim permanently consumes that trial. No claimed trial may retry, even when
its episode is partial, interrupted, failed or invalid.

## Execution boundary

The policy receives the ordinary identity-free goal question but is not free to choose. It must
select the preregistered available-menu ordinal and matching semantic kind, resolve it to the
full-question candidate index, and bind only that row. The recorded assignment law is
one-hot with probability 1.0; the runner does not query the previous model or a teacher to choose an
arm. The deterministic binding then executes under the existing per-decision action and frame
bounds.

An independent observer and counter must agree with the binding report. A successful skill must
change semantic state and satisfy the living-collection transition contract. A verified bounded
failure remains an outcome. A programming exception produces a failed private artifact rather than
a training target.

## Durable evidence

Each complete episode contains:

- one decision written before controller input;
- one independently settled goal outcome;
- the exact frozen question, selected index and semantic kind;
- collection state before and after, including specimen counts and integrity hashes;
- independently reconciled actions and frames; and
- one terminal record with no teacher, private path or binding identifier in its public summary.

Strict independent admission is implemented as a separate reader. It requires the exact trial
claim and execution identity, reconstructs the one-hot forced assignment, checks the frozen
question and semantic arm, validates the Red living-collection ledger and transition, reconciles
the complete execution stream with the reported action/frame totals, and only then derives a
signed outcome target. The next gate is publication plus green exact-head CI for the index repair,
followed by one action-free trial-1 preflight and the eight untouched no-replacement executions. A train-only outcome fit
follows complete admitted trials. No calibration result may be described as held out or
transferable.
