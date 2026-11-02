# Constraint-aware updates work locally; proposal selection still blocks qualification

September24,2026. [Evidence](../evidence/red-constrained-replay-2026-09-24.json).
[Prospective plan](2026-09-24-constrained-update-plan.md).
Follows the [complete replay experiment](2026-09-24-retained-replay.md).

## Outcome

Implemented opt-in projected_budget_v1 and ran its single frozen experiment.
196targeted tests pass; default training and inference remain unchanged.
The candidate improved full-action control regret9.4623%, below the unchanged10%gate.
This recovers the earlier best result; it is not a new performance high.
Switch regret remains0.531374716. Control regret fell0.982116740to0.889185591.
Candidate e7eb0e9e is rejected, not deployed. No comparison or campaign opened.

The method accepted34switch and44control updates without crossing any retained
numeric budget. Both heads stopped when their bounded proposed step had no
acceptable backtracking trial. Switch selectedepoch0;control selectedepoch33.
35switch/45control feasible checkpoints were logged. All18groups/35retention
checks pass;591status predictions identical;damage/status components fixed.
The single fit took76.27seconds. No secondfit or parameter sweep was performed.

## Implementation and verification

All distinct retained examples enter the50/50fresh/replay objective, preserving
337switch/326control replay rows and all existing group multiplicities/offsets.
A violating Adam proposal is projected against local score margins opposing
strictly worse measured actions. Equal/better alternatives are not locked out.
At most10projection passes and13step halvings are permitted. Exact nonlinear
budgets and strict objective descent decide acceptance. Rejected weights/moments
do not advance; initial infeasibility and exhausted steps stop explicitly.
This is a local bounded heuristic, not a global feasibility solver.

ROM-free tests cover feasible improvement, old-mistake correction, incompatible
constraints, proposal offsets, padding/ties, numerical Jacobians, nonfinite
configuration, unchanged defaults and deliberately incorrect projection rejected
by the nonlinear checks.196focused tests/lint pass;not the full suite.
Independent fit audit reconstructs selected regrets, replay inventories and
status predictions, checks accepted-history feasibility, ordering, objective
descent and iteration limits. Intermediate weights were not all saved, so
replaying every numerical iterate independently is not claimed.
Independent closure confirms0native episodes and unchanged protected state.

## Why further control-only training cannot pass

All four new control choices changed and now select the higher measured return
of the two proposals actually offered. Their conditional control regret is0.
The entire remaining0.889185591regret comes from better actions absent from those
proposals. The gate permits at most0.883905066. Thus no further control-only fit,
with these same move/switch proposals, can bridge the0.005280525gap.

Three cases omit better measured moves from the frozen move proposal. Two also
contain better reserve choices that the switch head did not select:

| TRAIN context suffix | Better measured reserve | Possible per-case proposal-cost reduction |
| --- | --- | ---: |
| 3-01 | slot3 | 0.120678346 |
| 3-05 | slot5 | 1.087424536 |

These are diagnostic measured alternatives, not injected actor instructions.
With the best measured switch proposals and ideal control, the conditional
aggregate floor would be0.587159870, or40.2149%below the parent's full-action
regret. That is an analytical bound, NOT an achieved result, proof that all
retention constraints can coexist, or evidence of transfer.
The final switch step still violated complete36 and its optional-prompt budget
at the smallest allowed trial. Its34accepted steps did not improve actual new
switch decisions, and their new expected regret worsened while the combined
training objective descended. More iterations of this unchanged rule are not
justified by this result.

## Next decision

Close this packet. Audit the two helpful reserve rankings against the specific
retained prompt constraints using the saved TRAIN vectors/returns. Determine
whether the obstruction is the local update direction, shared representation,
or coupled proposal objective before another prospective fit.
Do not repeat control-only fitting, lower10%, relax retention, increase iteration
counts blindly, collect more labels, reopen consumed comparisons or add a new
actor architecture on this evidence alone. Estimate45–90minutes for the focused
feasibility decision, not a qualification guarantee.

All45recent contexts remain intact.24comparison teams remain untouched for the
original216three-arm screen after a future fit passes. Actual461/state359a96aa,
envelope36dbc835,deployed4ea4cfde and unpromoted parentb106108e are unchanged.
32/36story,17campaign registrations,109/124separate collection,freshRed0/5.
0new labels/native actions/story/registrations/promotions. Nothing running.
No external agents or publication.
