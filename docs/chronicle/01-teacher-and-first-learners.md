# 1. July 28–August 5: build a teacher, then let the learner act

[Chronicle contents](README.md) · [Next chapter](02-evaluation-and-refocus.md)

## The first problem was making completion observable

The successor repository begins on July 28, 2026. Its early history is practical:
connect PyBoy safely, start the game, obtain a starter and Pokédex, then verify
Brock and restored overworld control. Subsequent commits move through the familiar
towns, HMs, Rocket events and gyms. By July 30 the history records a deterministic
teacher reaching the Hall of Fame.

That accomplishment mattered. The project needed working observations, controller
inputs and a way to distinguish apparent victory from actual completion.
But it answered a smaller question than Pete's eventual goal. Code could execute a
known route; a model had not learned to decide how to play it.

The distinction is preserved in the sources. The early
[Hall-of-Fame receipt](../evidence/qualified-play-hall-of-fame-2026-07-29.json)
is named for July 29; the completion commit is dated July 30. A receipt filename and
commit date are not interchangeable timestamps. This chapter does not collapse them.

## Learning began inside the teacher's game

The August 5 archive describes an initial assisted run in which a model proposed
battle moves while the teacher retained uncertainty and disagreement authority.
It reports 537 of 707 decisions handled by the model and labels the result
model-assisted, with scripted navigation still in control.

Later correction collection produced 126 examples. A correction-trained model
reduced a subsequent run's interventions to 84. Another retrain was rejected after
worse validation and 92 interventions. Even at this early stage, “newer model”
did not automatically mean “better model.”

The point was not simply the agreement percentage. Turning corrections into
retained examples created a repeatable observe–choose–measure–fit loop.
It also revealed how much of the game the action interface was withholding.

When the teacher's correction gate was removed, a Cerulean rival battle exposed
a fainting failure. A move-only learner could not request all the recovery or
switching behavior the teacher had supplied. Training the move scorer harder
could not add actions that did not exist in its menu.

A later attempt cleared more battles but arrived short of the route's supply
reserve. Combat efficiency and future money requirements were already coupled:
winning the current fight did not guarantee that the remaining route was affordable.

## From choosing a move to controlling a battle

The work expanded toward typed actions: attack, recover, boost and switch.
Target resolution mattered as much as action classification. A healing action
needed a legal item and recipient; a switch could serve different tactical roles.
Generic “choose the healthiest teammate” logic did not reproduce all those roles.

The archive records successive boundaries: shadow predictions, live execution,
teacher-free item/party target resolution, and model authorization of story
objectives. The
[objective-authorized completion](../evidence/model-authorized-objective-hall-of-fame-2026-08-05.json)
reports 36 objective boundaries and 312 checkpoints through Champion and Hall of Fame.

Its own limitation is central to this history: the route still supplied the
objective sequence, and the model largely confirmed or rejected it. That is a
real control boundary, but not free strategic planning.

Similarly, the
[typed battle-control record](../evidence/teacher-free-battle-control-hall-of-fame-2026-08-05.json)
belongs to a declared controller and route configuration. It cannot be reused as
proof that today's final fresh-start player is complete.

## What survived this phase

The project acquired a functioning teacher, native verification, learned components
and explicit authority boundaries. It also acquired the recurring temptation to
describe a whole game's completion as if every important decision belonged to the
learner.

The next phase challenged that interpretation. Agreement and route completion
were useful tools, but the product needed useful choices in changed situations.

### Source trail and caution

The July chronology is anchored in commits `6bece52a`, `f0a0d8c6` and
`14222cdc`, plus the dated native receipts. The detailed August account survives
under the August 5 headings in the
[archived project narrative](../history/project-narrative-through-2026-09-10.md).
Some archived summaries use overlapping action categories; this reconstruction
does not add their counts or invent a reconciled total.
