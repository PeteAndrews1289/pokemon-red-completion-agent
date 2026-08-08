# Handoff

Written 2026-08-07 for the agent taking over. Read this once, completely, before touching anything.
It is meant to make you *actually* oriented, not politely briefed — which means most of it is about
what is wrong, what is unproven, and what this codebase has repeatedly fooled people into believing.

Then read, in order: [MISSION.md](MISSION.md) (why the project exists),
[AGENT_COORDINATION.md](AGENT_COORDINATION.md) (rules and lanes), and
[docs/story.md](docs/story.md) (the narrative, which doubles as a record of the failure modes).

---

## 1. What this project is for

**Build a model that can actually play Pokémon, and fill a living Pokédex across the mainline
titles.** Not "beat Red reliably." The Pokédex is the forcing function: it is the constraint that
makes route tricks useless and real decisions necessary.

The deterministic teacher exists to *produce demonstrations a model can learn from*. Its value is
therefore measured by how many real decisions its demonstrations contain — not by whether it wins.
A run that wins with one overleveled Pokémon sweeping is a run that teaches nothing, and that is the
condition the current work is trying to escape.

Keep this in view. It is easy — I did it repeatedly — to spend a day on menu plumbing and lose track
of whether it serves this.

---

## 2. What is actually true, as of this handoff

**Working and verified:**

- The deterministic teacher completes Red repeatedly, with genuine Champion and Hall-of-Fame
  evidence in the same run.
- A trained model authorizes all 36 expected objectives with zero fallbacks. Fixed code selects and
  executes them. Do not describe it as an autonomous player — it runs as
  `model_authorized_fixed_specialists`.
- Encounter bands for five areas are measured with sample counts and reproduce exactly across runs
  (the route is deterministic).
- A party member too weak for where the run happens to be is now routed to a venue that suits it,
  travels there, and gains levels. This is new as of 2026-08-07 and is the mechanism everything
  downstream depends on.
- A clean-power, uninterrupted run now completes the entire development curriculum and the game in
  the same process: 312/312 checkpoints, 36/36 objectives, Champion defeated, and Hall of Fame
  entered. The curriculum used 1,716 battles and 885 heals and passed with a final-form party at
  levels 60/55/55/55/55/55.
- Whole-League instrumentation first recorded 49/49 attack decisions from party slot 1. Three
  matchup-aware lessons now create real roles: Jolteon handles Lorelei's Water core, Hitmonlee
  attacks Bruno's opening Onix, and Agatha is split between Jolteon's Thunder against Golbat and
  Dugtrio's Earthquake against her four grounded Poison targets. A clean-power completion records
  `[24, 0, 4, 0, 5, 1]`: 4/6 League participants and 70.59% busiest share overall. Agatha alone is
  `[0, 0, 4, 0, 2, 0]`, 66.67% busiest share, with all five opponent positions, three switches,
  and full-party recovery verified. All 312 checkpoints and Hall of Fame pass.

**Not true, however it may look:**

- The team still does not choose its own battles. The trainees now perform the majority of the
  balancing work, but the decisions remain teacher-authored.
- No learned policy has reproduced this balanced-team run. No cross-game transfer has been
  measured. The terminal Pokédex census is 18 owned and 89 seen against the 124-species Red target;
  living-Pokédex completion remains open.
- `max_enemy_level_delta=2` is **rejected**. A full-health level-23 Diglett fainted to a level-19
  Diglett before dealing damage. The replacement combines a five-level direct advantage, type-risk
  refusal, participation-based evolution, and immediate attacks; that replacement now has both
  captured-state and full-route proof.

**Gate state:** 1945 tests, 3 deselected; ruff, mypy (111 files), artifacts, docs and registry all
clean after the Secret Key adapter. The source-bound twelve-step run uses published commit
`e2875c4` (the documentation receipt lands in the following commit).

---

## 3. Start here

