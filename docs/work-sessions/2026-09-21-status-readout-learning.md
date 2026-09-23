# Fixed-hidden status readout experiment

## Prospective mission check

1. Capability: learn useful status/recovery choices without unstable nonlinear
   updates to the existing battle representation.
2. Authority: only16learned output weights change. Hidden features and K damage,
   control and switching remain exact. No move rule,mask or teacher fallback.
3. Transfer: full64paired TRAIN trajectories before128previously unopened generated
   comparisons. These share TRAIN ancestry,not independent natural-party qualification.
4. Cheapest falsifier: fixed hidden features cannot express useful corrections while
   retaining measured negatives,or the single convex fit fails its admission gate.
5. Budget:60minutes; one readout fit,max500iterations/60seconds; at most384evaluation
   episodes with existing40turn/45second per-episode bounds. No new collection.
6. Stop: infeasible retained preferences,failed fit/behavior gate or time limit.
   No alternate hidden basis,hyperparameter sweep,cap extension or save promotion.

## Frozen design

Use the audited execution-learning TRAIN views92/94/126,with the original three
continuation policies tagged separately. Preserve predecision-sleep exclusions;
keep awake stochastic suppression and all original costs/outcomes. Source weights
arefc4098a6,the earlier TRAIN-behavior-screen-passing initial model,not weights
selected from an evaluation. All old candidates/packets remain rejected and intact.

First inspect hidden contrast rank and test whether each high-cost initial error
is individually correctable under the retained-preference inequalities. Linear
feasibility witnesses are diagnostic only; discard them,do not instantiate policies
or claim joint learnability. An impossibility result remains visible,not relabeled.

One output-layer update: same equal-group weighting,softmax(3*returns),cost gap
clipped[0.1,4],and0.001mean-square displacement from the initial output weights.
Hidden activations are fixed,so this objective is strictly convex and retained
damage-score margins min(initial,0.05) are linear constraints. SLSQP uses analytic
gradient,max500iterations,ftol1e-9; no numerical continuation. Report gradient/
optimality diagnostics independently of convergence and actual argmax learning.

Unchanged admission: successful finite feasible fit,zero retention regressions,
oldest-group regret not worse,and at least25%lower combined later-group mean regret.
Then original TRAIN gate: wins>=K,zero raw applicability flags,at least one useful
won status case,decisions<=1.25*K. Only if passed,open the unchanged128withheld
configuration recipes and report the same gate plus all four cohorts. No test-set
fitting,retrospective asleep exemptions,live promotion or full-game run.

## Verified outcome

The convex solver converged in103iterations/0.029seconds,with all182protected
preferences retained and hidden parameters,K damage/control/switching unchanged.
Independent objective/gradient audit reproduced loss0.768229498 and stationarity
residual1.57846e-5. Constraint slack differs from zero only at rounding precision
(-4.02e-16). The numerical convergence bottleneck is resolved for this learner.

Representation rank16of16;25of27initial high-cost errors are individually correctable
under retention constraints. Two are infeasible for this basis/constraint set.
Individual feasibility does not imply the25corrections can all be made together.

The candidate5f6e9d5a nevertheless failed the unchanged TRAIN fit-admission gate:

| TRAIN group | Initial mean regret | Candidate mean regret |
| --- | ---: | ---: |
| Oldest92contexts | 0.668524 | 0.674090 |
| Later94contexts | 0.774340 | 0.569701 |
| On-policy126contexts | 0.717280 | 0.615820 |

Combined later-group mean regret fell20.521%,short of25%; oldest-group regret
slightly increased. High-cost errors27->22; total errors above0.05remain38.
These are TRAIN diagnostics,not a battle loss or a generalization claim. No TRAIN
trajectory or heldout evaluation was launched; no new emulator frames,observations
or targets. All128prospective comparison configurations remain unopened. One fit,
no cap extension,alternative basis or hyperparameter search. Candidate rejected.

## Next bounded design

The old fixed hidden representation plus this anchored objective is insufficient
for the admission threshold. The evidence does not isolate representation alone
from regularization/retention tradeoffs; do not call every remaining error
mathematically unlearnable. Numerical convergence is no longer the next task.

Assess using the existing TRAIN-learned0734686a hidden layer with the now-verified
convex readout update. That richer model already had much lower TRAIN regret but
was rejected before evaluation because its nonlinear solve did not converge.
Its original candidate remains rejected; using its frozen TRAIN features in a new
prospective experiment is not retroactive acceptance or an evaluation-selected basis.

Keep three roles explicit in that future design: fixed hidden basis0734686a;
output-weight anchor0734686a; retention reference and comparison baselinefc4098a6.
Retain the original182negative preferences and their original score-margin minima,
mapped into the new fixed feature space. Do not silently change the baseline or
claim a new candidate passed because it copied a rejected model. Check feasibility
before one separately frozen fit,then the unchanged TRAIN and withheld gates.
No new data collection or nonlinear training is needed for that question.
Budget30-45minutes for implementation and the first bounded test; live readiness
is not promised. This packet is closed and did NOT test the alternate basis.

## Closeout

[Read-only audit](../evidence/red-status-readout-learning-2026-09-21.json).
277 targeted battle tests and 174 documentation tests passed; 13 integration tests
skipped. Documentation, registry and roadmap checks, changed-module typing and
Ruff passed. Original model/target/inspection bindings and all312fit contexts
were checked independently. No native evaluation or collection delta this turn.
Protected story35feb8fa,primarybf603930,Model141record4ab0e75f hashes unchanged.
Primary109/124,story19/36,Giovanni incomplete;zero authority promotion.
Gameplay stopped;no external models,quota actions or GitHub publication.
Recommended next session:Astra High,Fast off,for the separate-basis/retention seam;
[official model guidance](https://developers.openai.com/api/docs/models/gpt-6-astra).
