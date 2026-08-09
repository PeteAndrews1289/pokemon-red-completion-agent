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

## Latest episode payoff: the AI won, and the evaluator still said no

The clean-start evaluator is now real. In the first uncounted baseline, the objective and
trainee/venue models select 21 composite goals, verify 15 automatic cartridge effects, and reach
Hall of Fame with 114,831 controlled training choices, 400 executed disagreements, and no expected
objective label or fixed dispatch. Put the denominator on screen: the model chooses goals and
trainees; bounded authored skills still navigate and operate menus.

Then run the stricter four-model composition. Show the party reaching Lorelei at
63/55/55/55/55/55, the teacher-query and fallback counters pinned at zero, and 3,220 model move
decisions accumulating. Lorelei is defeated. The game enters Bruno's room. Then freeze on the
verifier result: **failed**.

The reveal is the battle vector: `[19, 0, 0, 0, 0, 0]`. The model never switched and every attack
came from the first party member, so the run violated the lesson it was supposed to demonstrate.
This is the coldest, clearest version of the project's thesis: finishing the game and learning to
play Pokémon are not the same objective.

Follow the failure into the code. The active battler has type, move, and matchup features; the five
reserves are reduced to aggregate health and level statistics. Even when the controller asks to
switch, the resolver prefers a healthy high-level reserve rather than the one with the best
offensive and defensive matchup. The next training phase is therefore concrete and portable:
represent each reserve by semantic matchup value, rank switch candidates, retrain on balanced-team
demonstrations, and repeat the exact same verifier. Do not edit around the red result.

Then show the repair as a feature-panel transformation. Six party cards now expose the same
identity-free measurements: health, status, level margin, usable PP, best offensive type margin,
accuracy-weighted power, and defensive resistance. Shuffle the reserve cards and show the same
matchup following the candidate to its new slot. Change only the opponent's types and show the
selected reserve change. Finally split the scorecard into **switch class** and **switch target**;
the model does not get credit unless both the action and the member are correct. Keep the final card
honest: **schema implemented; fresh model not trained yet**.

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
Keep the first Blaine rehearsal in the edit: the team-development skill returns, but the runtime
rejects it for exceeding its declared frame budget. It is a clean demonstration that the safety
envelope is enforced after real work, and that failed rehearsals are measured rather than relabeled
as successes.
Then show the successful source-bound rerun: **469,232 actions; 31,883,961 frames; 1,716 balancing
battles; 885 healing trips; final-form levels 60/55/55/55/55/55.** Finish on TM38, the Volcano
Badge, a fully healed party, and Giovanni appearing as the next independently observed objective.
Label this footage clearly as a post-Mansion captured-state qualification, not a continuous
thirteen-dispatch run.
Follow it with the short contrast: Giovanni takes only **1,409 actions / 156,305 frames** after the
31.9-million-frame training lesson. Show six required Gym trainers, two bypasses, the exact leader
party, TM27, Earth Badge, full-team healing, and Victory Road appearing from fresh observation. The
contrast makes the real bottleneck visible: broad team development, not high-level dispatch.
Then compress Victory Road into a navigation montage: Route 22 rival, seven badge gates, five
boulder-switch proofs, the League shopping ledger, and the healed Indigo terminal. Overlay
**3,857 actions / 453,733 frames** and end with Lorelei appearing from fresh observation.
For the League montage, keep the role vectors on screen: Lorelei `[5,0,0,0,3,0]`, Bruno
`[6,0,0,0,0,1]`, Agatha `[0,0,4,0,2,0]`, and Lance `[6,0,0,0,0,0]`. The last vector is important:
the loop completed the room, but it did not invent team diversity that the teacher had not taught.
Pause before the Champion to explain the final authority split—defeating the Champion and verifying
the Hall of Fame are two graph objectives even though the game may chain them automatically.
Show the failed split as the answer: the first post-victory observation is already the Hall of Fame.
Then show the corrected ownership label—**one model dispatch, one declared automatic cartridge side
effect**—beside **567 actions / 45,216 frames** and the final 66/55/55/55/55/55 party. Do not animate
a fictional second model choice.

Return to the original Celadon checkpoint for the payoff: show the full uninterrupted counter
advancing through all 20 dispatches without a restore between objectives. The terminal card should
read **“502,175 actions; 37,369,283 frames; 20 model dispatches; 36/36 graph objectives; Hall of
Fame; zero labels, fallbacks, or replans.”** Immediately reveal the denominator: 19 dispatches were
singletons, and fixed teacher skills still pressed every button. A stacked bar makes the next target
obvious—Blaine's team-development lesson alone consumed **93.44%** of the actions through 1,716
battles and 885 healing trips. End the Red act by replacing “Can the pieces connect?” with the more
important question: “Can the model learn the largest piece?”