**Extend the qualified League roles beyond four members.** Lorelei, Bruno, and Agatha now prove
non-cosmetic specialist roles, but DUX and Snorlax still supply no recorded League attacks and
Blastoise still owns 70.59% of the whole-League decisions.

The next useful experiment is a fifth species- and matchup-resolved role, judged by the same
clean-power whole-League report. DUX or Snorlax needs a matchup that creates genuine offensive,
defensive, or resource value; never switch merely to satisfy a counter. Lance and the Champion are
still single-participant chapters, so they are the clearest candidates. Keep the private chained
League checkpoints for bounded regressions, preserve the existing lineage and partition contracts,
and keep living-Pokédex expansion and second-title transfer as explicit later stages.

Then continue down [AGENT_COORDINATION.md](AGENT_COORDINATION.md) § *Open work, in priority order*.

### Architecture-audit pivot — 2026-08-08

The latest full audit changes what "start here" means. The deterministic teacher is now sufficiently
complete to serve as the frozen expert oracle. Another Red-specific repair or League role is useful
only when it fixes a genuine regression or adds a bounded, non-cosmetic lesson; it must no longer
delay transferring control authority to the learner.

What the audit established:

- the clean teacher, referee, trajectory recorder, captured-state harnesses, and private lineage
  controls are unusually strong and should be preserved;
- the nonlinear battle model has real live Red completion evidence, but it predates the current
  balanced-team curriculum;
- `ModelObjectivePolicy` authorizes the objective that fixed code already intends to run, while
  `run_qualified_play` still dispatches the chapter sequence directly;
- live navigation is dominated by authored direction sequences even though reusable local A* exists;
- resource planning, recovery, collection execution, and the second-game adapter remain teacher
  owned, partial, or scaffolding; and
- a normal completion report can pass without requiring a teacher-free battle-policy report, so
  official learned evaluation needs a stricter, explicit contract.

The dependency order is now:

1. **Freeze and publish the Red oracle.** Keep this branch as the canonical source, merge the current
   draft into `main`, and stop opening sealed campaigns for teacher-only tuning.
2. **Create a portable player loop.** Observation → chosen objective → dispatched skill → typed
   action → structured result → replan. Revision-specific reads and menu compilation stay behind the
   game adapter.
3. **Collect current balanced decision data.** Record decision spans, learner failures, and
   corrections rather than treating roughly half a million controller actions as equally useful.
4. **Enforce teacher-free learned evaluation.** Any teacher query, unsupported-observation fallback,
   undeclared safety substitution, or expected-route label is a visible counted failure.
5. **Complete Red with the learned stack.** The initial reliability gate remains at least 8/10
   preregistered clean starts with frozen code and weights, no restore, and no teacher control.
6. **Falsify transfer with Crystal.** Start with one battle and local-navigation vertical slice, then
   compare zero-shot, few-shot, and from-scratch performance.
7. **Use collection as the lifelong curriculum.** Expand capture, storage, evolution, and training
   through the portable loop; do not write a second 120-species fixed route.

Near-term code work starts with item 4 because it creates an enforceable boundary immediately, then
items 2 and 3 proceed together. See [the roadmap](docs/roadmap.md) for the full gate sequence and
[the video narrative](docs/youtube-video-narrative.md) for the public explanation of this pivot.

### Portable-loop implementation checkpoint — 2026-08-08

The first two architecture boundaries now exist and are ROM-independent:

- strict battle evaluation records teacher queries separately from fallbacks and cannot pass after
  either one;
- `ModelObjectivePolicy.select(state)` ranks legal objectives without receiving the route's expected
  objective ID;
- `PortablePlayerLoop` implements observe → select → specialist plan → one bounded typed action →
  observe result → verify/replan;
- verified objective facts may not regress across an action, unavailable objective choices fail
  before execution, and a specialist cannot return authority for a different objective; and
- the deterministic objective policy uses the identical loop interface, so teacher and learner
  ownership can be compared without two runtimes.

