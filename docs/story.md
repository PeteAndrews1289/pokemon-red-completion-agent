# The story: teaching a model to actually play Pokémon

A narrative account of this project, written for an audience rather than for a compiler. The
engineering record lives in [project-narrative.md](project-narrative.md); this is the arc.

Every number here is real and traceable to a receipt in `docs/evidence/`.

---

## The premise

Beating Pokémon Red with software is a solved problem. People have done it with scripts, with
reinforcement learning, with hardcoded button sequences. This project can do it too — repeatedly,
from a clean power-on, with the Champion defeated and the Hall of Fame verified in the same run.

That result turned out to be almost worthless, and finding out why is the story.

The question underneath is different from "can software finish this game?" It is: **can a system
learn to *play* Pokémon** — make real choices, adapt when things differ from what it was taught, and
carry that competence into a game it has never seen?

The goal we settled on is deliberately larger than any single game: **a living Pokédex spread across
every mainline title.** One accumulating collection, filled by however many runs, versions and trades
it takes. Ideally 100% completion of each game along the way.

That target was not chosen for ambition. It was chosen because it is the only one that forces the
system to actually play.

---

## Act I: The run that wins and teaches nothing

The teacher completes Red. 312 checkpoints, 36 objectives, 74 scheduled battles, Champion, Hall of
Fame. On paper it looks finished.

Then we looked at *how* it wins.

The final battle against the Champion — six Pokémon, levels 59 to 65, the hardest fight in the game —
lasted **six turns. One per opponent.** A single level-87 Blastoise one-shot the entire team. The
other five party members never entered the battle.

Every decision recorded in that fight was "use the strongest move." It was always correct. For a
model learning from these demonstrations, there is nothing there. No type reasoning, no switching, no
resource management, no risk. Just a hammer meeting six nails.

This is the central insight of the project: **completing the game and playing the game are different
problems, and optimizing the first actively degrades your data for the second.**

Making the route *more reliable* would only have produced more of the same emptiness.

---

## Act II: The metric that told everyone what they wanted to hear

Before we could fix the team, we had to notice it was broken — and for five evaluation versions,
nothing did.

Every run produced a receipt recording `final_party_levels`. Across twelve committed receipts,
spanning five different repairs and twelve different random seeds, that field read:

```
[61, 59, 61, 61, 63, 65]
```

Identical. Every time. A perfectly trained, perfectly balanced six-member team.

Twelve independent runs cannot produce identical party levels. A *fixed opponent* always will. Those
were the **Champion's** levels, recorded as our own. Our real party levels had never been captured at
all.

When we finally measured them:

```
Ours:      [68, 20, 26, 30, 25, 30]     spread 48
Claimed:   [61, 59, 61, 61, 63, 65]
```

One carry at level 68, and five Pokémon between 20 and 30 who walked into the Elite Four as cargo.

The lesson is not "there was a bug." It is *why it survived*. The number looked exactly like what
everyone hoped for, so nobody checked it. The project's evidence discipline was genuinely good —
immutable receipts, sealed evaluation seeds, one-attempt accounting — and it still shipped a metric
that could not embarrass anyone.

**Prefer measurements that can come back wrong.**

---

## Act III: The training code that was never called

So why weren't the five members trained? The code to do it existed. It was written, tested, and
configured with a level floor, a spread ceiling, and a 7,000-battle budget.

It had two modes. One evolved a specific Pokémon and stopped the moment that species appeared. The
other ran the real balancing loop and *raised an error* if it stopped before the team was ready.

There was exactly one call site, and it passed the evolution mode.

The balancing pass — the level floor, the spread ceiling, the budget, the readiness enforcement that
everyone assumed was protecting them — **had never executed once.** Twenty-seven battles satisfied
the block, because twenty-seven battles was all the evolution took.

Nothing complained, because the verification gate downstream checked only that the roster was
complete and that *one* designated workhorse had reached its level. Five of six members were outside
what any check looked at.

---

## Act IV: Fixing it wrong, then fixing it right