For the next-episode bridge, show the same teacher loop with five labels appearing before the
inputs: `seek`, `fight`, `flee`, `heal`, and `stop`. Fade out the Red-specific map, species, move,
and memory fields, leaving the 21 portable signals—relative levels, health, attack reserve, team
readiness, venue suitability, and bounded progress. Be precise: this is the collection interface,
not a trained result. The cliffhanger is the first lineage-held-out candidate and whether it can
replace the teacher without changing the safety referee.

The first collection gives that bridge a measured ending: **48,156 decisions, 1,716 battles, 885
heals, zero faints, 55/55/55/55/55/55**. Animate the class distribution rather than only the total:
44,882 seek, 1,710 fight, 1,064 flee, 499 heal, one stop. Then let the 93.2% seek bar fill the screen.
That is the next trap—an apparently accurate model could simply predict the majority action. Close
on the safeguards: class weighting, whole-lineage validation, root-state overlap rejection, and no
held-out score until independent v2 lineages exist.
Show the learner architecture briefly after the warning: inverse-frequency weighting lifts the
minority classes, the current phase blacks out illegal outputs, and both raw and balanced accuracy
appear together. Keep the result card blank—the implementation exists, but no real lineage-held-out
candidate has earned a score yet.
Then show the first counted v2 root: a 17-frame perturbation saved as an exact private state, two
mid-run party-level checkpoints diverging, and both paths reconverging at all 55. Put **99.85% new
unique action-feature pairs** beside the hashes—but do not end on an easy victory.

Try 43 idle frames for lineage two and freeze the screen when both root hashes match. The entire
46,687-decision sequence matches too: 45,902 shared unique pairs, zero new ones. Label it
**“reproducibility control—rejected as independent data.”** This is the next measurement trap:
different settings and different output files are not necessarily different experience. Show the
repair as a reversible down-and-back movement that returns to the same map, tile, battle state, and
party while changing the serialized root.

Then let the honest root fail. At decision 11,122, a durable matchup faints the trainee because the
teacher enforced its health floor between battles but not between turns. Put **99.46% novel pairs**
next to **“failed—excluded from training.”** Show the repair: the same health signal is checked
before every move, and the safe escort takes over to flee. End the card with “training lineage 1
accepted; lineage 2 taught the teacher; validation still empty.”

Pay off the repair by replaying the exact same root: **60,192 decisions; 1,740 battles; 1,017
heals; zero faints; all 55.** Put **99.89% novel pairs versus training lineage 1** on screen. The
honest distinction matters: this earns a second training lineage, not a validation score. The next
card remains “validation lineage: empty” until a root that never influenced the repair completes.

Do not cut around the first validation failure. After 725 real wins, the held-out route encounters
33 consecutive matchups it safely refuses; an old 32-flee anti-loop threshold stops the run even
though levels were progressing. Mark all 17,751 decisions **“failed validation—never rerun.”** The
lesson is subtle: a useful saturated feature is not automatically a valid termination condition.
Freeze that repair, then require an entirely fresh validation root before showing a model score.

The fresh root completes: **60,459 decisions; zero faints; all 55; 99.72% novel unique pairs.** Now
reveal the first honest model card: **75.62% raw / 76.91% balanced validation accuracy** across all
five actions. Contrast it with the 20% balanced majority baseline. End with the necessary caveat in
large type: **offline candidate—no emulator authority yet.** The next episode is shadow inference,
then bounded control under the teacher referee.

For the shadow episode, show the model file hash being authenticated before the emulator starts.
Run teacher and model decision cards side by side, but visually disconnect the model card from the
controller. Accumulate confidence, phase accuracy, balanced agreement, and the five-by-five
confusion matrix live. Keep **“model authority: false”** on screen throughout; shadow success is
evidence that the model understands decisions, not permission to press buttons.

Then show why causal evaluation matters. The first controlled run stops at decision 480 because an
unsafe fight was still advertised. The second makes 1,963 conservative flee choices for real and
eventually exhausts its healing budget. Neither failure is edited away. The fix aligns the fitting
and inference masks, throws away both failed lineages for training, and starts again with two fresh
training roots plus untouched validation.

Reveal the replacement card: **78.06% raw / 89.25% balanced validation**, then the fresh shadow's
**100% battle agreement**. Finally connect the model card to the emulator: **59,137 decisions,
1,743 battles, zero faints, all six level 55, zero fallback.** Immediately split that success into
1,984 real safe fight choices and 1,602 forced singleton flees. The honest ending is the overworld
confusion: 12,405 safe seeks predicted as heals. The next problem is no longer “train a model”; it
is “give the model a real overworld control surface and score the cost of its mistakes.”