This is **not end-to-end Red autonomy yet**. `run_qualified_play` still invokes most chapter
functions in a fixed Python sequence. The portable loop now has an explicit composite-skill
registry, action/frame bounds, declared side effects, and independent post-skill semantic
verification. Unsupported model choices stop visibly rather than falling back to the fixed route.

The bounded exhaustive counterfactual audit of the historical planner enumerates **166 reachable
dependency-valid states**, including **129 branching states** and **446 neutral/candidate-local
evaluations**. Selection changes with location in **73/129 (56.59%)** branching states and chooses
the candidate whose target region matches simulated location in **237/317 (74.76%)** opportunities.
This proves some context sensitivity, not correct gameplay. The 80 local-context misses are the
first explicit planner-curriculum queue. See the
[sanitized receipt](docs/evidence/semantic-objective-counterfactual-audit-2026-08-08.json).

A current-source private capture at the stable Celadon Center boundary then reconstructed fourteen
verified objectives and exposed three genuinely legal choices: `clear_rocket_hideout`,
`defeat_erika`, and `reach_saffron`. Without an expected label, the historical model selected
`clear_rocket_hideout` at **99.70% confidence**. No skill or action was executed, so this is the
first real-state selection diagnostic—not live objective completion. The capture also proves that
resumed evaluation needs an authenticated progress envelope because transient historical location
facts are not recoverable from current cartridge memory alone. That envelope is now implemented:
the capture tool binds the exact private state digest to its checkpoint and verified-objective
prefix, and refuses a modified state. The resumed Red observer now reconstructs the real Celadon
state and its three legal objectives from that envelope plus live memory. The dispatcher remains
next. See the
[selection receipt](docs/evidence/model-selected-celadon-objective-2026-08-08.json).

The next published slice then executed that choice. From the same three legal branches, the model
selected `clear_rocket_hideout` at **99.70% confidence** with no expected label or fallback. Its
registered teacher-authored skill executed **1,143 actions / 98,237 frames**, defeated five exact
trainers, bypassed eight optional trainers, returned the fully healed party to Celadon Center, and
released the controller. Crucially, the loop did not accept the skill report as completion: a fresh
memory observation independently added both `story:rocket_hideout_cleared` and
`item:silph_scope`. The resulting legal frontier is `rescue_fuji`, `defeat_erika`, and
`reach_saffron`. See the
[execution receipt](docs/evidence/model-selected-hideout-execution-2026-08-08.json).

The next published slice added Pokémon Tower and ran both decisions uninterrupted. After Hideout,
the same model selected `rescue_fuji` at **99.08% confidence** from `rescue_fuji`, `defeat_erika`,
and `reach_saffron`. The Tower skill executed **2,508 actions / 167,351 frames**, fought ten required
battles, obtained the Poké Flute, and returned the healed party to Lavender Center. Across both
steps the model made two decisions with no expected labels or fallbacks; the loop executed **3,651
actions / 265,588 frames** and independently verified all three new semantic facts. See the
[two-decision receipt](docs/evidence/model-selected-two-objective-sequence-2026-08-08.json).

The third uninterrupted decision selected `reach_fuchsia` from the post-Tower Lavender state. Its
registered skill executed **3,132 actions / 373,072 frames**, cleared the required Route 12–13
battles, captured the level-30 Snorlax in two throws, preserved the Poké Flute, and returned a
fully healed four-member party to Fuchsia Center. The complete three-decision slice totals **6,783
actions / 638,660 frames**, three model selections, four independently observed progress facts,
zero expected labels, zero fallbacks, and zero replans. See the
[three-decision receipt](docs/evidence/model-selected-three-objective-sequence-2026-08-08.json).

The explicit skill-affordance mask is now implemented. It reports dependency-legal objectives,
executable objectives, and an exclusion reason for every unavailable skill. The uninterrupted live
run extends through Surf, a real Koga-versus-Strength branch, Strength, Erika, and Saffron: eight
model dispatches, **15,593 fixed-skill actions**, zero expected labels, zero fallbacks, and zero
replans. The model chose Koga from two executable candidates at **96.41% confidence**; the other
seven decisions were singleton dispatches and are recorded separately so their near-100%
confidences cannot be mistaken for ranking evidence. The observer also stopped latching transient
inventory facts, so Gold Teeth disappear after the Warden consumes them while durable objective
progress remains. See the
[eight-decision receipt](docs/evidence/affordance-masked-eight-objective-sequence-2026-08-08.json).

