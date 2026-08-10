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

## Act VI: Four guesses, one measurement

The team could now reach the right *level*. It still could not reach the right *place*.

Training happened in one late block at the Pokémon Mansion, and the Mansion is where a run goes to
get strong, not to grow up. Our own note in the repository said its wild Pokémon were level 30–32.
That note came from eight encounters. When 155 encounters were counted properly, the real band was
**28–39** — we had understated the ceiling by seven levels and could not tell, because the note
recorded no sample count.

A level-20 trainee cannot fight anything there. So it fled, thirty-three times, and gave up.

The fix is obvious once stated: send each member somewhere its own level lives. Diglett's Cave
measures 15–21 over 29 encounters, which suits a level-20 Diglett exactly. But "send it there"
means walking there, and walking there meant Fly, and Fly meant the town map.

### The map that will not answer

Every menu in this project is driven the same way: press a direction, read where the cursor went,
press again until it is where you want it. That technique had solved a dozen menus.

The town map does not participate. Five candidate memory addresses were sampled after every cursor
move, and all five were **frozen** — still holding values the previous menu had left behind. There is
no cursor to read. The screen is not a list.

So we stopped trying to steer it and started checking it instead: fly, then ask the game which town
we are standing in, and try again if it is the wrong one. A wrong fly costs a few seconds of game
time and nothing else. Two runs had ended at *"Fly to Vermilion failed"*, arriving at Viridian; the
next one flew to Vermilion, healed at the nurse, and failed two steps further along.

Nothing was ever learned about the town map's layout. Nothing needed to be.

### The menu that cost five runs

Then a party menu. To put a trainee in front you open POKéMON, pick a slot, and choose SWITCH from
its submenu. The only question is which row SWITCH is on.

We guessed four times. Each guess was checked by logic derived from the same assumption as the
guess, so nothing could contradict it, and each one cost a six-minute run to disprove:

| guess | outcome |
|---|---|
| one row past the field moves | confirmed on the wrong row |
| exactly at the field moves | changed nothing at all |
| "the menu will be as long as the party" | it is not |
| "the cursor can reach the target slot" | it can in both menus |

Five runs. Thirty minutes of emulator time, spent asking a menu the same question in four different
wrong ways.

### The suggestion that ended it

The project's owner asked why we were replaying the whole game to reach the same thirty seconds.
Why not save the emulator's state at that point and resume from there?

The answer took one afternoon to build and reduced the loop from **six minutes to one second**.

With that, the menu stopped being an argument and became an experiment. Load the state, put the
cursor on a row, press A, look at the party. Five rows, five seconds:

```
row 0   stayed in the submenu
row 1   stayed in the submenu
row 2   stayed in the submenu
row 3   opened the party list — and the party order changed
row 4   exited
```

SWITCH is row 3. Which is `field_move_count + 1` — **the formula the code had before we changed it.**

We had broken working code with a plausible theory, then spent five runs failing to disprove the
theory, because the theory and the tests came from the same place.

### And then it looked like it was working

With the swap fixed, the block ran for ten minutes without failing. Previous attempts had died in
seconds. That looks exactly like training.

It was pressing left against a rock.

The cave walk picked one direction from the player's position and kept it. Diglett's Cave winds, so
after eight tiles the player met a wall, and a blocked press is not a step — the game never rolls for
an encounter. The loop counted a step anyway. Five hundred thousand of them.

The number that separates training from spinning is the ratio of steps to battles, and nothing was
reporting it. Measured: **250 walks, one encounter, no level gained.** After pacing the tunnel and
turning at each wall: **120 walks, level 20 to 21.**

That is the whole lesson of this act, twice over. A wrong belief that nothing can contradict, and a
process that looks like work. Both survive any amount of care. Neither survives one measurement.

---

## Act VII: taking the answer key away

The teacher eventually became extremely good at Red: it could complete all 312 checkpoints, build
a six-member final-form team, defeat the Champion, and verify the Hall of Fame. But it still owned
the route. An objective model could approve the answer the fixed sequence expected without ever
choosing among genuinely executable alternatives.

So the runtime changed. It now observes the game, asks the model for an objective, resolves only a
skill that can physically run from the live state, executes that bounded skill, observes the result
again, and replans. An impossible choice cannot quietly fall back to the teacher.