Open the next episode by stopping the first collection early. Split 639 old heal labels into 356
caused by the escort and 283 caused by the trainee, then highlight that the observation shows only
the trainee. The 3.49% heal precision is not merely a tuning problem; half the causes were invisible.
Cross out all three exposed roots before adding four game-neutral reserve signals. This is the
project's recurring thesis in miniature: do not ask a model to learn an answer from information it
was never given.

Reveal the completed shadow card: **55,904 decisions; 75.57% raw; 76.73% balanced; zero faints;
all 55; authority false.** Then zoom into the confusion matrix. The model catches 96.53% of flees
but only 42.05% of fights, replacing 1,134 safe fights with conservative exits; it also replaces
12,285 seeks with heals. That makes the next episode concrete: can a safety referee permit genuine
model authority without quietly turning every disagreement back into teacher control?

Answer with a deliberately narrow control diagram. Connect the model to `fight` and `flee` only;
leave overworld actions connected to the teacher. A conservative model flee really exits and costs
progress. An unsafe model fight hits a red referee wall and ends the run—there is no teacher arrow
around it. Label the experiment **“battle authority: true; overworld authority: false; fallback:
none.”** This makes the first controlled failure as scientifically useful as a completion.

Then show the failure rather than skipping to a cleaner rerun. At decision 480, every usable attack
is exhausted or disabled, the model requests `fight`, and the red referee wall ends the run. Put
**“479/480 agreement; terminated; zero fallback”** on screen. Rewind one decision and display the
two model inputs side by side: the last safe fight and the now-impossible fight are identical. The
lesson is not “train longer.” The model was offered an action the emulator could no longer execute.
Animate `fight` disappearing from the candidate card, leaving only `flee`, and name the principle:
**the model chooses among safe affordances; the adapter defines what is currently possible.** This
is the kind of game-neutral boundary that can transfer even when Crystal uses different memory
addresses, species, and moves.

Do not make the corrected rerun an instant redemption. It survives the unsafe boundary, but the
model turns **1,963 of 2,690 safe fights into real flees**. After 77,538 decisions, the healing
budget is gone and the party is still not ready. Put the two outcomes side by side: attempt one
proved the action interface was incomplete; attempt two proved a safe policy can still be useless.
Then reveal the second mismatch: inference masked impossible actions, while the training softmax
still learned from them. Show singleton rows fading out of the loss—not out of the evidence—and end
the beat on the new rule: **learn only where there was a choice; audit every boundary.**

Do not skip the feature-v2 rejection. Show the preregistered card before its numbers: zero missed
heals, at most 50 wasted heals, at least 92% heal precision. Then reveal **26 missed heals; 2,219
wasted heals; 20.72% precision** and stamp **“stopped before shadow.”** The story is not that 96.18%
accuracy was secretly good enough; it is that the operational contract overruled the headline.
Animate mandatory recovery collapsing to singleton `heal`, verified readiness to singleton `stop`,
and leave safe `seek`/optional-`heal` connected to the model. That visual carries the battle lesson
forward: the referee defines safe affordances; the policy owns the choices that remain.

Then allow the redesigned v6 controller to earn the narrow success. The offline card reads 100%,
the fresh shadow completes, and the causal cable connects to both battle and overworld control.
Let the counter finish at **57,644 controlled decisions; 1,801 battles; 1,046 heals; zero faints;
all six level 55; zero fallback**. Show all seven operational gates turning green.

Before calling it intelligence, put a second card beside it: **candidate-set-only baseline: 100%**.
The legal choices already determine every label—safe battles say fight, safe movement says seek,
and safety boundaries are singletons. Rename the green result on screen from “strategy learned” to
**“live authority and safety integration verified.”** This is the episode's most important honest
turn: even causal control can prove the plumbing without proving that state features matter.

Carry the same controller into the portable loop rather than ending on the isolated lesson. From
the post-Secret-Key capture, show one `defeat_blaine` dispatch feeding the authenticated controller
into the fixed skill, then returning to fresh observation: **57,548 controlled decisions; 1,796
development battles; 1,074 heals; 60/55/55/55/55/55 fully healed; Volcano Badge added; Giovanni
opened; all ten integration checks passed.** Keep “singleton objective dispatch” and “captured-state
integration” visible so this card closes system composition without inventing planner evidence.

Move the camera one decision earlier. Show six party members competing to become the next trainee,
then three measured encounter bands competing to become the venue. Strip species, slot, move, area,
map, and memory identities from the cards; retain only candidate-relative readiness, health,
levels, attack reserve, and encounter safety. Shuffle the cards and require the same candidate to
win. Then reveal the sealed result: **99.9004% on 7,030 genuine choices versus 95.6615% for the
shape-only baseline**, with 99.7727% trainee and 100% venue accuracy. Let the shadow card pass at
**119,353 genuine choices and 99.9941% agreement**, then connect authority on the separately sealed
root.