Silph is now part of the same uninterrupted sequence. Its bounded skill executed 5,041 actions and
1,675,457 frames, cleared the required events, retained the Card Key and Master Ball, left optional
Lapras untouched, and returned healed to Saffron Center. The complete slice is now nine dispatches
and 20,634 actions; eight are singletons and the Koga-versus-Strength choice remains the one measured
ranking branch. See the
[nine-decision receipt](docs/evidence/affordance-masked-nine-objective-sequence-2026-08-08.json).

The post-Silph curriculum is now connected as one bounded `defeat_sabrina` skill. It recruited
Hitmonlee after all five Dojo fights, completed the six-member party, followed the trainer-free Gym
warp route, defeated Sabrina, and returned healed to Saffron Center. The skill used 3,058 actions /
949,298 frames; the ten-step slice totals 23,692 actions with independent Marsh Badge observation.
See the
[ten-decision receipt](docs/evidence/affordance-masked-ten-objective-sequence-2026-08-08.json).

The Cinnabar adapter is now live-qualified. It used 830 actions / 148,680 frames, acquired HM02,
taught Fly to DUX, preserved all six party members and lead stats, fled four bounded wild battles,
defeated zero Route 21 trainers, and ended fully healed in Cinnabar Center. The eleven-step slice
totals 24,522 actions and independently verifies `location:cinnabar_island`. See the
[eleven-decision receipt](docs/evidence/affordance-masked-eleven-objective-sequence-2026-08-08.json).

The twelfth dispatch now isolates the Mansion lesson from Blaine. It used 732 actions / 87,564
frames, recovered the Secret Key and TM14, preserved all six optional trainers, explicitly verified
that Blaine and the Volcano Badge remained untouched, and returned the healed party to Cinnabar
Center. The twelve-step slice totals 25,254 actions, eleven singleton dispatches, one real ranking
branch, and zero labels, fallbacks, or replans. See the
[twelve-decision receipt](docs/evidence/affordance-masked-twelve-objective-sequence-2026-08-08.json).

**Next:** connect a separate post-Mansion `defeat_blaine` skill from this verified boundary. Do not
reintroduce the old combined Mansion-plus-Gym authority: the model owns the objective transition;
current skills still own navigation, battle, menu, training, and recovery actions.

That skill is now live-qualified at the authenticated post-Mansion boundary. Its first private
rehearsal returned a report but was correctly rejected for exceeding the initial 20,000,000-frame
declaration. With only the safety envelope widened, the published-source rerun passed in 469,232
actions / 31,883,961 frames. It trained 1,716 balanced-team battles with 885 healing trips, reached
60/55/55/55/55/55 in final forms, defeated Blaine, collected TM38 and the Volcano Badge, returned
healed, and independently exposed `defeat_giovanni`. See the
[post-Mansion receipt](docs/evidence/affordance-masked-post-mansion-blaine-2026-08-08.json). The
failed rehearsal remains uncounted; the successful receipt is a bounded one-objective qualification,
not yet a contiguous thirteen-step run.

The post-Blaine Giovanni adapter is now live-qualified from its authenticated capture. It used
1,409 actions / 156,305 frames, cleared the six declared Viridian Gym trainer lessons, preserved
the two intended bypasses until Giovanni settled the remaining events, defeated his exact party,
collected TM27 plus both Earth Badge mirrors, returned all six members healed, and independently
opened `cross_victory_road`. See the
[Giovanni receipt](docs/evidence/affordance-masked-post-blaine-giovanni-2026-08-08.json). This is a
bounded one-objective qualification; the next adapter starts from the authenticated Viridian Center
terminal.

