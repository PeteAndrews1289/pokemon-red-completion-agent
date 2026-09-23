# Execution-aware status learning

## Prospective mission check

1. Capability: select useful status/recovery actions over actual battle trajectories.
2. Authority: only the compact learned selector changes; K damage/control/switching
   remain frozen. No runtime move ban or teacher substitution.
3. Transfer: full TRAIN screen, then the previously unopened128configuration cohort
   only if the unchanged gate passes. No independent natural-party promotion.
4. Cheapest falsifier: label eligibility incorrectly discards awake stochastic
   suppression, or a new on-policy fit still fails full-trajectory behavior.
5. Budget: two-hour session; one collection of64TRAIN trajectories, at most512
   sampled contexts/3072branches, one fixed fit, then at most384evaluation episodes.
6. Stop: invalid provenance, failed fit/behavior gate or time budget. No same-packet
   refit, consumed-evaluation replay, gate weakening or protected-save write.

## Frozen correction and collection

Keep original outcome files and closed-loop-return.v1 unchanged. Add a separately
versioned TRAIN eligibility report: do not infer move-ranking labels from a decision
whose pre-observation says the player is asleep. Retain its costs and outcome in
whole-battle evaluation. Do NOT filter awake rows based on whether a sampled move
subsequently executed: that would discard real paralysis/miss/faint consequences.
Execution diagnostics report selected, executed and asleep separately; the original
qualification gate is unchanged and every original rejection remains rejected.

Collect native pre-decision snapshots from frozen candidateeb11d733 at indices
2,3,4,5,6,8,12,19 on each of the64original TRAIN starts. Preserve every trajectory,
including sleep selections; measure eligible awake snapshots with both legal choices
and existing timing offsets0,11,12 under that same frozen continuation. No failed
case-only selection or injected labels. Old94and97targets remain separate groups.
New target capture identities must include the packet identity, not collide with
earlier actors' trajectory capture IDs. Audit snapshot observations and branch logs.

## One prospective update

Use awake-eligible rows in the three continuation-tagged groups, each equally
weighted. Warm startfc4098a6, retain its correctly ranked robust negative examples
at margin min(initial,0.05). Same compact16hidden units, cost-weighted soft-target
cross entropy, plus fixed0.001mean-square distance to the initial parameters to
discourage the unconstrained weight growth that fit the old small dataset.
One SLSQP solve,max2000iterations/15minutes,ftol1e-9,no numerical continuation.
This is a new-data regularized experiment,not another iteration of the closed fit.

Fit admission: convergence,feasible retention,old-group mean regret no worse than
initial,and at least25%lower combined later-group mean regret. Then unchanged
64paired TRAIN gate (wins nondecreasing,zero raw applicability flags,at least one
useful won status case,decisions<=1.25*K). Only after that pass,128frozen unopened
configurations versus K,with the same gate and four cohort reports.
No claim of live readiness without independent-origin/multi-party qualification.

## Result — correction and collection verified; fit rejected before evaluation

All64frozen-actor trajectories completed.136snapshots were retained:126awake
contexts measured with756native branches,10asleep snapshots excluded prospectively;
376sampling positions were unreached/non-main. All64action/observation sequences
matched the prior uninstrumented actor run. This is a new TRAIN collection, not
a replay of a consumed evaluation. Five older asleep rows were excluded only from
the new fit view; original targets and whole-battle costs remain unchanged.

Independent audit verified820episodes,3516decisions,17668event records,all820terminal
hashes,136snapshot bindings,246trajectory predictions and2514branch-continuation
predictions.451wins/369losses,zero invalid actions or turn caps.756prescribed first
choices and2760learned choices remain explicitly separate. No fit on heldout data.

Eligible fit group sizes92/94/126. All182protected negative preferences retained.
Mean regrets0.668524/0.774340/0.717280 became0.000127/0.004614/0.253342;
high-cost errors27->3,ordinary errors38->9. The new candidate's first-layer norm
is50.626,versus2404.186for the previous rejected actor and2.527for the warm start.
These are TRAIN diagnostics,not an independently verified gameplay improvement.

The single fixed regularized solve reached2000iterations without convergence:
loss0.159582039,minimum constraint slack0.000196866,parameter distance64.122847.
The frozen fit gate rejected it. No TRAIN comparison or heldout evaluation was
started;128prospective comparison configurations remain unopened. Candidate
0734686a is retained and NOT deployed. No numerical continuation or alternate
fit was run. The new data and eligibility correction are reusable; this learner
has not finished the status battler.

## Reassessment and next bounded decision

The execution-opportunity correction is complete and measured data expanded.
Repeated nonlinear constrained solves now hit their numerical caps despite
feasible retained preferences. Do not automatically add iterations or fabricate
successful battle qualification from a low training loss.

The next design to assess is an anchored final-layer-only update with fixed
learned hidden features: cross-entropy plus quadratic regularization is convex
in the output weights and retention constraints become linear. This removes the
specific nonlinear constraint-boundary problem while preserving learned authority,
data provenance and the outcome gates. It is a prospective design recommendation,
NOT another fit executed on this packet or a proven cure for generalization.
First check representation adequacy and numerical tests; then separately declare
one fit and its evaluation. Budget45-60minutes for that bounded redesign/falsifier;
no promise of live readiness. Original failures remain closed.

Protected story35feb8fa,primarybf603930 andModel141record4ab0e75f hashes unchanged.
Primary109/124,story19/36,Giovanni incomplete;collection and authority deltas0.
268battle tests and174documentation/focus tests passed;13integration tests skipped.
Native audit,registry and documentation checks passed separately.
Changed-module typing and Ruff passed. Gameplay stopped; no GitHub publication,
external model,quota reset or purchase. A reported model-capacity interruption did
not stop the local experiment; the actual stop was its numerical fit gate.
Recommended next model:Astra High,Fast off,for numerical-learning design review;
[official guidance](https://developers.openai.com/api/docs/models/gpt-6-astra).
