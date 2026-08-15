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

## Current checkpoint: choosing a move still matters when the move never happens

The first eight-battle curve reached the cartridge only after its exact source passed GitHub. All
eight assigned roots produced distinct battle captures, and all four moves were available in every
one. Then the run stopped before training.

One development choice had been real, but the move was suppressed by Pokémon's own mechanics
before it spent PP. The old target code threw the entire result away. That revealed a subtle but
important mistake: the model's job is to choose an action, not to guarantee that the game lets the
action execute. Sleep, paralysis, Disable, trapping, recoil and Selfdestruct are part of the world.
The damage and terminal state after choosing a move are still its observed action value. They are
not a teacher label, and they should not disappear because `move_executed` is false.

The failed attempt trained nothing and promoted nothing. It also caught an evidence bug: the runner
did not open its private journal until after every battle had been measured, so the candidate that
stopped the run was not durably recorded. The next version writes each branch before trying the
next. The four exposed development battles are retired, four fresh ones were frozen before anyone
looked at an encounter, and the same tiny curve will be tried again before the project scales.

That is the research loop this project needed: the game contradicted the experiment, the result was
kept as a failure, and the abstraction became more like the thing a Pokémon player actually has to
learn.

## Current checkpoint: three different lessons, one honest report card

The first battle lesson exposed the next architectural trap. Its record called itself
“title-neutral,” but it still required move PP, damage and faint fields. Navigation does not deal
damage. Party training does not have a move slot. Forcing them into that record would have produced
one schema only by lying about what the games measured.

The new boundary shares only what the learner genuinely needs: an identity-free candidate menu and
an independently verified ordering of outcomes. Battle keeps damage and survival. Navigation keeps
arrival, progress, collisions and route effort. Party development keeps experience, battles,
Center visits, evolutions, faints and blackouts. Interrupted evidence stays censored, equal outcomes
stay tied, and a result attached to the wrong candidate is rejected. Experience must reach the
chosen trainee; letting the overlevelled escort take it does not earn credit.

The first follow-up experiment is intentionally tiny and exact: four Red training battles, four
untouched development battles, and three models fitted from the same prior with one, two and four
contexts. It cannot prove battle competence. It can cheaply show whether adding a few independent
lessons bends the curve in the right direction—or makes the failure worse—before the project pays
for hundreds. Only after that result and one real navigation and party lesson does collection grow.

## Current checkpoint: the first lesson made the model worse

The new development loop finally did what the old full-game loop could not. It restored two real,
authenticated Red battles and tried every legal move from exactly the same moment. The teacher did
not vote. The game answered: damage, faint, survival and cost. Eight move outcomes arrived in two
seconds instead of another overnight playthrough.

The first attempt failed before a move. A safety check still assumed every bounded battle was a
trainer battle, so it rejected the real wild encounter. That bug had survived thousands of tests
because no test had asked the new one-turn executor to begin from a truthful wild state. The failed
attempt wrote no model. The check was repaired, a real-wild regression was added, and the exact
published commit passed again.

Then the learner updated. Its training loss nearly halved. If this project were still optimizing
pretty training numbers, that would have been the headline.

The untouched battle gave the opposite answer. The old model chose one of three moves that knocked
out the opponent. The updated model chose the only move that did not. Development went from one out
of one to zero out of one. The candidate was rejected automatically and received no authority.

That is the first real model-first success: not that the model improved, but that the system could
teach from the game and still refuse a worse lesson. The next step is deliberately not a huge Red
battle matrix: collect the smallest set that can draw one learning curve, prove one navigation and
one party-development outcome fit the same abstraction, and only then scale. Full Red remains a
final exam; living-Pokédex rollout resumes after battle authority survives its unseen gate.

## Current checkpoint: stop replaying the answer key

The four learned pieces did enter one visible Red run, and the run failed in the most useful way it
could: it made the project's strategic mistake impossible to ignore.

After 1,250 training battles and more than 85 million observed frames, the party was still in
Cinnabar at levels `(42, 43, 43, 55, 42, 42)`. The battle model had disagreed with the teacher 600
times. The team model had almost perfectly predicted hundreds of thousands of candidate rankings,
but the teacher still acted. Navigation still followed fixed arrows, visibly pressing against
Saffron walls until a retry registered. The recovery policy treated ten percent damage as a reason
to visit a Center.

That was not a model learning to play Pokémon. It was a model being examined inside a teacher's
walkthrough—and using the entire game as the test harness made every local lesson painfully slow.

