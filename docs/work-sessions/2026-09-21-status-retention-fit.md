# Retention-aware status fit

## Prospective mission check

1. Capability: useful status/recovery decisions across full battle trajectories.
2. Authority: fit only the existing compact status selector; frozen K damage,
   control and switching remain exact. No action rule, mask or teacher fallback.
3. Transfer: freeze128new generated comparisons before fitting, then open only
   after TRAIN fit/trajectory gates pass. Related TRAIN ancestry is not natural
   independent-origin qualification; no automatic campaign deployment.
4. Cheapest falsifier: new fit cannot reduce later-turn regret while retaining
   measured negative preferences, or the TRAIN trajectory behavior gate fails.
5. Time box: two-hour session; one fixed fit and at most384native evaluation episodes,
   with45minute packet deadline and existing per-episode40turn/45second limits.
6. Stop: unverified data or failed gate; preserve outcomes and reject the candidate.
   No consumed-holdout tuning, extra same-data optimizer sweep, main-save writes
   or publication. Reassess failures instead of making readiness claims.

## Frozen learning design

Use all94prior TRAIN contexts and97new later-turn TRAIN contexts as separate
continuation-tagged groups, equally weighted by group, without averaging targets
across policies. Both use the unchanged closed-loop-return.v1. Prior observed
continuation differences remain explicit in target digests and group metrics.
Warm startfc4098a6: it passed the prior TRAIN behavior screen, unlikeb8f3a53d.

One deterministic6000epoch weighted cross-entropy fit,learning rate0.03,existing
16hidden units and compact features. Soft targets are softmax(3*mean returns);
example cost is clipped absolute return gap[0.1,4]. Full-batch vectorized updates.
Retain every robust negative preference that the initial model already gets right:
status is worse by0.05in each of its three measured timing branches. Preserve
damage-versus-status score margin min(initial margin,0.05) by bounded backtracking
(up to12halvings per proposed step), otherwise reject the optimizer step. No runtime
special-case rule or snapshot identity enters the model. All uncertain examples
remain in the objective; timing variation is not erased or claimed independent.

Fit gate: zero protected-preference regressions, at least25%lower new-group regret,
and no old-group regret regression. Then64TRAIN starts paired with K under the
unchanged gate: no win regression,no applicability concerns,at least one useful
status win,decisions<=1.25*K. If passed, evaluate128new balanced configurations
from seeds2026092201–2026092204 against K, excluding previous cohort configurations.
Same aggregate gate; report cohort/family results and losses, not superiority from
a small correlated sample. No selected/replacement cohort or additional fit.

A pass establishes bounded single-member laboratory behavior, not natural-party
status integration, broad Gen1 mastery, Giovanni completion or a final Red run.

## First fit closed: retention optimizer stalled before evaluation

The initial fit retained109negative preferences but accepted only8of6000proposals;
5992updates were rejected at a constraint boundary. Old-group regret improved
0.654300→0.436565 while new-group regret0.750391→0.755030 failed. No native evaluation,
holdout or promotion. Keep the original candidate/fit/result unchanged.

This exposes an optimizer limitation: repeatedly shortening the same full-gradient
direction cannot move along a curved constraint boundary. A distinct corrective
packet uses SLSQP with analytic objective/constraint Jacobians to solve the same
constrained problem. Retain the same data,initial model,features,soft targets,cost
weights,protected109preferences and fit/behavior gates. Maximum500iterations and
15minute optimizer bound,one solver invocation,no restart or hyperparameter sweep.
The solver is an offline numeric dependency,not an external model or runtime
action filter. Nonconvergence or constraint violation rejects its candidate.

The original128heldout recipes remain unopened and may be bound as an unchanged
prospective inventory in the corrective packet; no outcomes exist to tune against.
If the corrected fit passes, carry out the originally planned TRAIN and withheld
evaluation. Source and new packet identity must be committed before fitting.

## Numeric-cap continuation — no evaluation has opened

