# Learned-feature status readout and conditional integration

## Prospective mission check

1. Capability: learn useful status/recovery decisions using existing TRAIN-learned
   features and the verified convex output solver.
2. Authority: only output weights are fitted; K damage/control/switching remain
   exact. No teacher fallback or runtime action bans. Integration requires passing
   behavioral and independent natural-workload qualification, not merely a fit.
3. Transfer: original 64 paired TRAIN battles, then the 128 unopened generated
   configurations. These share TRAIN ancestry and cannot replace independent
   natural-party testing. Define the latter separately if generated gates pass.
4. Cheapest falsifier: the richer feature space cannot retain the original 182
   negative preferences, or its single readout fit fails unchanged admission.
5. Time box: 30–45 minutes for implementation and initial fit; at most 45 minutes
   and 384 episodes for the conditional generated evaluation. No full-game run.
6. Stop: infeasibility, unsuccessful solve, failed learning/behavior gate, invalid
   execution or budget exhaustion. No hidden-basis sweep or second fit in this packet.

## Frozen design

Reuse existing TRAIN-learned candidate 0734686a as the fixed hidden basis and output
anchor. Retain fc4098a6 as the comparison and retention reference: original protected
indices and minimum margins remain unchanged, evaluated in the richer feature space.
Keep 312 existing eligible TRAIN contexts (92/94/126), tagged by their original
continuation policies. No new targets, nonlinear fitting or evaluation-selected basis.
The earlier 0734686a experiment remains rejected for nonconvergence; this is a new,
prospectively specified experiment, not retroactive acceptance.

One SLSQP output fit, maximum 500 iterations/60 seconds, ftol 1e-9, anchor penalty
0.001. Preserve the old learning gate: zero retention regressions, oldest-group
regret no worse than fc4098a6, and combined later-group mean regret at least 25%
lower than fc4098a6. Inspection is action-free and discards feasibility witnesses.

If admitted, compare K and candidate on 64 TRAIN battles: wins at least K, zero
raw applicability concerns, at least one improved won status case, and decisions
no more than 1.25 times K. Only then open the 128 reserved generated configurations,
reporting that same gate and all four cohorts. Do not fit to their outcomes.

Main story, collection saves, Model141 and K remain unchanged. No GitHub publication.

## Verified result — useful TRAIN improvement, integration rejected

Candidate 9bec7380 converged in 65 iterations / 0.026 seconds. All 182 original
preferences remain protected; hidden features, K damage, control and switching
are unchanged. Later-group mean regret fell 82.706%; oldest-group regret fell from
0.668524 to 0.000127. High-cost errors fell 27 to 3, ordinary errors 38 to 9.
Independent objective/gradient and model-binding checks passed.

The admitted candidate then completed 64 paired TRAIN battles against K:

| Measure | Candidate | K |
| --- | ---: | ---: |
| Wins | 37/64 | 32/64 |
| Decisions | 197 | 154 |
| Improved won status cases | 6 | Baseline |
| Raw status applicability concerns | 13 | Status disabled |

The unchanged screen failed: 13 concerns and decision ratio 1.279 exceeds 1.25.
This is measurable TRAIN learning, not transfer or integration qualification.
All 128 episodes completed normally: 69 wins, 59 losses, zero invalid actions or
turn caps, 351 learned choices, 1,788 verified events, 482,048 emulator frames.
All 197 candidate predictions were independently reproduced. No prescribed first
choices, new targets, heldout evaluations, natural-party tests or live promotion.
The 128 prospective comparison configurations remain unopened. No second fit.

## Read-only diagnosis — the training objective and readiness diverge

The 13 flags comprise nine occupied-major-status selections, two already-confused
selections and two full-HP healing selections, across six cases at decisions 3–9.
Two selections occurred while asleep and did not execute; they remain counted.
Only three flagged decisions exactly match eligible TRAIN inputs. All three
match targets that prefer the concerning selection (zero target regret).

Across the full 312-context inventory, 12 targets favor a concerning status choice;
seven have losses in all six measured branches. Original group counts are 0/4/8
such targets, with 0/3/4 all-loss targets. This is not merely fitting error.

For the matched paralysis example, both actions lose all three timing branches.
The status-first sequence deals less damage, but finishes in 2.67 versus 4 turns
and incurs fewer subsequent ineffective-status penalties. Its recorded return is
0.611 higher. The same shorter-loss incentive also appears in a matched confusion
example (0.216 higher). Unit tests reproduce the structural preference for shorter
otherwise-equal losses under the frozen reward. We did not change that reward.

Readiness flags alone are not proof of causal ineffectiveness: execution order,
sleep and later stochastic outcomes matter. Do not equate every flag with an
executed failed move or simply impose a penalty selected to clear this screen.
The evidence identifies reward/readiness mismatch, not one proven universal cure.

## Next bounded decision

Before another fit, design a versioned objective that distinguishes measured useful
effects from downstream continuation noise and does not reward losing sooner.
Audit first-step effect observability in the retained TRAIN traces; healing/Disable
and suppressed actions require explicit unknown/censored treatment, not invented
effect labels. Preserve stochastic outcomes and original return files. Validate
the objective on counterexamples and held-back TRAIN checks before freezing a new
candidate experiment. Keep the 182 retention checks and existing behavior gate;
any acceptance-contract change requires an explicit roadmap decision, not a
post-hoc exemption for this rejected candidate.

Budget 45–60 minutes for objective design and ROM-free falsifiers. This is not a
promise that integration will be ready afterward. No new collection or generic
integration wrapper is justified until the training objective is coherent.

## Closeout

[Independent fit, native and reward audit](../evidence/red-status-feature-readout-2026-09-21.json).
456 targeted battle/documentation tests passed; 13 integration tests skipped.
Changed-module typing, Ruff, registry and documentation checks passed. Native
episode audits ran separately; no whole-package typing or full-suite claim.
Protected story35feb8fa, primarybf603930 and Model141record4ab0e75f hashes unchanged.
Primary109/124, story19/36; Giovanni incomplete. Collection/promotion deltas zero.
Gameplay stopped; no GitHub publication or external-agent/usage actions.
Recommended next session: Astra High, Fast off, for objective/measurement reasoning;
[official model guidance](https://developers.openai.com/api/docs/models/gpt-6-astra).