So the project changed its unit of progress. It will restore authenticated development situations,
randomize what matters, let the model act, permit bounded teacher intervention, and judge outcomes.
Navigation is measured by arrival and collisions. Battles are measured by winning, damage, turns
and resources. Training is measured by experience per frame and battles per heal. Goals are real
only when the model has alternatives. Collection is organized around a living-Pokédex dependency
plan. Crystal becomes an early test of whether shared skills transfer, not the next scripted route.

Full games are now final exams. The daily work happens in scenarios short enough to fail, learn and
retry hundreds of times.

## Historical checkpoint: four learned pieces entered one visible Red run

Red now has four freshly fitted decision-makers: what kind of work to pursue, which strategic
destination to choose, which battle move to use, and which teammate/venue to develop. They learned
from different genuine teacher datasets because those are different decisions. Their held-out Red
scores range from 83.33% for the tiny five-weight destination model to more than 98% for battle and
team development. Those are real models. They are not yet one autonomous player.

The first full-game evaluation makes the gap visible. The battle model proposes a move while the
teacher checks it. Agreement allows that proposal through; disagreement or low confidence uses the
teacher move and preserves a correction. The team model predicts without controlling the training
route. The goal and destination models wait offline until the hierarchy can offer them real choices.
The live dashboard labels each boundary beside the game and keeps Crystal sealed for the eventual
transfer test.

That is the current meaning of “training Red”: fit reusable decisions, expose them to the entire
game, keep the teacher where evidence still requires it, and turn every disagreement into the next
lesson. A Hall-of-Fame result from this run will be a supervised compatibility result, not a claim
that the model independently solved Red.

## Earlier checkpoint: the catalog recognized the same lesson twice

The first curriculum board now holds 81 authenticated Red situations: nine examples for each of
nine kinds of work, split into 54 training and 27 development-validation choices. All 81 passed a
read-only inspection, all protected fingerprints are unique, 28 training choices have at least
three real options, and the correct answer appears in every shuffled position. Three identical
menus even change their answer when the cartridge state changes—the difference between memorizing
a menu and responding to a situation.

The board was then inspected against one published, green commit and locked. Five real story
lessons completed. The sixth defeated a mandatory trainer, returned to Lavender Center and failed
inside the longer route. Its setup had discarded the last Poké Ball, but the menu check looked only
for the Poké Flute; the missing prerequisite was discovered only when the executor tried to fund
the Snorlax capture. The check now happens before the choice is offered. The episode stayed failed:
its identity was not retried, its selected choice did not become an imitation target, and no model
was fitted.

That failure found the missing rung between looking at a menu and safely spending a one-shot
lesson. Every exact frozen card must now complete a full rehearsal with no recorder attached. Only
after all 81 mechanics execute and independently verify may a fresh campaign begin. The old pilot
remains **5 successful, 1 failed, 0 models**—a small scoreboard that says more than another large
green test count.

The replacement kept its ball and sold an obsolete TM through the real shop. All 81 new inspections
passed, yet the catalog refused to lock: the fifth and sixth states had the same strategic evidence.
Money and an obsolete item made the saves different without making the lesson different. The next
replacement consumes a real Rare Candy on the fully evolved lead, creating a one-level change the
manager can actually observe. Its setup proves the exact item, level, party, health, move, money,
story and location ledger. The uniqueness rule did not move.

That replacement catalog froze, and its first six story cards completed a full rehearsal. The
seventh found two more truths. A shopper in Celadon Mart swallowed an open-loop stair input, so the
route adopted the collision-aware movement already used elsewhere in the building. Once inside
Silph, the level-39 three-member party lost with 20 HP left on the opponent. Its own Rare Candy
raised the lead to 40, after which the whole chapter completed and returned fully healed. The card
was not “close enough”; the catalog is rebuilt from the stronger state.

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

## Act XI: the shoreline changed the state space

Water is not another blue floor tile. On land, stepping into it is illegal. With the Soul Badge and
a living party member that knows Surf, the same edge becomes a menu action that changes how every
later coordinate is interpreted. Leaving the water changes it back. A planner that stores only
`(y,x)` cannot tell those worlds apart.

The route graph now stores `(coordinate, mode)`. Boarding is a typed field action from land to
water. Water travel stays in water. Disembarking returns to land. The Red adapter reads the badge,
the entire party, the living move holder and `wWalkBikeSurfState`, then uses the real menu. The
neutral executor still sees only an action and the exact state that must acknowledge it.

