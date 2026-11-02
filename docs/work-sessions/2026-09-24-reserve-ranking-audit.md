# Reserve-ranking audit: competing gradients and fragile retained margins

September24,2026. [Evidence](../evidence/red-reserve-ranking-audit-2026-09-24.json).
[Prospective scope](2026-09-24-reserve-ranking-audit-plan.md).
Follows the [failed constrained fit](2026-09-24-constrained-replay.md).

## Outcome and scope

Completed the promised read-only diagnosis before any further fit.
Added a reusable diagnostic and11ROM-free tests;207targeted tests pass.
No model weights, labels, controller inputs, comparison cells or campaign state
changed. This is maintenance unblocking switch/control learning, not learning
progress. All prior failed fits remain closed.

The supported conclusion is shared-gradient interference plus fragile retained
ranking boundaries. Missing inputs, insufficient network capacity and globally
incompatible constraints are NOT established. Do not expand the actor yet.

## Findings

The frozen switch head has38features,16hidden units and640parameters.
Six of seven new switch choices are wrong by the recorded mean returns.
None of those chosen-versus-best candidate pairs appears exactly in the old
inventories. This stronger partial-inventory check found no direct exact-pair
contradiction; it does not prove adequate state information.

For useful MAIN case3-01, the better reserve trails the selected reserve by
14.5758score units. Its own lesson pushes that gap toward correction
(derivative+12.3696). Combining all seven new lessons reverses the direction
to−15.7927; the50/50fresh/replay direction remains−7.7461. Initial Adam also
moves the useful gap the wrong way (−0.02245). Other fresh lessons, not merely
old-example replay, oppose this correction through shared parameters.

For MAIN case3-05, initial Adam points toward the better reserve (+1.08685),
but its useful direction conflicts strongly with some old status-attrition
rankings (cosine−0.9381). Its wrong score gap is11.5540.
Half its hidden activations are saturated above|tanh|.999;3-01has54.7%.
Saturation is a conditioning observation, not proof that gradients vanished.

An earlier prompt choice has only0.00726857score advantage over a worse
measured alternative. Initial Adam decreases that margin by0.0279161to first
order. The optional-prompt group has zero mean regret, so switching to the
worse measured action cannot be compensated by improving another already-zero
case in that group. This is a real constraint of the recorded sample objective.

At the frozen parent, initial Adam is a local ascent direction for fresh
expected regret (+0.00127667), while the plain negative combined gradient is
a descent direction (−0.00113219). Neither is an executed update here.
Decreasing the combined pairwise surrogate does not guarantee useful new
argmax changes; that mismatch was also visible in the closed fit.

## What chance contributes

The retained prompt winner beats its close alternative in only2of5recorded
timings. Its mean advantage2.3324is strongly influenced by one+12.9735outcome;
the other differences include−1.2145,−0.9971,+1.0004and−0.1002.
Both useful new reserve alternatives win their paired comparison in3of5timings.
These are correlated timing siblings, not independent game roots or confidence
intervals. The records do not prove stable underlying action orderings.

Correction to any overly broad dismissal of randomness: no new random battle
caused the fit to stop, but finite-sample variation affects the returns that its
hard retention constraints protect. No gate or old result is weakened here.

## Local freedom, not a global feasibility proof

The distinct old worse-action margin Jacobian has numerical rank365of640 at
relative cutoff1e-10. The desired3-01margin derivative retains20.53%of its norm
outside that row space;3-05retains only0.000120%. Thus3-01has measurable local
first-order freedom even while freezing old sampled margins.
This stricter equality diagnostic is not the actual numeric budget system.
It does not prove a finite nonlinear update can cross the required score gap,
and a small residual does not prove the original inequalities are infeasible.

Independent scalar differentiation recomputed all seven cases and337distinct
replay examples; maximum derivative discrepancy9.55e-14. Input/model hashes
and unchanged protected state verified. The diagnostic never fitted a direction
or candidate actor. Only parent derivatives were inspected, not unsaved final
weights from the earlier trajectory.

## Corrective specification

Next, implement/test an opt-in joint ranking-direction method rather than another
unchanged Adam trajectory. Work from measured chosen-versus-better alternatives;
report useful-margin progress, binding old constraints and solver residuals.
Handle direction choice and retention together rather than relying solely on
post-step rejection and shrinking. Keep exact nonlinear numeric budgets as the
final authority; allow old mistakes to improve and do not freeze all argmaxes.
A local feasibility certificate must not be described as global neural feasibility.

Require synthetic tests for competing lesson gradients, tiny old margins,
compatible progress, old-mistake correction, infeasible local systems and bounded
termination. If no useful bounded method survives those tests, stop with the
specific obstruction. Do not add features or enlarge the model on this audit alone.
Only a separately frozen plan may open one private fit, then the original216
comparison battles if all unchanged fit gates pass. No control-only repeat,
threshold reduction, more labels or consumed-evaluation replay.

Estimated60–90minutes to implement/test the next method, not a qualification
promise. Current deployed actor4ea4cfde,actual461/359a96aa/envelope36dbc835 and
unused462remain protected.45recent contexts retained,24comparison teams unopened.
Story32/36,separate collection109/124,freshRed0/5;zero progress on those counters.
Nothing running;no external agents or GitHub publication.
