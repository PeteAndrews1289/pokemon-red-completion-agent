# Retained replay implemented; unchanged optimizer still fails

September24,2026. [Evidence](../evidence/red-retained-replay-2026-09-24.json).
[Prospective plan](2026-09-24-retained-replay-plan.md).
Follows the [late-state fit diagnosis](2026-09-24-later-attrition-fit.md).

## Outcome

Implemented and tested opt-in complete retained-example replay. The existing
default, actor behavior, feature schemas and numeric gates are unchanged.
Every retained group now contributes to the replay pool; exact ordered
feature/return duplicates receive one optimization vote, not one per group.
Different measured returns remain separate. Constraints keep their original
multiplicities, offsets and limits. Fresh and replay gradients retain50/50weight.

The single frozen fit took156.98seconds and failed: both heads selectedepoch0.
Switch regret stayed0.531374716; full-action control regret stayed0.982116740.
No improvement versus the required10%control gain. All35retention checks over
18groups pass,591status predictions identical,damage/status unchanged.
Candidate d3dd6c09 has parent switch/control weights exactly; only training
membership metadata changed. It is retained as a rejected artifact,not deployed.

All45recent targets remain intact,including9late and36previous contexts.
No new labels,native episodes,controller inputs,frames,comparison battles,
story progress or registrations. All24comparison teams remain unopened.

## What was verified

Replay inventories independently reconstructed:337unique switch examples from
1234budget memberships plus289anchors;326unique control examples from1186budget
memberships plus281anchors. These are optimization-example counts,not new labels
or independent roots. Every budget group contributes without duplicate weighting.

181focused tests pass,including non-anchor gradient influence,deduplication,
different-return preservation,padding/ties,impossible constraints,offset retention,
unchanged default behavior and rebuilt control proposals. Lint and documentation
checks pass;not the full suite. The fit audit recomputed regrets to1e-12,
checked unchanged components and metadata,all saved feasibility flags and selected
checkpoint metrics. Independent closure verifies0native episodes and protectedstate.

Both heads report onlyone feasible checkpoint out of2401:the initial model.
All96logged updated switch checkpoints violate the complete36 joint budget,
forced/prompt family budgets and retained52;all96updated control checkpoints
violate anchors andpolicy16. Logged new-task regret can reach0,but those iterates
are not acceptable and were not retained as actors. Intermediate weights were not
all saved,so exact re-evaluation of all2400iterates is not claimed.

Exact cross-inventory feature screening found two switch matches (one prior
lesson appearing in two groups),with compatible best-vector sets;none forcontrol.
This narrow check found no contradictory exact match. It is not a separability
proof and does not establish that the network can satisfy all desired rankings.
A read-only diagnostic reader's wrong dictionary level was corrected before its
receipt;no fit or native attempt was repeated.

## Decision and next work

The earlier hypothesis was incomplete: including missing lessons is mechanically
correct, but uniform replay alone did not produce useful retained learning.
Do not repeat the same Adam trajectory with another packet name or collect more
battles for this question. Do not reduce the10%threshold or loosen retention.

Next,design a bounded constraint-aware update method: rejected retention checks
must influence the proposed direction/step,not only checkpoint selection. Reuse
the existing measured budgets and investigate bounded backtracking/projection.
Do not lock every old argmax choice,which could also freeze old mistakes.
First demonstrate feasible improvement and honest infeasible termination on
ROM-free examples,including compatible/impossible constraints and composed
proposal offsets. Only then freeze one separately declared offline attempt;
no parameter sweep or automatic secondfit. Estimate60–90minutes to that next
decision,not a guarantee of qualification.

Existing45contexts and24untouched comparison teams suffice for this next question.
No new model architecture,teacher factory,consumed-game replay or promotion.
Actual461/state359a96aa/envelope36dbc835,deployed4ea4cfde and parentb106108e unchanged.
32/36story,109/124separatecollection,freshRed0/5. Nothing running.