Victory Road is also live-qualified from that Viridian capture. It used 3,857 actions / 453,733
frames, defeated the exact Route 22 rival party without a Hyper Potion, passed all seven badge
gates, satisfied all five boulder-switch events, normalized the exact League reserves, and ended
with the full party healed at Indigo. Fresh observation opened `defeat_lorelei`. See the
[Victory Road receipt](docs/evidence/affordance-masked-post-giovanni-victory-road-2026-08-08.json).

The portable League chain is qualified through Lance from successive authenticated room terminals:
Lorelei 480 actions / 42,783 frames, Bruno 328 / 32,538, Agatha 466 / 45,854, and Lance 582 /
51,905. The first three preserve their measured two-member role lessons; Lance is still a
single-member chapter. The current private boundary is `portable-loop-post-lance.state`, with
`defeat_champion` available. Before wrapping the historical Champion chapter, split its automatic
Champion/Hall-of-Fame transition into honest graph authority if the live game exposes a stable
post-victory boundary.

That experiment is complete. The first rehearsal proved there is no stable post-victory
Champion-room boundary: the Champion event and Hall-of-Fame map appeared together. The final skill
therefore declares Hall of Fame as an automatic side effect of `defeat_champion`; it does not claim
a second model decision. The source-bound rerun passed in 567 actions / 45,216 frames with the exact
Champion party, one X Accuracy, six X Specials, three Full Restores, and the 66/55/55/55/55/55 team
in the Hall of Fame. See the
[Champion receipt](docs/evidence/affordance-masked-post-lance-champion-2026-08-08.json).

All post-Celadon adapters are now individually live-qualified on successive authenticated captures,
and the complete integration run has passed. From the original authenticated Celadon capture, one
emulator process executed 20 model dispatches, 502,175 actions, and 37,369,283 frames through the
Hall of Fame with no expected labels, fallbacks, or replans. Fresh observations closed all 36 graph
objectives. Nineteen dispatches were singletons; only Koga versus Strength measured ranking. See the
[twenty-decision receipt](docs/evidence/affordance-masked-twenty-objective-hall-of-fame-2026-08-08.json).

The first replacement seam is implemented. `training_control.py` defines a 21-feature portable
observation and the five phase-masked actions `seek`, `fight`, `flee`, `heal`, and `stop`.
`run_red_team_balancing` emits each teacher decision before execution through an optional sink, and
`scripts/replay_training.py --out-decisions` atomically preserves complete or failed streams. The
features deliberately exclude game, map, species, move, and memory identity.

Diagnostic lineage 01 completed at source `778e6cb`: 48,156 decisions, 1,716 battles, 885 healing
trips, zero faints, and a 55/55/55/55/55/55 terminal. Counts are seek 44,882, fight 1,710, flee
1,064, heal 499, stop 1. The raw v1 artifact remains private and immutable at SHA-256
`6685c889c4e5ea55c56b0194074f0c4b6b82376d40dfb8f475f7d903856f5a64`; it predates embedded
lineage/source provenance and is diagnostic only. The v2 writer and `training_control_dataset.py`
now bind later streams to source commit, dirty flag, root-state digest, and whole-lineage partition;
the audit rejects state overlap and validation-only classes.
`training_control_model.py` now supplies the class-balanced MLP, phase-masked inference, aggregate
metrics, and whole-lineage candidate fit. Its public summary is always non-promotable until later
runtime gates; only synthetic separability and integrity behavior are currently tested.
For distinct deterministic roots, `replay_training.py` accepts a positive `--seed-wait-frames` only
when paired with `--out-root-state`; it advances the emulator, saves the exact resulting private
state, and hashes that state into v2 provenance. Never call two copies of the same input state
independent lineages without creating and retaining distinct roots this way.

