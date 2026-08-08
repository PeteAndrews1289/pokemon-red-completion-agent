# YouTube narrative: teaching a model to actually play Pokémon

## Working title

**I Taught an AI to Beat Pokémon Red — Then Discovered It Had Learned Almost Nothing**

Alternatives:

- **My AI Beat Pokémon Red. That Was the Easy Part.**
- **Beating Pokémon Wasn't Enough: Building an AI That Can Transfer**

## One-sentence promise

Follow an evidence-driven attempt to turn a reliable Pokémon Red speed-running teacher into a
learned player that can make decisions, recover from surprises, and eventually transfer what it
learns to other Pokémon games.

## Story outline

### Cold open — 0:00–0:35

Show the first complete League participation vector: `[49, 0, 0, 0, 0, 0]`. The system wins, but
one overpowered Pokémon makes every meaningful decision while five teammates watch.

Narration: *“The run was successful. As training data, it was almost useless.”*

Immediately contrast that with the later `[24, 0, 4, 0, 5, 1]` run and ask the central question:
did the AI learn Pokémon, or did we write a very elaborate answer key?

### Act I: making completion measurable — 0:35–2:00

Explain why “it beat the game” is not enough. Show clean power-on, no save-state restore, the
independent referee, 312 semantic checkpoints, 36 objectives, Champion, and Hall of Fame. Introduce
the separation between actor and referee and the practice of preserving failed runs instead of
rerunning a favorable seed.

### Act II: the trap hidden inside a successful run — 2:00–3:25

The original teacher optimized for reliable completion. That naturally produced a single-carry
strategy: train the strongest Pokémon, use its strongest attack, and minimize everything that can
go wrong. It is sensible engineering for a completion script and poor curriculum design for a
general player.

Core lesson: **completion reliability and teaching quality are different objectives.**

### Act III: letting the measurements embarrass us — 3:25–5:05

Show how the project evolved from green checks to falsifiable claims. Include the participation
metric that initially checked the wrong scope and receipts that reported opponent levels instead of
the player's team. Explain the workflow that followed: make a prediction, capture the right state,
run the experiment, preserve the failure, and add the reading that would have explained it sooner.

This is where failed attempts become the story rather than footage to hide.

### Act IV: turning six passengers into a team — 5:05–7:00

Show the balanced-team curriculum: a six-member final-form roster, a level-60 workhorse, targeted
evolution training, and real League jobs. Jolteon handles Lorelei's Water core and Agatha's Golbat;
Hitmonlee attacks Bruno's opening Onix; Dugtrio handles Agatha's grounded threats. The vector moves
from `[49, 0, 0, 0, 0, 0]` to `[24, 0, 4, 0, 5, 1]`.

Be explicit: this is a better **teacher-authored demonstration**, not proof that a model invented
team strategy.

### Act V: what actually learned — 7:00–8:35

Present the real learned components without inflating them. A nonlinear battle ranker completed the
scripted Red route and made most reported move decisions without move fallback. A semantic
objective ranker authorized all 36 expected objectives. Then show the boundary: fixed code still
chooses the next chapter, invokes the specialist, navigates menus, manages resources, and recovers.

The objective model was checking an expected answer, not yet deciding what to do next in an open
loop.

### Act VI: the architecture pivot — 8:35–10:10

Introduce the new player loop:

```text
observe → choose objective → choose skill → issue typed action → observe result → replan
```

The deterministic code remains valuable as expert demonstrations, bounded tools, and an independent
referee. It stops being the hidden decision-maker. A strict evaluation lane fails on any teacher
query, fallback, unsupported action, or undeclared safety substitution.

Implementation checkpoint: the game-neutral loop and no-answer-label objective-selection interface
now exist, and the first Red chapter is connected through a typed bounded-skill registry. Most of
Red's chapter runner is still fixed, so show this as one transferred decision—not autonomous
completion.

Useful visual: show the exhaustive planner audit as 166 reachable quest states, highlight the 129
branch points, then split the 317 candidate-local evaluations into 237 matching selections and 80
misses. Explain that sensitivity is encouraging but is not the same as knowing the correct goal.

Follow it with the first real-state branch: at Celadon the model sees three legal objectives and
selects the Rocket Hideout without being shown the fixed route's answer. Then show the bounded skill
clearing five trainers and the post-run observer confirming both the Hideout event and Silph Scope.
Do not cut there: show the loop observing again, choosing Pokémon Tower at 99.08%, and independently
confirming the Poké Flute at Lavender Center. Keep the screen labeled **“model chose two goals;
fixed skills executed 3,651 mechanic actions”**. The useful headline is two uninterrupted decisions
over 265,588 frames, not an autonomous run.