SLSQP reached500iterations with zero retention violations and strictly positive
minimum constraint slack0.000445497. New-group regret0.750391→0.005452 and old-group
0.654300→0.004329; no high-cost mistakes remain. Its convergence flag is false, so
the original result remains fit-gate-failed and no evaluation game was played.

Prospective bounded continuation: resume those exact saved weights for at most5000
additional solver iterations/15minutes, retaining the same objective,ftol1e-9,
109original-anchor constraints,data digests and still-unopened128comparison recipes.
This amends only the numerical work budget after a cap, not fit/behavior thresholds,
data selection or outcome-based tuning. Preserve both prior attempts and count the
extra optimizer invocation explicitly. No repeat cap extension or alternative fit;
stop on nonconvergence/infeasibility. Only a converged feasible candidate may enter
the original TRAIN and fresh comparison gates.

## Final outcome — converged fit, rejected battle policy

The saved iterate converged after357additional SLSQP iterations,loss0.143945601,
minimum constraint slack0.254837980. All109protected preferences remain correct.
Old94context regret0.654300->0.004329; new97context regret0.750391->0.005452.
All17initial high-cost mistakes across the two groups became zero. Seven smaller
measured errors remain. This is training improvement, not deployment readiness.

Actual paired TRAIN battles: candidate35/64wins versus K32/64,246versus154decisions
(59.7%more,exceeding the25%cap),19flagged status selections,6improved won status
cases. The unchanged behavior gate failed. No heldout game was opened; the128
prospectively declared generated configurations remain unused. No candidate was
promoted; no natural-party or Giovanni qualification occurred. All three optimizer
invocations and their artifacts are retained, not reported as one successful run.

Independent read-only audit reconciled128episodes,400decisions,1984event records,
all128terminal state hashes and246candidate predictions.67wins/61losses,zero invalid
actions,turn caps,prescribed moves or actor memory writes. Frozen K damage/control/
switching remain exact. All191target bindings,continuation groups,retention margins,
fit gates and the numerical-continuation identity were independently checked.

## Failure diagnosis — not just more optimizer work

Seven battles contain the19flags:4major-status-occupied,3already-confused,
12full-HP-heal selections. The12heal selections occurred while asleep and their
selected-turn outcome reports move_executed=false. Calling all19executed redundant
moves would therefore be incorrect. Seven awake concerns remain, and the unchanged
turn-overhead gate independently fails, so this diagnosis does not rescue the policy.

Sixteen flagged inputs have no exact match in the191training examples. Three do
match and have selected_return_gap=0: the existing measured returns actually favor
or tie the choice being flagged. Those three are asleep/Rest decisions. This is a
label-versus-diagnostic mismatch requiring execution-aware interpretation, not
forgetting of the109protected negative lessons. Timing-dependent returns under
older continuation policies may reward a selection that cannot execute that turn;
causal action benefit has not been established for those labels. Do not overwrite
them, impose a runtime Rest ban or quietly exempt these cases from the consumed gate.

Next bounded work: reconcile action-selection versus execution opportunity in
TRAIN labels/diagnostics, then freeze a new on-policy collection/update packet.
Require paired outcomes on awake redundancy states and later-turn states reached
by the current candidate, with uncertainty explicit and no heldout fitting.
Do not repeat these numeric fits, add iterations, reuse consumed evaluation or
deploy the rejected candidate. Budget60-90minutes for the label/coverage correction
and its smallest falsifier; unseen and natural multi-party gates remain separate.

## Closeout

[Path-free audit](../evidence/red-status-retention-fit-2026-09-21.json).
263battle tests and174documentation/focus tests passed;13integration tests skipped.
Private native audits passed separately; registry and documentation checks passed.
Changed fitter typing and Ruff passed. No whole-package typing claim.
Protected story35feb8fa,primarybf603930,Model141record4ab0e75f and Ke626e343 hashes
rechecked unchanged. Story19/36,Giovanni incomplete,primary109/124;collection delta0.
Gameplay stopped. No external models,quota action or GitHub publication.
Next recommendation:Astra High,Fast off,for the label/behavior mismatch;
[official model guidance](https://developers.openai.com/api/docs/models/gpt-6-astra).
