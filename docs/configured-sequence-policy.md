# Configured sequence-policy inference

The normal runner supports an explicit DEVELOPMENT sequence policy through
`execute_player_chunk` and `run_native_continuous_player`. Omitting the declaration
keeps the previous defaults. This integration does not admit training data or
change the production model defaults.

A plan declares the following fields, using real pinned files and identities:

```json
{
  "partition": "development",
  "sequence_policy": {
    "path": "absolute path to the frozen policy document",
    "content_sha256": "raw file SHA256",
    "policy_sha256": "canonical SequencePolicy identity",
    "target_contract": "observed-task-or-horizon-masked-sequence-v2",
    "task_sha256": "task identity from the pinned catalog",
    "task_catalog": {
      "path": "absolute path to the task catalog",
      "content_sha256": "raw catalog file SHA256"
    },
    "window_stride": 1,
    "reason": "Explicit frozen-policy copied qualification"
  },
  "goal_selection": {
    "mode": "exploration",
    "exploration_mix": 0.25,
    "story_milestone_commitment": true,
    "story_kind_commitment": false,
    "reason": "Frozen policy owns goal kinds; existing milestone support"
  },
  "force_resource_safety": true,
  "include_preparation_party_context": true,
  "retain_story_preparation_opposition": true
}
```

The existing configuration, source, model record, venue policy, finite allowance,
package, protected inputs and input recorder remain mandatory. The example above
is a declaration fragment, not a complete launch plan. SHA256 values are lowercase
64-digit hexadecimal strings, not the explanatory placeholders shown above.

The loader checks raw and canonical policy identities, its embedded head, baseline
model and feature version, target contract, catalog bytes and task identity,
exploration mix and stride. A v16 head requires preparation context. The runner
forwards the policy's horizon, contract and task identity to the existing collector.
Existing sequence/consequence, greedy and compulsory-settlement isolation remains.

The ordinary execution path supports this opt-in declaration. Inspect, loan-copy,
evolution-copy, boxed-machine-copy and prepared-evolution-copy diagnostic selectors
reject it before backend or emulator creation. They cannot silently choose the
baseline. Use copied ordinary executions and their native audits for qualification.

Segment plans retain the policy and observation declarations. Automatic renewal
uses the same live guest, cumulative costs and paired continuation export. A new
process cannot silently change the policy/task, resource-safety or preparation
observation declarations across a continuation. The policy and catalog assets must
remain available and unchanged; revalidation fails closed if they move or change.

Task identity is inference metadata, not permission to fabricate a successful task
terminal. This path does not mark task completion: full horizon windows are
observed, incomplete tails remain censored. The collector and its sequence history
restart per chunk. All such records remain ineligible for training without the
separate native and source-admission workflow.

`EXECUTION.json` retains the immediate goal-model identity and explicit wiring;
`native-plan.json` and selector decisions use the compound policy identity. The
sequence declaration records the task contract/hash. Qualification still requires
native source/input/cost/support and physical-state checks. Focused unit checks or
a wrapper's `passed` field alone do not establish a gate pass or campaign readiness.

See [the current handoff](../HANDOFF.md) and
[the integration session](history/2026-11-12-policy-runner.md).

## Explicit V3 selection modes

A pinned `SequencePolicy` can declare `stable` or `stable_recurrence`. Both retain
the exact frozen combined scores. `stable` uses the existing maximum-score tie
rule. `stable_recurrence` invokes the existing full-menu sampler only when every
tied maximum is a certified movement unit with `movement_revisit is True`.
Fresh, unknown or nonmovement maxima keep the greedy choice. The sampler can
choose the same action again; there is no forced escape or success fallback.

The V3 document and canonical identity declare the changed authority. V1/V2 sample
defaults remain unchanged. The legacy runner `goal_selection.mode` stays
`exploration` with its normal mix because sequence policy owns V3 selection;
`effective_sequence_selection_mode` in the execution wiring records the truth.
`stable_recurrence` additionally requires v16 movement history before input.
The native origin memory is sealed and its boundary/candidate witness replayed.

A score maximum can still change with context. Exact recurrence includes actual
resources, party and events, so paid searches and other resource changes may
prevent a recurrence witness even during unproductive strategic cycling. This
limitation is observed in the current copied diagnostics; neither a new policy ID
nor focused checks establish a native benefit or campaign readiness.

## Explicit V4 paid-failure recurrence

`stable_costly_recurrence` is an explicit new policy identity, retaining exact
scores/weights and every legal action. All tied maxima need either the old exact
movement witness or two certified settled paid zero-capture failures with equal
known cash-excluded physical progress, same private source/remaining target and
cash at/below its recorded low-water mark. Positive or unknown progress preserves
greedy selection. The unchanged sampler may still choose the failed search.

The private bounded monotone memory and optional non-feature context metadata are
replayed from sealed origins, actual bound options, native facts and closed prefixes.
Native snapshots read real Safari-session state; modern facts are projected into
the unchanged strict paid-setback certificate. Missing session is unknown. Old
sample/stable/exact-movement modes/defaults and empty serialized documents stay
unchanged. Effective selection mode is logged; legacy runner mode stays exploration.

Current F95 repairs explicit fresh-entry V16 context forwarding;20spy+225focused
checks and frozen import-only pass. Current full124 gates remainUNPROVEN.
F94/R2 all3story gatesPASS remain exact old-scope evidence,not F95 credit.
Full124 changes local_red target None/effective151 to124 as well as completion.
F87–F95 copies/repairs are separately authenticated;no gate credit transfers.
F90 repairs physical doors,F93 indoor departure quotes,F94 flat diagnostic retention.

F94 optionally declares the certified noncombat/unopposed partial-interaction success
head. One scalar fits four actual TRAIN units;all six outcomes remain retained.
Core175,movement head and other outputs retain parameters. Interaction parent
includes movement;movement still binds its original unheaded parent. Only the
typed partial-interaction domain receives the override. No priority/new planner.

e328 learned weights remain unchanged;its behavior-parent binding is explicitly
rebound. The composed policy has its own identity;old native credit cannot transfer.
Sequence-policy and33f consequence inference remain mutually exclusive. Separate
parent-first33f loses sequence/V4authority;no silent V4+33f composition.

Use exact source/model/policy/resource declarations and companion readbacks. Short
HOF copies/offline fits do not establish45native minutes,124registrations,all gates,
whole-Code parity or default promotion. See [current session](history/2026-11-13-overnight-readiness.md)
and the current handoff.
