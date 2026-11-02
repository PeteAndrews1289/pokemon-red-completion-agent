# Status effect observability and TRAIN-root prediction probe

## Prospective mission check

1. Capability: distinguish measured turn-boundary changes, suppression and unknown
   effects, enabling authentic immediate-effect teaching instead of noisy battle returns.
2. Authority: no actor changes. A separate diagnostic predictor may learn observable
   changes; it is not an applicability mask, effect-success oracle or live policy.
3. Transfer test: hold out the lexicographically last of the four existing TRAIN
   roots for this predictor only. All rows/timings from that root stay out of fitting.
   These roots were previously used by battle models; this is a TRAIN diagnostic,
   not an untouched evaluation, natural-party qualification or cross-title claim.
4. Cheapest falsifier: records cannot distinguish a relevant effect from ambiguity,
   or a fresh predictor cannot improve over a training-prevalence constant.
5. Time box: 60 minutes; read existing 936 status-first branches only, no gameplay.
   At most one 500-iteration logistic fit, no hyperparameter or split search.
6. Stop: provenance failure, inadequate classes/coverage, nonconvergence or worse
   prediction. Never convert missing effects to failures or waive a battle gate.

## Frozen semantics and diagnostic design

Use authenticated first decisions from the same 312 eligible contexts and three
timing offsets. Predict observable persistent change, NOT causal move success.
No later outcome/return, species identity, root identity or case ID enters features.
Use only the existing compact semantic status-choice vector plus an intercept.
No pretraining or learned features from a model exposed to the held-back root.

Record suppressed selections separately; exclude them from the conditional-on-
execution predictor and explicitly disclaim unconditional effect/success prediction.
Changed/terminal opponents, missing context and unreliable boundary identity are
unknown. Major-status change requires a newly visible intended affliction; an
unchanged nonempty sleep status is duration-ambiguous. Confusion already present is
ambiguous because expiry/reapplication cannot be resolved from two booleans.
Accuracy reductions are measured from visible stages. Healing/Rest and Disable
remain unknown: net HP/end-turn state cannot prove their immediate effect.
No readiness flag is directly copied into a success/failure target.

If both fit and held-root subsets contain positive and negative observations, fit
one zero-initialized logistic predictor with L2=0.001 on non-intercept weights,
equal total weight per training root then per context and timing. L-BFGS-B,
max500iterations, ftol1e-12. Report Brier/log loss and threshold0.5 confusion counts
on fit/held-root, plus per-family coverage. Diagnostic pass: finite convergence and
held-root Brier at least10%below the fit-prevalence constant. Do not refit on held-root.
Even a pass cannot promote or combine this predictor with the player without a
separate behavioral design/qualification. Preserve182preferences, rewardv2, all
rejected candidates and128unopened generated comparisons.

## Result — closed rejected diagnostic

Source freeze60750f9f. Authenticated936existing status-first branches twice, from312
contexts.392observations have reliable net-change labels:145positive/247negative;
71suppressed and473unknown stay out of fitting. This adds no causal-success labels.
Healing/Rest/Disable account for331unknowns; sleep duration84, confusion ambiguity54,
terminal/missing opponent4. Confusion has26positive and zero observed negative rows:
its apparent prediction performance cannot establish discrimination.

One fit converged in40iterations. Three fitting roots:333rows/116contexts;
excluded TRAIN root:59rows/23contexts. No shared roots/contexts/timings, no pretrained
features. All392predictions reproduced without fitting again.

| Root subset | Predictor Brier, lower is better | Fit-prevalence constant |
| --- | ---: | ---: |
| Fitting | 0.03253 | 0.24929 |
| Excluded TRAIN root | 0.38335 | 0.25341 |

Diagnostic rejected: threshold0.5predicts positive on all59excluded-root rows,
including38false positives. No second fit or split search was attempted.

Read-only diagnosis: all24poison-immunity and12electric-paralysis-immunity observed
rows occur in the excluded root; both corresponding features are zero throughout
fitting. Their fitted coefficients remain exactly0. This accounts for36of38false
positives: the dataset ties important mechanics to root identity. It is not evidence
that an optimizer failed to converge, nor that a model can infer never-taught immunity
from the compact features. A global two-class coverage check was insufficient; future
coverage checks must include mechanics-by-root support. Do not repair this result by
moving these tested rows into fitting or weakening its frozen threshold.

## Next bounded implementation, not another refit

1. Remove root/condition coupling in the scenario recipe builder. Freeze a mechanics
   matrix with useful/occupied/immune/floor cases represented across fitting roots
   and a separate reserved scenario cohort. Detect absent/constant required features
   before fitting. Use new packet identities; retain this failed probe unchanged.
2. Add training-only selected-move effect telemetry for currently ambiguous healing,
   Rest, Disable and confusion renewal. Record the selected move's own effect boundary,
   not HP after the opposing attack. Duration/debug reads must stay in the adapter and
   out of actor features. First verify a tiny native contrast set; unknown remains
   unknown when causal attribution is unavailable. No uncontrolled broad collection.
3. Only after coverage and observation checks pass, freeze a new measured-effect
   training design and a learned policy-combination experiment. Do not mask actions
   with this classifier or treat its conditional probabilities as expected battle value.
   Preserve182prior preferences, rewardv2 and the unchanged native readiness gate.
4. A policy that passes TRAIN readiness still needs the unopened comparisons and
   independent natural-party testing before earned story/Giovanni integration.

Next session:60-90minutes for the coverage/preflight and narrow telemetry work;
native label readiness is conditional, not a promised full integration deadline.
This is diagnostic learning progress, not better player behavior. Zero gameplay,
new collected outcomes, collection progress or promotions. Protected story/primary/
Model141hashes match;128reserved comparisons unopened.497targeted tests passed,
13private integration tests skipped. Gameplay/workers stopped; no publication.

[Path-free evidence](../evidence/red-status-effect-observability-2026-09-21.json).
Private packet:red-status-effect-probe-20260921-v1. No player checkpoint produced.
