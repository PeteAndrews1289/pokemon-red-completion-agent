# Narration draft: we beat Pokémon before we taught the model to play

Edition September22,2026. Suggested narration, not a verbatim transcript of Pete
or any assistant. This is an unfinished-project retrospective, not a completion
announcement. The eight source chapters supply the factual basis for each segment.
Production time and a finished runtime have not been measured.

## Cold open — a floor tile

Our model had beaten Blaine. We had brought three reserve Pokémon up to level39.
The party was healed, the money was still there, and the next target was Giovanni.

Then a spinning floor tile stopped us.

Not a bad damage calculation. Not a new training failure. The route expected one
position, and the game delivered another. More waiting could finish the animation.
It could not make the map's prediction correct.

That is a good place to start this story, because this project has never really
been about producing one impressive battle. It is about building the player
around the battles—and being honest about which decisions belong to the model.

[Visual: labeled diagram of predicted and observed endpoints, followed by a
timeline back to July. Do not present the diagram as recorded gameplay.]

## 1 — the teacher could already finish

The completion-agent repository began in late July. First came safe emulator
control, a starter, a Pokédex, and checkpoints that could verify what the game
had actually done. The route expanded through gyms, Rocket events and the League.
The deterministic teacher reached the Hall of Fame.

That sounds like the ending. It was really the beginning.

The teacher knew a route. The eventual product was supposed to make choices:
what to catch, when to heal, when to train, which battle action to take, and how
to react when things stopped matching the example. A script finishing Red did
not demonstrate that a model could do those things.

Early learned components entered that scripted world. Some chose moves while
the teacher corrected uncertain or disagreeing predictions. Others learned
typed battle actions or authorized a fixed sequence of objectives. Those were
real steps toward control, but they were not the same as owning the whole game.

[Source: chapter1. Show authority labels beside historical completion receipts.]

## 2 — the scoreboard looked stronger than the player

A model can agree with a teacher almost all the time and still make the few
decisions that matter badly. It can also look accurate because most examples
offer only one legal action. That is not strategy; there was nothing to choose.

We found observation gaps: the teacher's answer depended on information the
model did not receive. We found training masks that did not match runtime masks.
We found evaluations where the learned policy and baseline rarely differed,
making a high score a poor answer to the question we actually cared about.

Then a long supervised run made the engineering costs visible. Fixed directions
could push against obstacles. Conservative recovery could end training trips
early. A model might be scoring decisions without controlling any of them.

The project changed its development strategy. Whole games should be final exams,
not the unit test for every local change. Short authenticated situations became
the classroom. The teacher could demonstrate and verify, but agreement with it
could not be the only definition of learning.

[Source: chapter2. Distinguish shadow prediction from executed model authority.]

## 3 — finding a question worth asking

A folder full of saved states did not automatically solve training. Several
states might come from the same origin. Some apparent choices were not executable.
Some experiments stopped before the game advanced at all.

The project built a lot of safeguards around those boundaries. Some protected
real evidence. Some sessions produced more preparation than learning. Both are
part of the history; I do not want to edit that frustration out of the story.

One battle comparison was especially useful because it did not justify continuing
in the same direction. The challenger improved over an earlier model, but a simple
legal heuristic still did better on the measured opening-action task.

Attention moved toward higher-level choices. In a bounded comparison, the learned
manager chose a team-development goal that finished. A fixed ordering chose an
evolution that did not finish within the same declared limit. That was a small,
real strategic result—not proof of an autonomous Pokémon player, but a choice
whose consequences could actually be compared.

[Source: chapter3. Keep the earlier budget-reporting failure beside the later pair.]

## 4 — the failed search still costs a ball

Collection made the dependencies impossible to ignore. The Pokémon you need may
be in storage. Its evolution may require training. It may have no useful attack.
The party still has to preserve its field moves, heal, travel and afford supplies.

The important change was continuing from the result we had earned. If a search
failed, the ball stayed spent. If the party took damage, that became the next
state. A negative outcome could become a learning example without being called
a successful capture.