The cartridge was again more useful than the code's confidence. The first probe exposed a race:
after a direction press, Red could still publish the source coordinate while its walk animation was
in flight. Blocker discovery ran before the settling wait and declared the destination unavailable.
The order is now action, bounded settle, exact reobservation, and only then blocker inference.

The second probe reached the bottom of Cinnabar Center and contradicted the router's warp model. The
ROM says the return warp is at `(7,3)`, but entering that square is not the transition. The player
stands there and presses Down again, arriving outside at `(12,11)`, one square beyond the exterior
door record. The third probe showed one-frame direction taps can repeatedly miss Red's joypad poll
when the retry interval keeps the same phase. The final route uses the longer controller timing
already proved by the rest of the teacher.

Then the round trip passed. From an authenticated post-Blaine state, cartridge search exited the
Center, selected a target that required two real water-travel edges, boarded at `(13,11)`, reached
`(16,11)`, disembarked and returned to the exact `(12,11)` origin in land mode. Thirteen planned
steps, thirteen live acknowledgements, no wild battle, no replan, no leaked or modified private
artifact.

This is the kind of structure that can transfer. The learned layer can decide that a water route
serves healing, capture or exploration. It does not need to rediscover how a particular cartridge
stores shore collisions or which menu row means Surf.

---

## Act XII: look before you walk

The first closed-loop route recovered from people by pressing into them twice. That was honest—the
game did refuse the inputs—but it was still reactive in the clumsiest possible way. The cartridge
already knew which non-player sprites were rendered and where they stood.

The new adapter reads that live overlay. The neutral executor checks it before an ordinary walk and
asks for a replacement route without pressing toward an occupied square. It also forgets the
constraint when the object leaves; a moving person is not promoted into permanent terrain. Failed
steps remain the bounded fallback beyond the visible window.

The proof deliberately denied the planner Red's initial object positions. ROM data selected a
stationary Cinnabar NPC at `(6,14)` and a goal at `(6,13)` whose preferred route crossed the NPC,
but it did not mark the square blocked. From `(6,15)`, live RAM exposed the person. The last Left
input disappeared before it was sent, a four-step suffix went around, and the route returned to its
exact shore origin. Forty-three requests, forty-three acknowledged movements, one replan caused by
perception rather than collision.

A map says where someone started. Perception says where they are. The next honest gaps are Cut's
map mutation, Strength's pushed-object state and story gates that change whether the same passage
exists.

---

## Act XIII: the tree had to disappear twice

Once in cartridge data, where block `$35` predicts replacement `$4C`. Once again in the live game,
where the prediction has no authority until RAM actually changes.

That distinction reshaped Cut. The planner reaches a stance and stops. The field adapter proves a
living holder and badge, navigates the menus, keeps the player still, and accepts only one exact
block mutation with control restored. Then the old path is thrown away. Terrain is rebuilt from the
active map buffer and a new route is allowed to cross.

Celadon made the contract visible: `(20,47)` was solid, block `$35` became `$4C`, tile `$3D` became
`$2C`, and only then did the next plan step onto the former tree and continue east. Sixty route
movements were acknowledged around the full Center round trip; not one was justified by merely
owning HM01.

The system did not learn where Celadon's tree is. It learned where responsibility belongs: strategy
chooses what to open, the adapter performs the title-specific mechanic, and observation decides
whether the world changed. Strength is the next test because both sides of that transition move.

---

## Act XIV: the floor stayed open while the world said no

Route 7's guard house is five walkable tiles from west to east in every static read. Before the
guard receives a drink, those tiles are not a route. The obstacle is not collision and the map does
not mutate. It is a story fact.

The neutral graph now attaches opaque requirements to exact directed edges. Red's adapter observes
the Saffron guard bit as satisfied, unsatisfied or unknown, and publishes only satisfied facts as
capabilities. That last distinction is the safety rule: missing memory cannot become optimistic
permission.

The proof watched the same passage change meaning without changing topology. With Fresh Water still
in the bag and status byte `$00`, an ordinary graph found five Right inputs while the semantic graph
rejected them and sent nothing. After the teacher gave the drink away, RAM became `$40`. Generated
routes crossed back west, forward east, exited the gate and entered Saffron: eleven requests,
eleven acknowledgements, no replan.

The first attempt failed one step later. The composer expected the horizontal gate to use the same
one-tile exterior walk-out as a Pokémon Center door. Live RAM settled on the Route 7 warp instead.
That failure was kept long enough to correct the abstraction, then the proof was rerun from clean
committed source. A story about intelligence that hides the emulator's veto would be less valuable
than the bug.

