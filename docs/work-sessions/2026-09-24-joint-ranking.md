# Joint ranking: real local learning, failed composed handoff

September24,2026. [Prospective plan](2026-09-24-joint-ranking-plan.md) ·
[Evidence](../evidence/red-joint-ranking-2026-09-24.json).

## Outcome

Implemented the opt-in joint ranking solver, passed222focused tests, completed
the one declared private fit and independently audited its saved checkpoints.
The bounded experiment is closed and failed. The battler is NOT qualified.
No comparison team, campaign input, new label, promotion or publication occurred.

Switch regret improved0.5313747161→0.4952445949. Correct fresh choices rose1/7→2/7;
the improvement is a forced reserve choice, not either helpful MAIN proposal.
There were58accepted updates; checkpoint46was selected. Every accepted switch
checkpoint satisfied its original numeric switch budgets. Old mistakes remained
free to improve; no actor feature, architecture, status or damage component changed.

Control then stopped at initialization: the selected switch changed its concrete
proposals and put the unchanged control head outside7old full-action budgets.
For6of those groups, even choosing the best offered alternative cannot recover
the budget. No control update occurred, and no combined candidate was written.
The complete two-head retention screen did NOT pass. Do not report the switch
checks as35passed combined checks or an accepted complete model.

## Implementation and verification

`joint_ranking_v1` jointly maximizes a useful measured ranking direction under
bounded parameters and local worse-action guards, then minimizes L1 movement
while keeping90%of the available improvement. Trust-region trials are solved
again rather than projecting an Adam direction. Actual nonlinear numeric budgets
and fresh selected regret determine acceptance. Every accepted parameter vector,
target choice, solver residual, binding guard and rejected attempt is retained.

Synthetic tests demonstrate correction despite shared-gradient interference,
large wrong scores with tiny old margins, old-mistake improvement, ties, numerical
input rejection, honest local infeasibility, solver failure and nonlinear vetoes.
The default fitter remains unchanged. Both old/new paths preserve frozen heads.
222targeted tests and lint pass; this is not a full-suite result. An additional
type-check invocation encountered two pre-existing imported errors in
`red_damage_interaction_head.py`; no error was reported in the new module.

Private fit lasted148.73seconds. Independent audit reconstructed60checkpoints:
59switch points including initialization and1unchanged control initialization.
The closed run has no completed combined candidate, so no591-choice final-candidate
claim is made; the frozen components were never updated.

## Exact failure, not another control-only optimization problem

At selected switch checkpoint46, illustrative old control floors are:

| Group | Best possible offered-action regret | Maximum allowed |
| --- | ---: | ---: |
| anchors | 0.199255003 | 0.194343987 |
| new80-canonical | 0.229339804 | 0.222758409 |
| new80-nonoverlap | 0.153011862 | 0.149043530 |
| prior48 | 0.388348050 | 0.368712658 |
| terminal128-canonical | 0.145971925 | 0.142095767 |
| terminal128-nonoverlap | 0.090575161 | 0.088574822 |

The all-nonoverlap group also regresses with the unchanged control head, but its
offered-action floor is below its budget. It is not one of the six irreducible
proposal failures. These are conditional floors for this switch checkpoint,
not impossibility proofs for the model or the original training problem.

All59saved switch checkpoints still have new full-control floor0.8891855907;
the unchanged10%gate requires at most0.8839050659. Fifteen of those checkpoints
can start the old control head feasibly, but none offers enough new improvement.
Thus selecting an earlier saved checkpoint or merely fitting control cannot
rescue this declared experiment. The9.4623%ceiling was already known and is not
presented as a new performance gain.

## Required correction

The two-stage training seam is incomplete: switch training constrains switch
outcomes but does not constrain the downstream control proposals affected by
every switch parameter update. Its checkpoint selection also does not reward
the MAIN proposal improvements needed to pass the full-action objective.

Next implement a composed, measured-outcome constraint/objective for switch
training and selection, including control-bearing contexts rather than only
explicit switch-head rows. Preserve original numeric budgets and full-action
offsets. First demonstrate on a synthetic case where a better switch-only score
destroys a required control proposal, plus a compatible joint correction.
Do not simply let an initially infeasible control stage train: six conditional
floors already show why that alone cannot work here.

This needs a new prospective experiment, not a blind repeat of the closed fit.
No reason to change inference architecture or relax noisy finite-sample budgets
has been established. Original216battle comparison stays available after a
future complete fit passes; no comparison retry or threshold adjustment here.

Actual461/state359a96aa/envelope36dbc835 and deployed4ea4cfde are unchanged;
462unused. Story32/36,17campaign registrations,109/124separate collection,
freshRed0/5. Nothing running. Estimate60–90minutes for the composed-training
repair/tests, with qualification time dependent on its measured outcome.