Then let the third replan breathe: the model chooses Fuchsia, the fixed skill captures Snorlax in
two throws, and the observer confirms Fuchsia Center. Update the label to **“three model goals;
6,783 fixed-skill actions; zero route labels or fallbacks.”**

Now reveal the measurement trap. The quest graph can call a goal legal before its mechanic skill is
physically runnable from the current map and inventory. Add the live affordance mask, then show its
on-screen exclusions: dependency-legal goals remain visible, but each impossible skill has a typed
reason. This is the point where the demo stops confusing “allowed eventually” with “executable
now.”

Continue the same emulator process through Safari, Koga, Strength, Erika, and Saffron. The final
counter reads **“eight model dispatches; 15,593 fixed-skill actions; zero labels, fallbacks, or
replans.”** Do not present all eight decisions as equal evidence. Seven had only one executable
candidate. At the first true branch, Koga and Strength were both runnable and the model chose Koga
at **96.41% confidence**. Make that distinction part of the visual: seven grey singleton dispatches,
one highlighted ranking decision. Then let the model dispatch Silph Co. in the same emulator
process. The fixed skill performs 5,041 more actions, verifies the Master Ball and required events,
leaves optional Lapras untouched, and returns healed. Continue into the Fighting Dojo: five fights,
Hitmonlee recruited, and the six-member party finally complete. The same bounded objective skill
then takes the trainer-free warp route to Sabrina and independently verifies the Marsh Badge. End
then acquire Fly, teach it to DUX, cross Route 21 without defeating a trainer, and heal at Cinnabar.
Inside Pokémon Mansion, recover the Secret Key and TM14 while a split-screen evidence panel proves
that all optional trainers, Blaine, and the Volcano Badge remain untouched. Explain why this matters:
the old deterministic chapter quietly combined two graph objectives, while the portable loop now
returns control to the model between them. End the act on **“twelve dispatches; 25,254 fixed-skill
actions; zero labels, fallbacks, or replans”** and the separately selectable Blaine frontier.

### Act VII: the Crystal test — 10:10–11:15

The first transfer benchmark should be small enough to fail clearly: one battle and one local
navigation task in Pokémon Crystal. Compare zero-shot performance, few-shot adaptation, and
from-scratch training. The point is not to claim universal Pokémon intelligence after one test; it
is to discover which Red abstractions were real and which were accidental details of one cartridge.

### Ending: why the Pokédex matters — 11:15–12:00

A living Pokédex is not merely a completion trophy. It forces the player to explore, capture,
store, withdraw, evolve, manage scarce items, assemble parties, and train many different Pokémon.
Those pressures form a lifelong curriculum. Level 100 is the final endurance gate, not the first
proof of intelligence.

Closing line: *“The first version proved an automated system could finish Pokémon Red. The next
version has to prove the model learned something worth carrying into a game it hasn't seen.”*

## Required visuals and receipts

- Clean power-on through Hall of Fame footage with the checkpoint counter visible.
- The `[49, 0, 0, 0, 0, 0]` and `[24, 0, 4, 0, 5, 1]` League vectors side by side.
- A six-member party screen before the League and role-specific battle clips.
- One preserved failed-run receipt and the measurement that diagnosed it.
- Teacher versus learner control diagrams with individual decision ownership highlighted.
- A strict-evaluation counter showing teacher queries at zero.
- The Celadon three-way choice, the post-Hideout replan to Tower, and the independently verified
  Hideout/Silph Scope/Poké Flute receipt, with model-versus-fixed-skill ownership labeled.
- The twelve-step Mansion receipt, with eleven singleton dispatches visually separated from the real
  Koga-versus-Strength branch, the transient Gold Teeth fact disappearing after use, and Hitmonlee
  filling the sixth party slot before Sabrina. Add the Fly lesson, trainer-free Route 21 crossing,
  and the positive Secret Key/TM14 evidence beside the negative Blaine/Badge/trainer evidence.
- The first Crystal zero-shot/few-shot/from-scratch comparison when it exists.

## Honesty rules for the video

- Do not call expected-objective authorization autonomous planning.
- Do not combine teacher, constrained, shadow, and model-controlled decisions into one denominator.
- Do not call deterministic completion model completion.
- Keep training seeds, rehearsal runs, and sealed evaluation starts visibly separate.
- Label future architecture and Crystal footage as planned until receipts exist.
- Put source hashes, manifests, and full receipts in the description rather than crowding the edit.