This is one predicate, not a universal story interpreter. The next route must manage something that
depletes while it moves: Repel. That requires renewal to become planner state rather than another
authored preamble.

---

## Act XV: the path paid for its own protection

Victory Road still had three invisible cheats: two copied strings between floors and a third walk
whose only purpose was to make Repel expire where the script expected. The boulders were planned,
but the journey connecting them was not.

The route now observes Repel like any other finite resource. Active means continue. Unknown means
stop. Zero plus a carried renewal means settle the prompt, consume exactly one item, prove the new
counter and unchanged player/party, then resume. The same receipt works inside ordinary walking and
inside Strength search; the puzzle does not get a weaker inventory rule just because its protection
ran out.

The cartridge composed both missing room changes: 51 steps from 1F to 2F and 56 from 2F to 3F,
each through an exact warp, every movement acknowledged. Trainer sight changed the first suffix once
without causing a battle. With the 14-step expiry walk deleted, the final Max Repel reached zero
naturally at 3F `(1,9)`. One confirmation, one item, 250 restored steps, same search.

That changed the headline. The five puzzle plans now take 267 steps and 65 pushes/drop receipts.
The third search explores 54,305 states because it starts at the real 3F arrival rather than after a
hand-selected head start. The larger number is the more transferable result.

The route to Indigo after the final switch is still teacher-authored. This is not full generated
completion; it is one more removed answer key and one more mechanic represented as observable state.

---

## Act XVI: the sealed test almost measured the wrong thing

Thirty-six genuine destination choices finally made a small learned scorer possible: 24 for
training and 12 for development validation. The first neural model was rejected because roughly 753
parameters were too many for 24 examples. A five-coefficient linear ranker, selected using training
alone, then scored 10/12 on development validation while cheapest route scored 4/12.

That was when the dangerous button appeared: run the final test.

The review found four reasons not to press it. The original test guaranteed no cases where cheapest
route should be wrong. The first replacement mixed two baseline-friendly safety cases into the
primary statistic. Then the cartridge adapter assumed ten challenge snapshots had somehow already
moved from their authenticated source city to the city where the challenge was supposed to be
asked. Finally, the plan named audit and live-qualification gates without requiring their exact
receipts at runtime, and its validated objects could be copied with a hidden constructor token.

All four were repaired while the sealed counter stayed at zero. The current protocol binds the
audit and non-test qualification evidence into authorization and preflight, then claims a case
before access, authenticates the source save, relocates without creating a training label, rejects
any change to completed story objectives, and only then shows identity-free route structure to the
model. Predictions are committed before the teacher acts; no result or p-value is exposed until all
twelve cases are consumed; a crash burns its case rather than creating a convenient rerun. The
private root cannot hide behind a symlink, validated authority objects cannot be cloned, and the
ledger cannot start without a cleanup boundary for a prepared emulator.

The important result is still not a score. It is **0/12 opened**. The system became more capable of
being wrong honestly before it was allowed to make a final claim.

---

## Act XVII: the rehearsal that failed before the ocean

The first live qualification looked persuasive. From a public validation capture, the production
adapter authenticated Celadon, relocated to Saffron, planned every candidate, closed without asking
the teacher and changed nothing on disk. Its exact source passed CI. The typed receipt said what it
had proved.

Then the reviewer asked a better question: had it proved the route the sealed test would actually
need? Two cases begin in Saffron and ask the model about Cinnabar. That means a journey through the
sea, and the successful rehearsal had never touched Surf.

The substitute was a train capture, not a peek at test. It started in Saffron with Cinnabar already
authenticated by its completed story frontier. The run did not even reach the water. At the north
gate of Viridian Forest, the map decoder said the destination warp was `(0,5)`. The cartridge said
the player had finished the doorway animation at `(1,5)`. One tile was enough to stop the entire
route.

That mismatch already existed elsewhere in the system. A return edge through a south-facing door
had taught the planner that the animation walks one square beyond the exterior warp. The code had
mistaken the edge label—`return`—for the mechanic. Route 2 used an ordinary directional warp, but
the cartridge played the same doorway step. The repair moved the rule to the behavior it describes.

The failed qualification also exposed a reporting flaw. It closed safely, but the command left only
a traceback unless someone manually preserved the observation. The next version writes evidence
for failure as deliberately as for success: a typed negative receipt, no private path, no teacher,
zero test access, unchanged capture, and a nonzero exit that automation cannot mistake for green.

