# Win-conditioned status reward correction

## Prospective mission check

1. Capability: learn useful status/recovery choices without a reward for losing
   sooner merely to avoid subsequent turn, PP or unchanged-effect costs.
2. Authority: a new TRAIN reward view only; learned output weights may change in
   one admitted fit. No runtime rules, masks, teacher fallback or live promotion.
3. Transfer: original 64 TRAIN battle pairs, then the 128 unopened generated
   cases only if the unchanged behavior gate passes. Independent natural-party
   qualification remains separate; generated cases share TRAIN ancestry.
4. Cheapest falsifier: equal-terminal-resource losses still score differently
   solely due to duration/cost, or a win can score below a loss within the budget.
5. Time box: 60 minutes for implementation/audit and one fit; at most 45 minutes
   and 384 episodes for its conditional evaluation. No new target collection.
6. Stop: invalid source binding, changed original retention, failed fit/behavior
   gate or budget exhaustion. No coefficient sweep or repeated fit in this packet.

## Versioned correction, frozen before inspecting rescored target preferences

Keep closed-loop-return.v1 and every previous candidate/result immutable. Add v2:
terminal +10 for a win, -10 otherwise; retain 0.5 final own-HP fraction plus 0.5
opponent damage fraction. Apply efficiency costs only on a win, normalized by the
declared 40-decision horizon: 0.1 turns/40, 0.01 min(PP/40,1), and 0.5 observed
unchanged-status turns/40. The efficiency deduction is bounded by 0.61. Within
the declared domain, any win beats any nonwin. Failed outcomes receive no duration,
PP or downstream unchanged-effect deduction: equal resource outcomes tie, and
greater damage improves the loss score rather than being outweighed by living longer.

This does not reward survival time, invent unobserved effects, identify every
flagged selection as ineffective or prove a three-timing mean causally reliable.
The existing observation-only unchanged-effect diagnostic stays unchanged; healing,
Disable and suppressed moves receive no invented immediate-effect labels. All
original raw cost/behavior diagnostics still apply, including asleep selections.

Recompute a separate view of all 312 eligible TRAIN targets from their 1,872 retained
branches. Validate old reward reproduction, branch identity, event/terminal hashes
and first-action observations. Retain continuation-group tags and original targets.
No new emulator collection, outcome filtering or heldout access.

Use frozen0734686a hidden features and output anchor, originalfc4098a6 comparison,
and the original 182 v1 negative constraints/margins. Fit one convex readout using
v2 labels, max500 iterations/60 seconds, ftol1e-9, anchor penalty0.001. Apply the
same numerical and 25%/old-group fit tests to the declared v2 scale; also report
v1 metrics without rewriting prior admission. Behavioral evaluation retains v1
returns and exactly the old gate, allowing direct comparison with previous screens.
No new candidate is accepted solely because its reward scale changed.

No collection/save/Model141/K change or GitHub publication is authorized here.

## Verified result

All 1,872 retained branches authenticated, including original v1 reward reproduction,
first-action observations and event/terminal bindings. No source outcome changed.
The v2 view changed 29 of 312 mean preferences. All seven previously identified
flagged all-loss preferences now favor damage. In total, flagged-status preferences
changed from 12 to 11: six other preferences appeared under the new measured scale.
This removes the diagnosed earlier-loss incentive, not every noisy/inappropriate
sampled preference. No coefficient was tuned after observing these results.

Candidate a28b6774 converged in 74 iterations / 0.052 seconds; stationarity residual
8.66e-7, zero regressions among the original 182 protected preferences. Fixed hidden
parameters and K damage/control/switching are exact. Fit admission passed on the
declared v2 scale, with 84.869% lower combined later-group regret than fc4098a6.
Original-v1 group metrics are retained separately; this percentage is not a
cross-reward comparison with prior candidates or a generalization claim.

| TRAIN screen | K | Previous candidate9bec7380 | Corrected candidatea28b6774 |
| --- | ---: | ---: | ---: |
| Wins | 32/64 | 37/64 | 38/64 |
| Decisions | 154 | 197 | 196 |
| Raw status concerns | Status disabled | 13 | 8 |
| Improved won status cases versus K | Baseline | 6 | 7 |

The unchanged behavior gate still failed: eight concerns and decision ratio1.273
exceeds1.25 (at most192integer decisions). Candidate remains rejected for integration.
The128reserved generated comparisons remain unopened; no second fit or live promotion.

Independent audit verified128native episodes,350learned decisions,196candidate
predictions,1,784events and483,810frames.70wins/58losses; no invalid action or turn cap.
The eight remaining flags cover five cases: four occupied major-status selections,
two already-confused and two full-HP healing selections. Two were asleep and did
not execute; they remain in the unchanged gate. Three exact TRAIN input matches
remain: the corrected paralysis/confusion examples now have small regret0.03598/
0.02410, while another confusion example still favors status under measured returns.
Raw flags are not relabeled as proven causal failures; effect ordering can matter.

## Next bounded work

The reward defect is corrected and tested. Do not repeat its coefficient choice,
increase solver iterations or collect a broad new bank as the default response.
The remaining issue is reliable effect/applicability learning from sparse, noisy
whole-battle outcomes. Assess a separate measured immediate-effect teaching signal,
starting with the existing branch transitions. Distinguish executed no-change,
suppression and unknown effects; healing, Disable and confusion expiry may need
more precise observation rather than invented labels. Check signal coverage before
designing one new learner experiment. Keep all old rejections, retention checks,
the behavioral gate and the unopened comparison set unchanged.
Budget45-60minutes for that bounded observability/learning-design test; no promise
of completing integration in that time. No runtime move bans or teacher substitution.

## Closeout

[Combined independent audit](../evidence/red-status-reward-correction-2026-09-21.json).
474 targeted battle/documentation tests passed;13integration tests skipped.
Changed-module typing, Ruff, registry and documentation checks passed; native audit
ran separately. No full-suite or whole-package typing claim.
Protected story35feb8fa, primarybf603930 and Model141record4ab0e75f unchanged.
Primary109/124, story19/36, Giovanni incomplete; collection/promotion deltas zero.
Gameplay stopped; no GitHub publication, external-agent or usage actions.
Recommended next session: Astra High, Fast off, for effect/measurement semantics;
[official model guidance](https://developers.openai.com/api/docs/models/gpt-6-astra).