Counted v2 train lineage 01 is qualified from a retained 17-frame root at source `4c885d8`:
46,687 decisions, all five actions, 1,726 battles, 815 healing trips, zero faints, and all level 55.
Its private stream SHA is `f13f9f1031632a8f1158c280c241d6f6a24ab5eeed4c30bdf76d802917e1aca1`;
its root-state SHA is `62f7862e6f7e15c6f7c14a4cbb7488d6ff946502809dde5e1315171925e80c9c`.
It adds 45,831 novel unique action-feature pairs versus diagnostic lineage 01 (99.85% of its unique
pairs). See the [sanitized receipt](docs/evidence/training-control-v2-train-01-2026-08-08.json).

**Next:** collect at least three v2 complete decision lineages, split by root lineage rather than by
row, train and shadow-evaluate the first candidate, then replace the 469,232-action skill's teacher
authority under the same safety envelope. Preserve the fixed skill as demonstrator and referee. Do
not describe instrumentation as a trained policy or this integration result as clean-start or
end-to-end learned completion.

---

## 4. How to work here without burning hours

### Iterate against a captured state, not a full run

A run reaches the training block in about six minutes. A captured state reaches it in about one.
Twelve runs in one session were spent replaying the same 275 checkpoints before this existed.

```bash
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Returned safely from Mansion" --out <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state --swap-only
POKEMON_RED_ROM=<path> python scripts/replay_training.py --state <scratch>/mansion.state --max-steps 40
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Bruno room ready" --out <scratch>/bruno.state
POKEMON_RED_ROM=<path> python scripts/replay_bruno.py --state <scratch>/bruno.state
POKEMON_RED_ROM=<path> python scripts/capture_checkpoint.py \
    --at "Lorelei supplies ready" --out <scratch>/lorelei.state
POKEMON_RED_ROM=<path> python scripts/replay_lorelei.py --state <scratch>/lorelei.state
POKEMON_RED_ROM=<path> python scripts/replay_lorelei.py --state <scratch>/lorelei.state \\
    --out-state <scratch>/bruno-current.state
POKEMON_RED_ROM=<path> python scripts/replay_bruno.py --state <scratch>/bruno-current.state \\
    --out-state <scratch>/agatha.state
POKEMON_RED_ROM=<path> python scripts/replay_agatha.py --state <scratch>/agatha.state \\
    --out-state <scratch>/lance.state
POKEMON_RED_ROM=<path> python scripts/replay_lance.py --state <scratch>/lance.state \\
    --out-state <scratch>/champion.state
POKEMON_RED_ROM=<path> python scripts/replay_champion.py --state <scratch>/champion.state
```

`--max-steps` shrinks the policy's step budget so a spinning loop fails in seconds instead of
burning 500,000 steps.

A capture is **one starting point**, and its starting position is part of what it captures — the
Mansion capture leaves the player on the nurse's tile, where a button press feeds her dialogue.
Iterate against it; confirm with `cli play`.

State files are ROM-derived and private exactly as the ROM is. Keep them in scratch, never commit
them. This does not weaken the adapter's no-save property, which is about PyBoy never writing files
beside the user's ROM — see `PyBoyAdapter.save_state`.

### The gate, before every commit

```bash
.venv/bin/python scripts/check_public_artifacts.py
.venv/bin/python scripts/check_docs.py
.venv/bin/python scripts/regenerate_collection_registry.py --check
.venv/bin/ruff check .
.venv/bin/python -m mypy
.venv/bin/pytest -m "not integration"
```

Any `src/` change restales the collection registry. Regenerate and update the four golden values in
`tests/test_collection_protocol.py` **in the same commit**. Never hand-merge those hashes — they are
derived; take either side and regenerate.

### Two hard rules

- **Never edit `src/` while an emulator run is in flight.** A run loads its source at launch, so a
  mid-run edit does not change the run — it changes what the tree claims the run was.
- **Never open a counted evaluation seed.** Validation `1810002`–`1810005` and sealed test
  `1820001`–`1820005` are one-attempt-only. `1810001` is exposed and diagnostic-only.

The ROM path, private artifact root and objective-model path come from the environment per session
and must never appear in any file, tracked or not — `check_public_artifacts.py` scans the working
tree including untracked files.

