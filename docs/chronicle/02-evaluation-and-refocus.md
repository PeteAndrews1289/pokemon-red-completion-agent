# 2. August 6–14: high scores meet the real game

[Previous](01-teacher-and-first-learners.md) · [Contents](README.md) · [Next](03-scenarios-and-strategic-learning.md)

## A safe answer is not necessarily a useful answer

The August record increasingly distinguishes teacher agreement from causal success.
A model can imitate “flee” accurately while failing to train the party. It can
predict healing conservatively while spending most of its time traveling back to
a Center. It can finish a fixed route without learning which destination is useful.

The archive describes a masked-action mismatch: inference removed unavailable
actions, but fitting still learned from forced choices as though they were real
alternatives. Large numbers of compulsory flees could therefore distort choices
at genuine fight-or-flee boundaries. The repair aligned training masks with the
available action menu; forced singletons were not new strategic decisions.

Another lesson concerned observability. Some healing labels depended on the
escort's condition while the input represented only the trainee. A learner cannot
reliably distinguish states that its features make identical. The response was
to expose the relevant semantic condition, not pretend more labels would solve it.

These examples are preserved as historical diagnoses, not a claim that every
later model inherited or qualified every earlier mechanism.

## Navigation became a stateful problem

During August 10–11, the narrative moves from fixed directions toward map-derived
navigation and observed replanning. Water, ledges, Cut trees, boulders, trainer
sight and changing objects all challenge the assumption that a tile is either
permanently open or permanently blocked.

A geometrically short route could trigger an unwanted trainer. A move could turn
the player rather than advance a tile. Owning Cut did not mean a particular tree
had already been removed. A policeman or story event could alter available paths.

Those repairs supplied reusable mechanics. They were not learned route selection.
That separation later became crucial: a destination model should compare real
opportunities, while the executor should reliably carry out a legal chosen route.

## The evaluator itself needed scrutiny

The August 13 account records a destination-learning audit. An initial model had
far more fitted parameters than the small set of training examples justified and
had been selected using repeated development comparisons. The redesign favored
a small scorer and training-only selection.

More importantly, a test could be incapable of resolving the claimed question.
If a learned policy and a cheapest-route baseline nearly always agree, a large
agreement score does not establish learned strategic value. The project began
examining whether scenarios actually offered informative alternatives before
spending expensive native evaluations.

The current [mission](../../MISSION.md) also preserves a severe reporting mistake:
earlier receipts had reported the Champion's party levels as the player's.
The lesson is not that checks guarantee truth. It is that attractive numbers
need independent observation and an explicit correction when they are wrong.

## August 14: stop using whole games as unit tests

The most consequential refocus followed a live supervised run that stopped after
1,250 balanced-team battles and more than 85 million frames. The archive reports
2,260 battle proposals with 600 disagreements. A team ranker scored a very large
number of teacher rankings without controlling them; goal and destination models
were still offline.

Visible behavior made the limits obvious. Fixed Saffron movements pressed against
obstacles. Conservative healing ended trips early. Neither was a learned decision,
yet both constrained what the learner could demonstrate.

The exact terminal exception had not been retained. Replaying the whole game
would have been an expensive way to investigate a local fault. The resulting
[North Star](../../NORTH_STAR.md) made short authenticated scenarios the normal
development loop and full runs the final exam.

## What changed—and what did not

Red became the first curriculum for a transferable player, not a route to polish
indefinitely. A teacher could demonstrate, intervene or verify, but its obedience
score was no longer enough to establish competence.

The archive contains early Crystal adapter and route probes. Those are historical
engineering explorations, not proof of learned cross-title transfer or satisfaction
of the later Red-first gate. It would be inaccurate to erase them; it would also
be inaccurate to market them as a model that had learned Crystal.

### Source trail

See the August 8–14 sections of the
[original narrative](../history/project-narrative-through-2026-09-10.md), especially
“the project stopped mistaking a final exam for practice,” the destination audit,
and the map/hazard chapters. The [North Star](../../NORTH_STAR.md) retains the
August 14 decision and the restrictions that followed it.