That first correction was still only a hypothesis. Published v8 failed safely on the same public
route. The next observation separated two doors that looked identical from the source: Route 2
lands on an automatic trigger and plays the extra inward step; Route 6 lands on a directional return
and stops on it. After that distinction, Viridian Forest's bottom gate revealed its missing second
`down`. After *that*, Surf finally worked—but the planner chose Route 21's cheapest source column
without asking whether the paired Cinnabar square was water, land or even present.

The durable lesson was larger than any one coordinate: crossing a boundary is a relation between
two executable local states. Schema v9 checks the destination trigger for doorway animation,
lets the cartridge's automatic-warp table override geometry, and refuses a map connection whose
arrival cannot continue in the current movement mode.

Then the same public train capture crossed Kanto. The route completed 550 acknowledged steps through
nine wild interruptions with no replan, came ashore on Cinnabar in land mode, and planned both
candidate destinations. No teacher ran. No source artifact changed. No typed success receipt was
created from unpublished code.

The seal still reads **0/12**. The most valuable result was not merely that the agent crossed Kanto.
It was that three cheap public failures prevented two expensive one-shot failures from being blamed
on the model—and that every failed version stayed failed in the record.

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
  and replanning around both a disclosed artificial blocker and a naturally moving NPC. A third
  generated route has boarded, traversed and exited Surf from observed movement mode, then returned
  to its exact shore origin. A fourth generated route directly observed a Cinnabar NPC, replanned
  before sending an input into its occupied square, and returned to its origin. A fifth staged Cut,
  verified one exact Celadon block mutation, rebuilt terrain from live RAM, crossed the former tree,
  and returned to Center. Five bounded searches then solved Victory Road's full Strength chain, and
  a trainer-sight proof replanned before engagement. One observed Route 7 story predicate now keeps
  closed and unknown Saffron states unavailable, then admits the same corridor after the live flag
  opens. Both open Victory Road room transitions are now composed, and Repel renewed from observed
  zero inside Strength without an authored expiry walk. Repeated Cut, other story scripts, the
  post-final-switch Indigo route and general generated routing remain outside completion-run
  authority.
- A member that is too weak for where the run happens to be is now routed somewhere that suits it,
  travels there, and gains levels. That is new, and it is the mechanism the rest depends on.
- A clean-power teacher run reaches its 60/55/55/55/55/55 readiness gate and completes the game;
  the learned objective loop now reproduces the post-Celadon portion, not a clean-power route.
- A five-coefficient strategic destination ranker was selected on 24 training choices and scored
  10/12 on 12 development choices versus 4/12 for cheapest route. This is development evidence.
  Its one-shot 12-case final test remains unopened at 0/12. One live Celadon-to-Saffron adapter
  qualification passed; the harder public Saffron-to-Cinnabar route then exposed destination-
  trigger, bottom-gate and cross-map-arrival defects. The repaired v9 public rehearsal reaches
  Cinnabar and plans both candidates. Published v9 qualification, independent authorization audit,
  the real path-free catalog and owner authorization remain.
- A broader game-neutral goal manager now ranks nine kinds of work—story, acquisition, team
  development, evolution, restoration, resupply, storage, recovery, and exploration. All nine have
  real bounded Red bindings, and an 81-context train/development protocol is implemented through
  authenticated preflight, record-before-action collection, strict reload, and train-only fitting.
  Acquisition has passed authenticated preflight; resupply, transient-control recovery, field
  restoration and Center restoration have executed successfully without consuming episodes. The
  two restoration contexts began at 66.67% safety pressure and ended fully healed, status-free and
  stable. Evolution then passed a genuine three-way preflight and changed Diglett level 22 into
  Dugtrio level 26, but an unrelated catalog aggregate falsely rejected the success. The repaired
  verifier checks that exact transformation. Published-source replay then changed Diglett level 22
  into Dugtrio level 26 in 21,604 actions and passed with zero faints, stable control and no episode,
  even as the honest catalog aggregate remained 3/22. The manager still has **zero genuine examples
  and no trained artifact**. That distinction is deliberate: authenticated rehearsal evidence is
  not training data.
- The team still does not choose its own battles. The escort still does most of the fighting.
- No learned policy has completed the game. No cross-game transfer has been measured. The living
  Pokédex has not been started.

The interesting part of this project is not that software beat Pokémon Red. It is everything that
went wrong on the way to noticing that beating Pokémon Red was never the point.