We called the balancing pass. It worked — spectacularly, and in the wrong direction.

The team trained from ~25 all the way to **79**, at a cost of 4,570 battles and 1,063 healing trips,
about an hour of emulator time against a 6-minute baseline.

Against an Elite Four that tops out at 65.

We had replaced one overleveled Pokémon with six. Same absence of decisions, eight times the cost.

The bug was subtle and worth understanding: the rule said "keep the party within five levels of each
other," measured *inside the party*. One member — the escort — was at 84. So the rule dragged
everyone up to 79 to satisfy it. Nothing in that computation ever looked at what the team was
actually fighting.

The fix was to make the target relative to the game instead of to itself:

> Stay within N levels of the opposition you are actually facing.

That single sentence is a reusable Pokémon concept. `minimum_level = 50` is a Red-specific magic
number that means nothing in a game whose league sits at 70 and over-trains one that tops out at 30.
"Near what you face" transfers unchanged, and it self-paces — a party measured against a rising
difficulty curve trains as that curve rises.

Re-run with the target derived from the League: the team arrived at **55**, in **1,878 battles**.
Two and a half times cheaper, and *under* the opposition rather than nineteen levels over it — which
is exactly where a normal human playthrough lands.

---

## Act V: And it still doesn't play

The team was now balanced. The run still finished the game the same way: the escort, now at 87,
one-shotting the Champion's six Pokémon in six turns while five level-55 Pokémon watched.

The mechanism that trains a weak member sends it into battle beside a strong escort so both earn
experience. But the escort earns experience from *every one of those battles too*. Training the team
pushes the escort further ahead. The harder you balance, the wider the gap gets.

**Balanced levels and a participating team are different things, and we had only fixed the first.**

That is where the work currently stands, and it is a better place to be stuck than where it started —
because the failure is now visible, measured, and specific, rather than hidden behind a metric
reporting somebody else's Pokémon.

---

## Why a living Pokédex

Every failure in this story has the same shape: a fixed sequence standing in where a decision should
be. A walk string that breaks when a wild encounter costs a step. A scripted party pivot that creates
the emergency it then recovers from. A level target anchored to your own strongest member instead of
your opponent.

You cannot script your way to a complete Pokédex. It needs encounter tables, all four kinds of
evolution, capture judgment, storage management, trading, version differences, and every area a
speedrun deliberately skips. The dex is not a stretch goal bolted onto a completion project — it is
the constraint that makes the system learn to play.

And it does not fit on one cartridge. The arithmetic is unforgiving:

```
151  species in the generation
-10  Blue-exclusive, unreachable in Red
- 4  evolve only on trade
- 1  Mew, never distributed in normal play
-11  forfeited by a run's own starter, fossil, Dojo and stone choices
────
125  actually obtainable in one Red run
```

Two Red runs taking opposite branches reach 132. Three are needed just for the starters and the Eevee
stones. Then Blue for its exclusives, and trading for the four evolutions that require it. Mew waits
for a later title that actually features it.

So the target is a *collection*, filled across runs and versions and generations — which is precisely
why it teaches transfer. Choosing which branch the next run should take, to cover what the collection
still lacks, is itself a real decision with a measurable payoff. "Take Charmander this time because
we already have Squirtle" is reasoning that carries into any game. "Walk 47 tiles left" is not.

---

## What is actually true right now

Being precise about this matters more than the story sounding finished.

- The deterministic teacher completes Pokémon Red repeatedly, with genuine Champion and
  Hall-of-Fame evidence in the same run.
- A trained model authorizes all 36 objectives with zero fallbacks — but fixed code executes them.
  It selects objectives; it does not yet play.
- The team can now be trained to League parity at a measured cost.
- The team still does not participate in battles. The escort does everything.
- No learned policy has completed the game. No cross-game transfer has been measured. The living
  Pokédex has not been started.

The interesting part of this project is not that software beat Pokémon Red. It is everything that
went wrong on the way to noticing that beating Pokémon Red was never the point.