The goal also changed explicitly: instead of keeping every form simultaneously,
the project would build a shared verified registration ledger across titles.
Old results kept their old definitions. A global entry would not magically add
a local Pokédex flag or create a Pokémon available for the current team.

[Source: chapter4. Show global registration, local flags and physical specimens
as separate records, not interchangeable counters.]

## 5 — money is part of playing

One acquisition attempt reached its destination, used its last Great Ball and
caught nothing. Travel had worked. The goal had still failed, and supplies had
become the immediate problem.

Pete pushed back on selling items as the default answer. Ordinary trainer income
and eventually sustainable League earnings should support play. But finishing
the League once is not the same as proving that repeated runs make money after
losses and recovery costs.

The execution layer needed scrutiny too. Seeing damage after a button press was
not enough to prove that the intended move had been selected. Tests had to check
the actual state changes and the right menu boundaries, not merely a favorable
looking result.

[Source: chapter5. Show spending and failures alongside successful goals.]

## 6 — build a classroom, then leave it

The no-cheating rule applied to the final player, not to constructing training
lessons. That distinction opened up a controlled battle classroom. The teacher
could prepare declared conditions; the model could not edit its own save.

Then another subtle problem appeared: an opening action might look good because
a strong teacher finished the rest of the fight. The deployed model had to finish
its own battle. Changing the continuation could change the lesson.

Whole-battle tests, natural encounters and larger parties followed. Some comparisons
improved. Others revealed limits. In the first ordinary funding integration,
Wartortle fainted and a no-faints guard stopped the unfinished battle. A retained
continuation later lost. We kept the blackout and the lost cash.

The fix was not to say fainting never happens. Story combat needed to handle it,
finish the fight and recover. A stricter funding test could still count that as
a failure. The game and the bookkeeping had to agree about what happened.

Flash and Claude helped with implementation and review, but their work still needed
verification. One Flash draft passed its tests even when eligibility was replaced
with an empty result. The corrected tests caught that mutation. That is a more
useful account of collaboration than declaring every outside review successful.

[Source: chapter6. No quantitative assistant-usage savings are established.]

## 7 — connect the decisions

The goal model eventually selected Lapras from a real set of alternatives and
completed the gift. A later seven-decision episode continued through failed searches
and made a successful trade. The failures and all spending stayed in the record.

A separate story experiment let the model choose Hideout or Saffron. It chose
Hideout and obtained the Silph Scope. That was a real destination choice, but
the battles and healing in that probe were still scripted. Near-even probabilities
did not prove the choice was strategically better.

This is why the project keeps asking who owns each decision. Connecting components
is progress. Giving them credit for choices they did not make is not.

[Source: chapter7. Keep the collection and earned story lineages visibly separate.]

## 8 — back to the prepared party

Stronger story opponents exposed status and attrition weaknesses. Some training
improvements failed to produce better native battles. A later additive actor won
more comparisons but used too many decisions to pass its original efficiency gate.
Pete accepted that exact actor for limited story development; the failed gate
remained in the record.

The frozen actor then won the Cinnabar gym workload. Reserve preparation brought
three teammates to39 through real battles and recovery. Those Pokémon gained XP;
that was not another fit of the model's weights.

And then we were back at the floor tile.

The shared router now represents forced-motion paths and checks their intermediate
hazards. A separate feasibility error was also caught before battle. The next
earned attempt won a gym fight in nine model decisions, despite Jolteon fainting.
Native healing restored the team and verified its recovery location.

Giovanni is still ahead. Red is not finished.

## Ending — the promise is still a player

At this edition's endpoint, the earned story has seven badges. A different
development save has109of124 declared native registrations. Neither is the
required fresh model-directed run. They cannot be stitched together into one.

The goal remains Red first, then an unfamiliar compatible modification, Crystal
and later generations. Earlier adapter experiments are not proof of that transfer.
The hoped-for paper is a possibility, not an achievement or a claim of novelty.

What we do have is a record of the decisions, failures and corrections that brought
us here. The next chapter should continue that record—not replace the earlier
history with another page saying only where we stopped today.

[End card: current result / remaining blocker / next bounded test.
Link the chronicle, evidence map and current handoff.]