From one authenticated Celadon capture, that loop first completed twelve objectives in the same
emulator process through the Mansion Secret Key. After each remaining adapter was qualified in
isolation, the full integration run started again at that same capture and continued through all 20
dispatches: the six-member development block, Blaine, Giovanni, Victory Road, the Elite Four, the
Champion, and the Hall of Fame. The fixed skills performed 502,175 mechanic actions across
37,369,283 frames. The model received no route labels, used no teacher fallbacks, required no
replans, and fresh memory observations—not the skills' own reports—closed all 36 graph objectives.

That sounds like twenty planning victories. It is not. Nineteen times only one registered skill was
physically executable. Those are useful dispatch and integration tests, but they do not measure
ranking quality. Once, both Koga and Strength were executable. The model chose Koga at 96.41%
confidence, and the run continued.

That distinction is the project in miniature: the number matters only after asking what it actually
measured.

One more number changed the direction of the work. The team-development and Blaine skill used
469,232 actions—93.44% of the entire integrated run—through 1,716 battles and 885 trips to heal.
The high-level loop is connected. The largest remaining piece of teacher authority is now visible,
bounded, and large enough to become the next learned skill.

---

## Act VIII: the cartridge becomes the guidebook

Every route in the teacher was still written as directions. Press up eleven times. Turn right four.
That can finish Red, but it cannot explain Red and transfers nothing to the next cartridge.

So the project stopped transcribing the map and read it. Red and Blue contain 220 reachable maps,
78 reciprocal edge connections, 917 ordinary warps, and 48,216 squares a player can stand on. Their
evolution data contains 70 evolving species and 72 evolution edges. Fishing resolves the apparent
Horsea/Krabby version discrepancy, and the acquisition routes parsed so far derive eleven candidate
version-exclusive species on each side rather than relying on a typed list.

The first comparison suite still managed to flatter itself. It called terrain equal by comparing
totals and Pallet Town, called map graphs equal by comparing adjacency, and would accept a four-entry
species mapping as if all 151 entries had been decoded. The hardened readers compare complete
structures. That immediately found something the summary had hidden: nine Blue tilesets store their
blocksets sixteen bytes earlier. The raw pointers differ; all 220 decoded terrain grids and every
grass/passability rule are identical. A useful test does not merely return `True`. It tells you
exactly what kind of equality you measured.

Then the generated knowledge touched the live game. The old opening teacher was allowed to do one
thing: establish a clean, verified state outside Red's house. From there, the cartridge graph chose
Oak's Lab and the terrain search produced the route. Fourteen movements followed. Live memory agreed
with all thirteen intermediate coordinates, and the final input entered the lab. No typed Pallet
path supplied those movements.

It is a small route, deliberately. The graph does not yet understand Cut, Surf, Strength, ledges,
story flags or a person standing in the road. But it is the first part of the game completed from
knowledge extracted from the game rather than from an answer key. That is the direction that can
eventually survive a different seed—and, more importantly, a different Pokémon cartridge.

---

## Act IX: the ground has rules

A passable square is not always reachable. A ledge can be crossed in one direction and not the
other. Two floor tiles can each support the player while the change in elevation between them is
forbidden. Surf changes movement mode. Cut replaces part of the map. Strength moves an object and
therefore changes the puzzle the next decision sees.

The cartridge contains those distinctions too. Red and Blue agree on eight directed ledge rules,
eleven land elevation-pair restrictions, three water-pair exceptions, nine Cut block replacements
and 25 initial boulders. Projected honestly, the static land world contains 154,653 directed edges:
153,904 ordinary walks and 749 directed coordinate ledge transitions. Another 1,152 transitions
that a flat passability grid would allow are closed by elevation rules.

The first router draft made a revealing mistake. It labeled a ledge action `hop_ledge`. That
described what the action meant and erased what the controller had to press. The fix separated
mechanism from semantics: `action="down"`, `kind="ledge"`. Every route edge now has to retain both.
That tiny distinction is the same boundary the whole project keeps rediscovering—a model can choose
an intention only if the adapter still knows how to make it real.