Do not hide the failure on the way to the resolution. The first causal run stops after **15,449 controlled choices**
with the party at 51/32/32/31/31/31 because the lesson exhausted its healing budget. Put the
surprising denominator beside it: **model/teacher disagreements: zero**. The ranker did not make a
different strategic choice before the failure, so the result is neither model success nor evidence
that one bad prediction caused the stop. Stamp the root **“causal gate rejected”**, preserve it,
and run the same-root teacher diagnosis. It completes normally, proving the curriculum and root are
sound. Then reveal the instrumentation bug: merely installing an agreeing callback recomputed a
downstream directive. After the agreement-no-op repair, a newly preregistered causal root finishes
with **119,668 controlled choices, 191 executed trainee disagreements, 1,803 battles, 1,114 heals,
all six level 55, and zero faints**. This failure–diagnosis–repair–causal-proof sequence is the
cleanest example yet of why live operational gates matter more than a 99.9% offline score.

Give the repaired ranker one final systems payoff. From the post-Secret-Key capture, show the
objective model dispatching `defeat_blaine`, then the same strategic scorer controlling **114,831
trainee/venue choices** and executing **400 disagreements** inside the bounded skill. End on the
fresh Volcano Badge observation, fully healed 60/55/55/55/55/55 party, and Giovanni becoming
available. Keep “singleton objective” and “authored mechanics” on screen throughout.

Then remove the captured-state card and rewind to clean power-on. Run the same frozen strategic
ranker through the newly wired full-route seam: **312/312 checkpoints, 36/36 objectives, 114,831
controlled trainee/venue choices, 400 executed disagreements, 1,803 development battles, zero
fallback, and Hall of Fame in one process**. The party leaves development fully healed at
60/55/55/55/55/55. This is the strongest ending available now because the model-controlled
strategy survives the entire route around it. Keep the boundary equally large on screen:
**“uncounted single root; fixed objective sequence and mechanics; not 8/10 autonomy.”**

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
- The uninterrupted twenty-dispatch Hall-of-Fame receipt and a proportional action bar showing
  469,232 of 502,175 actions inside the team-development/Blaine skill. Label the captured Celadon
  start and teacher-authored mechanics on screen for the entire sequence.
- The v6 causal receipt beside its candidate-only baseline: 57,644 controlled decisions and all
  operational gates passed, while the state-dependent-policy claim remains visibly rejected.
- A shuffled trainee/venue candidate-card sequence showing that identity-free candidate order
  changes without changing the intended strategic selection.
- The strategic shadow pass, preserved causal rejection, same-root diagnosis, and repaired causal
  success: 119,353 shadow choices; then 15,449 controlled choices with zero disagreements and an
  incomplete 51/32/32/31/31/31 terminal; then 119,668 controlled choices with 191 executed
  disagreements and an all-55 terminal.
- The portable strategic proof: 114,831 controlled choices, 400 disagreements, 1,803 development
  battles, 1,048 heals, fresh Volcano Badge observation, and Giovanni available—alongside the
  singleton-objective and fixed-mechanics limitations.
- The uncounted clean-power strategic rehearsal: boot, 312/312 checkpoint counter, the same
  114,831-choice / 400-disagreement authority receipt, balanced party, and Hall of Fame. Keep
  “fixed route, one uncounted root” visible rather than presenting it as end-to-end learned play.
- The portable clean-start baseline card: 21 selected composites, 15 automatic effects, 638,520
  actions, 45,766,774 frames, no expected labels, fixed dispatches, fallbacks, or replans.
- The strict four-model contrast: 63/55/55/55/55/55 at Lorelei, 3,220 model moves, zero teacher
  query/fallback, the battle win, then the rejected `[19,0,0,0,0,0]` participation vector.
- A split-screen feature visualization: rich active-Pokémon matchup features on the left and five
  anonymous reserve aggregates on the right, followed by the proposed candidate-relative schema.
- The first Crystal zero-shot/few-shot/from-scratch comparison when it exists.

## Honesty rules for the video

- Do not call expected-objective authorization autonomous planning.
- Do not combine teacher, constrained, shadow, and model-controlled decisions into one denominator.
- Do not call deterministic completion model completion.
- Keep training seeds, rehearsal runs, and sealed evaluation starts visibly separate.
- Label future architecture and Crystal footage as planned until receipts exist.
- Put source hashes, manifests, and full receipts in the description rather than crowding the edit.
- Do not present defeating Lorelei as passing the learned-team curriculum; the verifier rejected it.