---

## 5. Measured facts. Do not re-derive these, and do not contradict them without a measurement

Each cost at least one emulator run to establish. Each has an evidence file.

| Fact | Evidence |
| --- | --- |
| The Mansion fields levels **28–39**, not the 30–32 an old note claimed from 8 samples | `encounter-bands-2026-08-07.json` |
| Diglett's Cave is **15–21** typical with a rare Dugtrio at 31 | same |
| The **town map has no readable cursor** — five candidate addresses all stay frozen. Fly must be judged by the map underfoot | `town-map-cursor-not-observable-2026-08-07.json` |
| The party submenu is ordered **field moves, STATS, SWITCH, CANCEL**, so SWITCH is at `field_move_count + 1` | `party-submenu-layout-2026-08-07.json` |
| Menu signatures: start menu `max=7, top=(11,2)`; party list `max=5, top=(0,1)`; member submenu `max=4, top=(10,8)` | same |
| `watched=0x03` does **not** mean the d-pad is ignored — the party list reports it and its cursor moves | same |
| A **blocked press is not a step**, so a walk into a wall never rolls for an encounter | `cave-pacing-and-training-2026-08-07.json` |
| The +2 margin is unsafe: level-23 Diglett fainted from full HP to level-19 Diglett before dealing damage | `training-margin-four-level-faint-2026-08-07.json` |
| Captured-state development reached six level-55 members in 1,716 battles with zero faints | `measured-balanced-team-captured-state-success-2026-08-07.json` |
| A clean-power run passed the final-form 60/55/55/55/55/55 team gate and completed 312/312 checkpoints through Hall of Fame | `measured-balanced-team-full-route-success-2026-08-07.json` |
| The next full run measured all 49 League attack decisions on party slot 1: 1/6 participation and 100% busiest-member share | `measured-whole-league-participation-2026-08-07.json` |
| A clean-power run qualified the first matchup-aware League lesson: Hitmonlee attacked Bruno's Onix, recovery followed the damaged member, League participation reached 2/6, and Hall of Fame still passed | `measured-bruno-team-participation-2026-08-07.json` |
| The next clean-power run qualified Jolteon's Lorelei role: Thunder handled three Water targets, Blastoise handled Jynx and Lapras, League participation reached 3/6 with 90.70% busiest share, and Hall of Fame still passed | `measured-lorelei-team-participation-2026-08-07.json` |
| The next clean-power run assigned all of Agatha to Jolteon and Dugtrio, cut that battle from 15 decisions and ten healing items to six decisions and one item, raised League participation to 4/6 with 70.59% busiest share, and still entered Hall of Fame | `measured-agatha-team-participation-2026-08-07.json` |

---

## 6. How this codebase fools people

These are not hypotheticals. Each happened, more than once, and cost runs.

### Green tests that test nothing

The test file written to prevent never-executed code contained one test asserting objects construct
and one ending in `pass`. Both green. A later test monkey-patched away the exact method that was
broken, so the suite stayed green over a module whose entry point raised `AttributeError` on its
first call.

**Practice:** after writing a test, break the code it covers and confirm the test fails. If it does
not, the test is decoration. This caught four separate defects today that would otherwise have
shipped.

### A belief that nothing available can contradict

The SWITCH row was guessed wrong four times across five runs. Every check was derived from the same
assumption as the guess, so no amount of care could falsify it. One measurement did, in five lines —
and the answer was the formula the code had *before* I changed it.

**Practice:** when a guard and the code it guards come from the same assumption, the guard only
agrees. Recognise success by the game's own state: the map underfoot, the party order in memory, the
levels that rose. Where an observable exists, read it; where none does, act and check what happened.

### A process that looks like work

A run went ten minutes without failing. That looks exactly like training. It was pressing left
against a wall: 500,000 steps, fewer than 250 battles, no level gained. The number that separates
training from spinning is the ratio of steps to battles, and nothing was reporting it.

**Practice:** for any loop, ask what number would distinguish progress from motion, and report it.