Route 1 supplied the live test. From the verified post-Pokédex entrance, cartridge data generated
thirteen approach inputs and selected the nearest reachable ledge. `Down` moved the player two
squares to `(28, 10)`. `Up` did nothing. The first attempt actually crossed the ledge and then
failed because the probe named the wrong retry-timing field; the corrected harness was committed,
bound to a clean source hash, and rerun from power-on. The second record passed and changed no save
artifact.

The restraint matters as much as the result. Cut, Surf and Strength were decoded but not turned into
magic permission flags. The next audit found that even ordinary multi-map routing still lacks exact
arrival geometry: warps have destination indices and border connections have alignment fields that
the first macro graph discarded. The next job is to join map-level intention to coordinate-level
action, then reobserve every step. A truthful partial player is more useful than another complete
answer key.

---

## Act X: a route that can be wrong

The completed composer produced 86 movements from Pallet Town through Route 1 and Viridian into the
Pokémon Center. That solved geometry, but it still left a dangerous question: what happens when the
world does not consume the next input?

The new executor treats each movement as a claim that live memory must confirm. It knows the exact
source map and coordinate, the requested direction, and the only map and coordinate that count as
success. It waits for input readiness, sends one request, and observes again. A wild battle becomes
a typed interruption with an authenticated escape receipt. An unchanged coordinate is retried under
a finite budget. Two unchanged attempts mark the target square unavailable and send the current
state back to the cartridge planner.

The first Mart test caught a subtler problem before producing evidence. Gen I changed the map id to
the Mart while the coordinate bytes still briefly held the old Viridian position. The executor
rejected the half-transition. The repair added one bounded transition-settling state and a synthetic
test that reproduces the staggered update.

Then two clean-source runs passed. The Center control acknowledged all 86 movements and survived
three naturally occurring wild encounters without a movement retry. For the Mart run, the harness
openly suppressed exactly two requests for the first left-hand square. That was fault injection, not
a story about an NPC. The executor marked the square unavailable and found a longer route that
entered Route 1 through a different border coordinate.

Halfway north, the real moving youngster blocked the next square. The old teacher carried a special
instruction for this exact person: step east, wait, return, then cross. The generic executor knew
none of that. It observed two failed movements, removed the occupied square, composed another route,
and continued. One wild battle later it entered Viridian Mart: 108 acknowledged steps from 112
requests, two replans, no typed corridor fallback.

This is not a learned navigator. It is the machinery that makes useful navigation learning
possible. The model should decide whether it needs healing, supplies, a capture area, or a different
objective. Exact arrows and local obstacle recovery belong to search and observation. Next come Surf
as a real movement mode, Cut as a map mutation, Strength as a moving-object puzzle, and story gates
whose availability must be proved from state.

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
-11  Blue-exclusive through the acquisition routes parsed so far
- 4  evolve only on trade
- 1  Mew, never distributed in normal play
-11  forfeited by a run's own starter, fossil, Dojo and stone choices
────
124  obtainable under that simplified accounting
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
- A trained model has selected and completed twenty consecutive objectives from an authenticated
  Celadon capture through the Hall of Fame in one portable closed loop with no expected labels,
  fallbacks, or replans. Fixed skills still execute navigation, battles, menus, and recovery; only
  one of the twenty decisions had multiple executable candidates.
- Encounter bands for five areas are measured rather than recalled, with sample counts, and they
  reproduce exactly across runs because the route is deterministic.
- Red and Blue's complete decoded map graphs, traversable terrain, fishing tables and evolution
  graphs are now measured from both cartridges. Two generated multi-map routes have entered the
  Viridian Center and Mart live while acknowledging every movement, handling four wild encounters,
  and replanning around both a disclosed artificial blocker and a naturally moving NPC. Surf, Cut,
  Strength, direct visible-object projection and story gates remain outside authority.
- A member that is too weak for where the run happens to be is now routed somewhere that suits it,
  travels there, and gains levels. That is new, and it is the mechanism the rest depends on.
- A clean-power teacher run reaches its 60/55/55/55/55/55 readiness gate and completes the game;
  the learned objective loop now reproduces the post-Celadon portion, not a clean-power route.
- The team still does not choose its own battles. The escort still does most of the fighting.
- No learned policy has completed the game. No cross-game transfer has been measured. The living
  Pokédex has not been started.

The interesting part of this project is not that software beat Pokémon Red. It is everything that
went wrong on the way to noticing that beating Pokémon Red was never the point.
