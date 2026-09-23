# Frozen effect predictor and battle-selector combination

## Prospective mission check

1. Capability: turn measured effect knowledge into better learned battle choices,
   without treating effect application as battle value or an action veto.
2. Authority: one experimental selector update, retaining frozen K damage/control/
   switching and all182protected measured preferences. No story promotion.
3. Transfer test: first inspect/measure existing later-turn TRAIN states; then a
   fixed native TRAIN screen. Old128reserved comparisons remain unopened this packet.
4. Cheapest falsifier: frozen effect predictions fail later-turn observation, or
   the single combined fit/screen fails unchanged retention/behavior gates.
5. Time box:90minutes; at most12single-turn traced qualification episodes, one
   constrained output-layer fit (500iterations/60seconds), then64paired TRAIN
   battles at most40turns/80decisions/120000frames/45seconds per arm. Maximum140episodes.
6. Stop: inadequate measured later-turn support, invalid/corrupt execution, failed
   optimizer/fit/behavior gate, or budget exhaustion. No coefficient sweep, repeated
   candidate, heldout tuning, runtime status bans or campaign-save edits.

## Design frozen before implementation

Freeze effect artifactcad523f4 and prior rewardv2 selectora28b6774. Extend only the
selector's learned scoring representation with two values: supported-effect flag
and supported conditional-application probability. Scope remains Recover/Rest/
confusion. All other actions get zero auxiliary values, not removed legal actions.
Keep the old observation schema; serialize the entire auxiliary predictor and
learned readout with the model so reloading cannot silently drop the new component.
All auxiliary coefficients start at zero. Fit their values and the existing output
layer together from the authenticated312whole-battle rewardv2 contrasts; no new
action preferences come from effect labels. Retain182original-v1constraints exactly.

Before fitting, inventory actual later-turn feature support. Select the first two
capture-ID-sorted cases for each available family/condition cell across later groups,
not by outcomes. Current inventory has five cells: confusion clear/occupied,
Recover injured/full, Rest injured. Awake full-HP later Rest is absent; disclose it,
retain its first-turn qualification, and separately inspect two sleeping Rest
snapshots if present. Never invent a negative application label for suppression.
At most12new traced turns, no interventions or replay of old episode identities.
Require at least8observed labels across the10awake cases, every family represented,
and frozen conditional-predictor Brier<=0.125 before combination. Sleeping examples
are execution diagnostics only, not probability-of-execution labels or fit inputs.

The selector objective, rewardv2, retention margins and solver settings remain fixed:
SLSQP,500iterations,ftol1e-9,anchor penalty0.001. Fit admission retains the existing
old-group non-regression and at least25%later-group regret reduction againstfc4098a6.
Native acceptance remains wins>=K, zero raw concern selections, at least one improved
won status case and decisions<=1.25*K. No exemption for sleeping choices. Stop after
this screen and independent audit, regardless of pass; unused comparisons and natural
party qualification are subsequent work. All failures and no-effects remain retained.

## Result: qualification failed before fitting

The connection is implemented and tested. Its two auxiliary scoring values neither
choose moves nor change masks. Model checkpoint version2 preserves the frozen
predictor and trainable readout; old readers reject it rather than discard fields.
All312measured contexts reproduced prior scores exactly with zero new coefficients.
The original182retention constraints and authenticated rewardv2 corpus remain intact.

The12preselected diagnostic episodes completed: ten awake native effect observations
(eight applied/two no-effect) and two sleeping Rest suppressions. No label was inferred
from suppression.18492frames/84events, zero invalid actions. Independent read-only
audit reauthenticated every capture, event chain, episode/trace and measured row.

Frozen predictor accuracy was8/10at0.5, but Brier0.19013158 exceeded the predeclared
maximum0.125. The packet stopped: zero selector fits, zero native battle screens,
zero old reserved comparisons opened. No altered cutoff, second candidate or replay.

| Counterexample | HP at decision | HP at Recover entry | HP after Recover | Predicted application |
| --- | ---: | ---: | ---: | ---: |
| later-effect-06 | 111/111 | 45 | 100 | 2.69% |
| later-effect-07 | 111/111 | 43 | 98 | 2.72% |

Both selected healing at full HP, then took opposing damage before healing executed.
Each legitimately restored55HP. Status and confusion were absent; no teacher state
intervention occurred in these diagnostic turns. Visible speed margin was−0.21667;
the prior effect learner's entire fitting inventory had positive speed margins.
Its construction deliberately made the actor faster to simplify observation checks.
That convenient construction also removed the turn-order interaction it now needs.
This is a measured transfer limitation, not corrupt telemetry or a serialization bug.

The old6/6first-turn diagnostic remains valid within its narrow scope. It does not
justify general battle integration, and this new failure is retained alongside it.
There is also an evaluator concern: full HP at selection is not proof a healing
move is wasted. Conversely, restoring HP does not prove healing was the best action.
The raw-concern gate remains unchanged; any future revision needs explicit reasoning
and documented acceptance approval, not a quiet exemption to make this result pass.

## Next bounded objective

Freeze a new timing-aware effect curriculum crossing full/injured HP with both
actor-first and opponent-first conditions on fitting roots and unused configurations.
Use ordinary visible speed/threat information, not future damage or hidden timing
state. Require measured timing coverage before one revised auxiliary fit, preserve
cad523f4and these consumed qualification cases, and do not tune on these labels.
Recovery and Rest need both orderings; retain confusion coverage rather than assuming
the timing failure is limited to one move. Budget60–90minutes for this bounded
coverage/learning correction. No blind selector refit or broad campaign replay.

537targeted tests passed,13private integration tests skipped; three source modules
passed typing, changed code passed Ruff. Registry/docs checks passed. Protected
story/primary/Model141 and frozen effect hashes match. Collection delta zero;
primary109/124,story19/36,Giovanni incomplete,FreshRed0/5. All gameplay stopped.
No GitHub publication, external agents, reset or purchase. Recommend Astra High,
Fast off for turn-order semantics and the next training design.

[Path-free evidence](../evidence/red-effect-selector-combination-2026-09-22.json).