### Constants that were true by accident

Field Dig addressed Diglett as the third party member with Dig in move slot two. Both held only
while nothing ever reordered the party. The moment the party swap started working, it broke.

**Practice:** making the party movable was the point. Anything that remembers a slot is a latent
bug. Find the Pokémon, do not remember where it was.

### Copies that drift from their originals

Three times a helper was copied from a proven module and lost the constant that made it work: the
matchup gate, the cursor selector, and a walk bounded at 12 steps where the proven version allows 24.

**Practice:** before writing a navigation helper, grep for one that already works. `surge.py` in
particular has proven paths for Vermilion, Route 11 and Diglett's Cave.

### Failures that carry no evidence

Five failures today produced messages with no state: `Could not select menu item.`,
`Fly to Vermilion failed.`, `Failed to enter Route 11`, a silent 500,000-step exhaustion, and
`Battle menu did not settle.` Each needed a run spent purely on instrumenting it before it could be
fixed.

**Practice:** this is the cheapest available change to this codebase. When you write a raise, put
the readings in it.

---

## 7. Predict before you run

Every run this session was preceded by a written prediction in `docs/evidence/predicted-*.json`
stating what should happen and, crucially, **what would refute it**. This is not ceremony. One
prediction assumed the party arrived as `[68, 20, 26, 30, 25, 30]`; it arrived as
`[55, 20, 26, 30, 25, 30]`, and the divergence was only legible because the assumption had been
written down. A run compared against no prediction can only be interpreted after the fact — which is
how a wrong band survived 155 samples that contradicted it.

---

## 8. Do not

- Do not restore the multi-target Route 22 continuation loop. It cycled every reserve into Venusaur
  until the party read `(0, 0, 0, 0, 0, 0)`.
- Do not treat a green `passed` as evidence the thing it names happened.
  `team_development.passed` never looked at five of six party members, and twelve receipts reported
  the opponent's levels as ours.
- Do not use the party as disposable HP. Switching to a healthy teammate is strategy; feeding a weak
  one in to absorb a hit is the V35 failure.
- Do not reintroduce a hand-derived Fly hop sequence. Two runs died to one.
- Do not describe the objective ranker as an autonomous player.
- Do not commit ROMs, saves, emulator states, trajectories, secrets, or absolute paths.

---

## 9. Loose ends you are inheriting

- **`global_router.py` and `collection_chapter.py` are scaffolding.** The router has a correct
  Dijkstra, three tests, no call site, a hand-written five-node graph, and edges carrying no warp
  coordinates — it cannot drive navigation as it stands. `run_collection` reads the collection
  correctly then raises `NotImplementedError` at routing. Give them a job or park them.
- **Participation is measured across all five League battles, but still concentrated.** Every
  chapter records active-party indexes and publishes participating-member count plus busiest-member
  share. Lorelei, Bruno, and Agatha have explicit specialist-role contracts; together they raise the
  League to 4/6 participants, but Blastoise still owns 70.59% of decisions. The remaining work is
  behavioral: add real matchup value for DUX and Snorlax, especially in Lance or Champion.
- **The ROM path is in git history.** `a9d0bb4` added it in source, `371be10` removed it. Not in the
  current tree; `a9d0bb4` is on no remote, so exposure is local only. Rewriting history is
  destructive and belongs to the repository owner.
- **The historical tolerance conflict is resolved in code.** Mansion development and Champion
  readiness now share `COMPLETION_LEVEL_PARITY` at a level-55 floor. Older evidence remains
  historical; do not reintroduce separate local contracts.

---

## 10. The standard to hold

Report what happened, not what was hoped for. Two claims I made today were wrong and needed
retracting: that a ten-minute run was "training" when it was spinning, and that `watched=0x03` meant
the d-pad was dead. Both were corrected in the record rather than quietly dropped, and the evidence
files say so.

That is the standard. This project's whole value is that its numbers can be trusted, and the only
way that stays true is if being wrong in public is cheaper than being vague.
