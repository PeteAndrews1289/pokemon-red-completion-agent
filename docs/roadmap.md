# Roadmap

## End state

The final deliverable is a learned/hybrid policy that chooses objectives and bounded skills from
semantic observations, then adapts when timing, encounters, battle outcomes, status, or position
differs from its demonstrations. The qualified deterministic player is a disclosed teacher and
safety baseline for producing evidence and corrections. It is not the final model, and its results
must not be reported as learned-policy results.

## Milestone 0 — completion foundation

**Status: complete — July 2026**

- [x] Define the clean-run completion contract.
- [x] Separate training assistance from evaluation assistance.
- [x] Add exact ROM identity checks and public-artifact guards.
- [x] Add deterministic grid navigation.
- [x] Validate the semantic objective graph and specialist interfaces.
- [x] Add source-bound run manifests and the independent completion referee.

Exit gate: all foundation modules pass ROM-free CI and no document claims gameplay progress.

## Milestone 1 — verified clean-start chapters

**Status: complete — July 2026**

Current qualification: **299/299 bounded checkpoints** and **36/36 completion objectives**,
ending with concurrent Champion-defeated and Hall-of-Fame verification. Three clean-power-on,
no-restore runs reached the identical 4,796,436-frame / 41,316-action terminal. This is an exact
deterministic-teacher completion, not a learned-policy or timing/RNG-generalization result.

The later robustness lineage adds a reusable Mansion training block and has independently passed
two clean-power runs at **301/301 checkpoints** and **36/36 objectives**. Each replay trained the
lead from level 46 to 55 with 115 wild wins, five healing trips, and zero faints, then reached the
same Champion-plus-Hall-of-Fame terminal in 6,581,531 frames and 54,261 actions.

The newest balanced lineage adds the Celadon Eevee gift, Jolteon evolution, all five Fighting Dojo
battles, and the Hitmonlee gift. It passes **312/312 checkpoints** and **36/36 objectives** from
clean power with the declared six-member roster, zero training faints, a final level band of
82–87, and 516,338 teacher actions. The balancing block required 5,445 wild wins and 529 healing
trips before satisfying its five-level spread contract.

- [x] Build the no-save PyBoy bridge and read-only state adapter from pinned symbols.
- [x] Add controller timing and one authoritative action executor.
- [x] Qualify clean power-on through the input-ready bedroom and one-tile movement probe.
- [x] Qualify leaving home, Professor Oak's escort, and Squirtle selection through six closed-loop
  checkpoints.
- [x] Add an optional visible watch mode that leaves human input and saving disabled.
- [x] Qualify the lab rival, Oak's Parcel delivery, and Pokédex objective in one clean session.
- [x] Add a continuous `play --watch` command with visible semantic checkpoints and a safe,
  explicit bounded stop.
- [x] Qualify the route to Pewter City and defeat Brock.
- [x] Qualify Route 3, Mt. Moon's required battles and fossil choice, and Cerulean City.
- [x] Qualify the Cerulean rival, Nugget Bridge, selected Route 25 trainers, Bill, the mandatory
  Cerulean Gym trainer, and Misty.
- [x] Qualify the Cerulean Rocket thief, Route 5, the Underground Path, the required lower Route 6
  trainers, bounded wild-encounter recovery, and stable Vermilion arrival.
- [x] Qualify the Vermilion harbor, S.S. Anne corridors, required rival battle, Captain interaction,
  and four-field HM01 Cut evidence.
- [x] Qualify bounded Spearow and Diglett capture, the DUX trade, Cut and Dig preparation, the
  variable Gym switch puzzle, a Dig-only Lt. Surge win, TM24, and mirrored Thunder Badge evidence.
- [x] Qualify BubbleBeam preparation, exact tunnel supplies, Route 9, all mandatory Rock Tunnel
  trainers, bounded wild-flee recovery, the optional Route 10 trainer bypass, and stable Lavender
  Center arrival.
- [x] Qualify the single required Route 8 trainer, bypass all eight optional trainers, cross the
  west-east Underground Path and Route 7, and establish a stable Celadon Center boundary.
- [x] Qualify the Game Corner switch, spinner mazes, Lift Key and elevator, both boss-door guards,
  Giovanni, the Silph Scope, field Dig return, and a healed Celadon boundary.
- [x] Qualify the mandatory Pokémon Tower rival and Channelers, all three purified-zone heals,
  level-30 Marowak, the three final Rockets, Mr. Fuji's rescue, the Poké Flute, and the natural
  Wartortle-to-Blastoise evolution.
- [x] Qualify the level-30 Route 12 Snorlax, four mandatory Route 12/13 trainers, every optional
  Route 12–15 bypass, a resource-neutral Lavender recovery, and stable Fuchsia Center arrival.
- [x] Qualify one ₽500 Safari admission, the source-pinned Center/East/North/West route and
  elevation trap avoidance, six RUN-only encounters with 30 Balls retained, Gold Teeth and HM03,
  reusable-HM Surf teaching over slot-four Water Gun, and Time's Up cleanup.
- [x] Qualify the mandatory Fuchsia Gym route, Koga, Soul Badge, HM04 Strength, Erika, Rainbow
  Badge, the Fresh Water guard handoff, and stable Saffron access.
- [x] Qualify the Silph Card Key route, required trainers, rival and Giovanni battles, Master Ball,
  optional-Lapras bypass, and the permanent TM13 Ice Beam upgrade.
- [x] Qualify the trainer-free Saffron Gym warp route, Sabrina, TM46, Marsh Badge, and post-battle
  regular-trainer deactivation.
- [x] Qualify the bicycle-free Route 16 Cut lane, HM02 transfer, DUX Fly teaching, Pallet Fly
  destination, Route 21 wild-flee recovery, all nine trainer bypasses, and healed Cinnabar arrival.
- [x] Qualify the one-repel Pokémon Mansion route, all optional-trainer bypasses, Secret Key,
  six correct Gym quizzes, Blaine, TM38, Volcano Badge, and post-battle recovery.
- [x] Qualify Viridian Fly and inventory preparation, the spinner-floor route, six required Gym
  trainers, pre-leader recovery, Giovanni's exact party, TM27, Earth Badge, and Route 22 rival
  activation.
- [x] Qualify Toxic preparation, the final Route 22 rival with bounded live recovery, all Route 23
  badge checks, every Victory Road Strength switch and boulder drop, Indigo healing, and Elite Four
  supplies.
- [x] Qualify Lorelei's exact party, item-cursor recovery, status-aware healing, retained Toxic,
  and a fully healed Bruno-room boundary.
- [x] Qualify Bruno, Agatha, and Lance with exact trainer-party reconstruction, bounded recovery,
  PP-aware move selection, and fully healed room transitions.
- [x] Qualify the Champion with six verified X Special uses, exact six-member party
  reconstruction, bounded recovery, and concurrent Champion-event plus Hall-of-Fame proof.
- [x] Replay every qualified objective across three clean-power-on runs.

The qualified corridors and
semantic gates are pinned to pret/pokered commit
`1e96034092686d006e863cace09e87273051a3d8`. See the
[Hall-of-Fame three-run evidence receipt](evidence/qualified-play-hall-of-fame-2026-07-29.json).

Exit gate met: three intervention-free clean-power-on runs reached the Hall of Fame with identical
evidence.

## Milestone 2 — deterministic expert

**Status: complete — July 2026**

- [x] Complete the route graph through all eight badges, Victory Road, Elite Four, and Hall of Fame.
- [x] Add navigation transitions, menus, inventory, party management, HM/puzzle, battle, and recovery
  specialists.
- [x] Record failure categories, deterministic recovery behavior, and semantic action rationales.
- [ ] Generate clean demonstrations plus corrected trajectories for timing, encounter, battle,
  status, and nearby-position variations. This continues as Milestone 3 dataset work.

Exit gate met: the teacher completed three identical clean runs without save-state restoration.

## Milestone 3 — demonstration learner

**Status: in progress — July 2026**

- [x] Define the versioned, game-neutral semantic trajectory contract and Pokémon Red adapter.
- [x] Add fail-closed, path-free private episode storage for a separately mounted volume.
- [x] Record and integrity-audit the first private clean-start teacher control trajectory.
- [x] Add policy-safe battle move decision spans for the shared adaptive battle runtime.
- [x] Record and audit a clean-start trajectory containing adaptive battle decision labels.
- [x] Add an integrity-checked private episode reader and typed private model-artifact writer.
- [x] Add the pinned Red mechanics projector and slot-equivariant masked battle ranker.
- [x] Run and publish the aggregate first single-lineage battle diagnostic.
- [x] Record explicit physical battle instances, stable route-plan identities, planner goals,
  required-move semantics, and descriptive recovery markers at the policy boundary.
- [x] Add feature schema v2 with `constraint.matches_required_move` and separate free-choice,
  forced-choice, and unobserved-context metrics.
- [x] Preregister five train, two validation, and five test root lineages with immutable,
  single-attempt global and partition-local slots plus content-addressed 69-battle timing
  schedules.
- [x] Bind the registry to exact canonical roster, schedule, assignment, sidecar, executable
  source, teacher behavior, objective graph, and teacher execution identities.
- [x] Make planned recording verify exact battle order, apply each offset once before policy
  inference, emit per-battle and terminal schedule attestations, and fail closed on missing,
  extra, substituted, incomplete, or reordered battles.
- [x] Add a registry-declared, disjoint, unassigned, non-counted 69-battle schedule dry run.
- [x] Add a private campaign seal and immutable outcome ledger that counts complete, failed,
  interrupted, and invalid slot outcomes with durable reasons.
- [x] Pin the exact pushed source commit, live source bytes, CPython binary, and installed PyBoy
  inventory; authenticate schedule events against actual WAIT executions; and add safe campaign
  status/recovery reporting.
- [x] Require a re-audited immutable dry-run qualification before every counted slot and durably
  persist the one-shot episode claim before emulator execution.
- [x] Add a game-neutral six-member party observation contract, derived team metrics, and a
  reusable balanced-training policy, with a Red adapter binding the declared roster.
- [x] Integrate bounded switch-participation training for the route's existing party and replay it
  from clean power through the Hall of Fame.
- [x] Catch Route 12 Snorlax with bounded recovery and capture decisions, raise the live balance
  contract to four members, and qualify all 301 checkpoints through the Hall of Fame.
- [x] Add the Eevee/Thunder Stone/Jolteon acquisition and raise the live training contract to five.
- [x] Add the Hitmonlee acquisition and raise the live training contract from five members to six.
- [x] Replay the six-member balanced-team route from clean power-on and qualify it against the
  completion contract.
- [x] Define the Red one-save/no-link collection contract: 124 obtainable Pokédex registrations,
  120 coexisting living targets, and 27 explicit version, trade, mutually exclusive gift, fossil,
  starter, evolution, or event exclusions.
- [x] Add game-neutral collection planning plus fail-closed Red readers for seen/owned Pokédex
  flags and the visible party/current PC box.
- [x] Add checksum-verified all-box inspection across the active Work-RAM box and both dedicated
  saved-box SRAM banks without exposing raw addresses to the planner.
- [x] Replay the full teacher and publish the first terminal census: 12/124 owned, 85/124 seen,
  7/120 living, and 0/120 at level 100, with all twelve boxes verified.
- [x] Add bounded, transition-verified Bill's PC deposit and withdraw controls, and replace the
  route's one hard-coded helper deposit with the reusable storage specialist.
- [x] Add bounded, verified switch-box control and exercise a reversible Box 1→2→1 cycle without
  losing a stored specimen.
- [x] Replay the corrected contract and storage cycle from clean power through Hall of Fame:
  312/312 checkpoints, 36/36 objectives, storage initialized, all boxes verified, and a terminal
  12/124 registered, 7/120 living, 0/120 level-100 census.
- [x] Add a pinned 124-target acquisition graph with 67 ordinary wild, 11 Safari, 7 fishing,
  17 gift/static/prize/fossil/trade, and 22 evolution methods; prove that its 120 root specimens
  incidentally register every target and derive all duplicate precursors and evolution items.
- [x] Add a bounded semantic source-survey executor that seeks, captures into a full-party PC,
  flees irrelevant encounters, rotates full boxes, verifies one-specimen progress, and stops only
  when the source's downstream quantity requirements are retained; qualify it in ROM-free Route 1
  simulation.
- [x] Bind the source-survey executor to live Route 1 movement, capture menus, Pokédex flags, and
  PC storage, then replay Pidgey/Rattata acquisition through all 312 checkpoints and the Hall of
  Fame from clean power.
- [x] Replace Route 1's chapter-local target loop with the reusable source-survey executor backed
  by global Pokédex, party, and all-box observations; add duplicate-aware source ranking and replay
  the exact 83,835,201-frame / 758,430-action lineage through the complete integration contract.
- [x] Bind the reusable wild-source controller to Viridian Forest; retain Caterpie, two Metapod,
  two Kakuna, and Pikachu; and reproduce the complete 83,619,428-frame / 765,088-action lineage
  twice through all 312 checkpoints and the Hall of Fame.
- [ ] Independently retain one living specimen for all 120 coexisting targets.
- [ ] Implement the remaining map-specific encounter, fishing, Safari, gift, static, prize,
  fossil, trade, evolution, and resource executors for all catalog methods.
- [ ] Qualify the 124-species Pokédex-registration gate, 120-species living-collection gate, and
  120-species level-100 gate as three separate uninterrupted-run claims.
- [ ] Add title profiles for later generations, then measure zero-shot and fine-tuned transfer on
  unseen seeds before claiming support for another game.
- [ ] Build a multi-save, multi-version portfolio contract for species that cannot coexist or be
  obtained in one lineage, with unavailable event/service requirements reported explicitly.
- [x] Add the authenticated five-train/two-validation battle fitting lane: require complete
  one-shot outcomes, leave all five test roots unopened, disclose visible-state overlap and
  novel-visible performance, select a validation-only confidence threshold, and publish a private
  canonical candidate that remains promotion-ineligible until test and rollout evaluation.
- [ ] Commit and push the exact source/configuration state, then successfully complete the 69/69
  schedule dry run before slot `01`.
- [ ] Collect every declared train and validation lineage without opening the test partition.
- [ ] Freeze the selected battle model and thresholds, then evaluate the five test roots once.
- [ ] Record perturbed teacher corrections and recovery trajectories.
- Publish schemas, aggregate statistics, and dataset cards without game assets.
- Train goal-conditioned navigation, interaction, battle, puzzle, and recovery specialists with
  behavioral cloning.
- Evaluate each specialist on held-out seeds and deliberately perturbed semantic states.

Exit gate: learned specialists meet preregistered local reliability thresholds.

The first private control trace contains 41,330 executions, 300 events, and 14,760 deduplicated
policy snapshots across all 299 checkpoints. Its manifest, references, state-hash chain,
provenance, terminal record, and privacy invariants passed audit. See the
[sanitized receipt](evidence/private-trajectory-foundation-2026-07-30.json). It contains no
specialist decision records yet and is not described as a finished behavioral-cloning dataset.

The second private trace adds 422 adaptive battle move decisions across 32 battle locations and
links them to 3,022 contiguous executor actions. Every decision begins at the same step and
policy-snapshot hash as its first execution. The
[sanitized battle-decision receipt](evidence/private-battle-decisions-2026-07-30.json) keeps this
lane explicitly incomplete: custom battle controllers, perturbed corrections, frozen splits, and
learned evaluation remain pending.

The first battle-imitation diagnostic trains a 100-feature shared move ranker on those 422
decisions, grouped into 63 encounter proxies. Five-fold agreement is 72.5% versus a 50.5%
fold-local majority-slot baseline and macro F1 is 0.683. A hard mask makes every prediction a
legal positive-PP choice by construction; that 100% rate is a safety invariant, not a learned
performance result. The
[sanitized diagnostic receipt](evidence/private-battle-imitation-diagnostic-2026-07-30.json) keeps
the claim narrow: this is one unassigned root lineage with inferred groups and incomplete
planner-goal context, not held-out evaluation or a learned gameplay rollout.

Future recordings now have explicit context and are governed by the
[committed collection protocol](collection-protocol.md). Its twelve prospective assignments and
timing schedules have not yet run. Their current v2 feature view distinguishes free move choices
from exact teacher-required choices; future receipts report both separately because forced-choice
accuracy is constraint compliance, not autonomous battle judgment. The recovery marker remains
descriptive only and does not yet define a recovery learner's inputs or budget.

Dataset quality now also depends on party composition. The historical recordings complete the game
with one overleveled lead, which makes most battle labels trivially correct and teaches nothing
about switching or matchup selection. The current branch adds a game-neutral six-member party
contract, derived team metrics, a reusable equal-level policy, and a completion-efficient developed
team policy. The active route catches Snorlax, obtains and evolves Jolteon, recruits Hitmonlee,
verifies that all six members are in their declared final available forms, and trains Blastoise as
the designated workhorse to level 60. An earlier three-member teacher entered Indigo at level 58
and the Hall of Fame at level 61, making 60 an evidence-backed speed target rather than an
assumption that lower levels cannot work. A clean-power six-member replay has now passed all
**312/312 checkpoints** and **36/36 objectives** in **87,020 actions**: 177 Mansion wins raised the
workhorse from 48 to 60, and 24 targeted battles completed the remaining evolution. The prior
levels-82–87 zero-faint proof remains historical route evidence; matching every non-workhorse to
the carry is no longer a collection prerequisite.
See the
[Project Narrative](project-narrative.md) for the reasoning and the outstanding route work.

The protocol also requires a successful, non-counted 69/69 schedule rehearsal before slot `01`,
and its one-shot ledger preserves failures and power interruptions as consumed outcomes. Exact
identity, manifest, assignment, schedule, and lineage reuse is hard leakage. Repeated
policy-visible semantic states are report-only because distinct hidden timing histories can
naturally converge on the same observation; novel-visible-state performance is reported
separately. Preregistration and runtime enforcement are infrastructure, not held-out evidence. The
first Forest-lineage rehearsal exposed a Route 24 moving-NPC collision at checkpoint 38/312. The
repaired crossing passed clean-power qualification and cleared that point under the same schedule;
the second rehearsal then exposed a trapping-move recovery gap at checkpoint 109/312. Neither run
consumed a declared slot. Clean diagnostics have since cleared the repaired tunnel, Tower, and
Sabrina policies, isolated two-turn Fly from the one-turn Mansion grinding contract, and recognized
level-up move replacement as a valid post-attack observation. The combined source passed a new
312/312 clean-power Hall-of-Fame replay and was published before rehearsal. All twelve
slots remain pending, and the test partition remains unopened until a model and its selection
rules are frozen.

The first rehearsal of the published combined source cleared Route 24 and Route 25, then exposed a
remaining Wrap lock at Rock Tunnel checkpoint 109/312. A later uncounted rehearsal exposed an
unsafe low-HP DUX finisher at the same chapter; neither attempt consumed a slot. The current repair
removes that finisher, proves the tunnel potion floor, chooses Bite against Slowpoke after required
move evidence, escapes status-locked DUX matchups, and preserves the legal natural-evolution path.
A surplus Tower Rare Candy now establishes the level-41 TM40 lesson boundary, moving Celadon NPCs
receive neutral retry windows, and the Silph rival receives type-aware Ice Beam plus bounded
whole-battle recovery. The next uncounted rehearsal then proved the DUX status escape but put its
replacement to sleep and exposed that battle healing targeted only party slot one. The current
teacher buys one additional Awakening in Vermilion, reserves one for Tower, and applies both status
and HP recovery to the actual active party index under a two-potion cap. This exact source completed
a clean-power **312/312-checkpoint**, **36/36-objective** Hall-of-Fame replay in **771,022 actions**.
Its six-member Mansion curriculum exceeded **4,000 wins**, retained a level-77 floor, and passed the
bounded spread contract. Registry freeze and the next uncounted 68-battle rehearsal are the current
gates. The following rehearsal cleared Rock Tunnel but exposed a $200 restock deficit from the
additional schedule-specific recovery. The teacher now sells the unused, already-proven TM28 for
$1,000 before restoring the full downstream reserve; no counted slot was consumed.
That repair moved the rehearsal to checkpoint 202/312, where Koga Gym Juggler 4 fainted the lead.
The current teacher pivots at the 50-HP floor to the healthiest living reserve and uses that active
party member's own legal moves. Another uncounted rehearsal is required before collection opens.
That change advanced the route to Sabrina at checkpoint 261/312, where the Hyper Potion verifier's
24-frame settle window expired during the opponent reply. The shared battle-item primitive now has
a bounded 720-frame cancel-safe window and richer failure evidence. Rehearsal remains the gate.
That repair passed Sabrina and carried the balanced curriculum beyond 1,250 battles, where live PP
exhaustion or Disable removed every preferred attack. The current adapter hands control to the safe
escort, flees without a faint, and lets the game-neutral planner request restoration. Another exact
uncounted rehearsal then completed **312/312 checkpoints** and entered the Hall of Fame, proving
the scheduled gameplay route. Its episode remained unpromoted because wild curriculum battles had
no explicit training intent and repeated progress events reused an identity. The lossless-data
repair labels each wild decision, closes externally fled battle instances, and keys progress to
the execution step. No counted slot was consumed; the repaired exact source must repeat the
uncounted rehearsal before collection opens. That replay again completed **312/312** and Hall of
Fame, with lifecycle and progress loss reduced to zero and 4,789 move labels accepted. The only
remaining 209 rejections were early switch-training choices: Blastoise was active, but the snapshot
still described the weak field lead. The adapter now projects the controlled battler during battle
and the field lead outside battle. A newly frozen exact-source rehearsal remains the gate.
The newest rehearsal cleared the former Route 9 continuation failure and reached Koga at checkpoint
205/312. When the workhorse fainted with a living opponent and a healthy party behind it, the boss
adapter still stopped as though the run used a single carry. Koga now selects the healthiest living
teammate through the observed forced-party menu, ranks that member's legal live-PP moves, caps KO
handoffs by party depth, and records the continuation separately from mutual-KO recovery. The
post-battle Center proof still requires the complete party restored. The run was uncounted; the
republished source must pass the full rehearsal before slot 01.
That continuation defeated Koga and the Center restored the complete party, but the Strength input
gate then found Skull Bash in Blastoise's first move slot. The recorded transition proved level 42
was reached while fighting Muk and the natural move prompt replaced Bite, which is reserved for the
later controlled TM40 lesson. Koga now assigns Muk to the healthiest living teammate before the
workhorse selects an attack, preserving both the staged lesson and the no-faint tactical objective.
The uncounted run stopped at 208/312; v10 remains unopened.
The next replay handed Muk to Snorlax, but that reserve later fainted and Blastoise returned to win
at 14 HP, leaving the same natural level-42 move branch possible. Strength and Erika now preserve
two exact legal lineages: Bite followed by the controlled TM40 lesson, or natural Skull Bash
followed by archival of the redundant TM40. Both must converge on the same post-Erika moves and PP,
and Koga's Center gate must restore every member after any recorded continuation. The rehearsal was
uncounted; v10 remains unopened.
The combined source subsequently qualified v10 at **312/312**, **36/36**, Hall of Fame, and
**68/68** scheduled battles. Its first fresh counted root failed at Misty with the one-member party:
Wartortle fainted at 0/64 before a finishing attack and Starmie retained 10/59 HP. That immutable
outcome is sealed and v10 is retired. V11 rehearses on exposed seed `20001`, uses entirely fresh
counted seeds, and lets Misty spend only the live Potion surplus above the four-Potion Rocket
reserve under exact low-HP, heal, inventory, and same-intent gates.
The exposed-seed v11 rehearsal cleared Misty, then found two later generalization boundaries while
remaining uncounted. Route 10 could report field input between the nurse's final text boxes; a
bounded CANCEL-only normalization now proves the exit stance without reopening the heal dialogue.
At Koga, Muk's Minimize/poison stall eventually exhausted all four available party members despite
legal forced-switch continuation. The revised lesson uses the carried Tower X Accuracy on
Blastoise when Muk appears, directly counters the accuracy mechanic, and replaces that single
consumable during the already-qualified Celadon battle-item purchase. The complete source must
still pass all 312 checkpoints and 68 scheduled battles before v11 collection opens.
V11 subsequently qualified all of those gates, but fresh counted seed `21001` stopped after the
Nugget Rocket when a moving Cerulean Mart customer held the repeat clerk approach at `(4, 5)`.
That one-shot failure is sealed and v11 is retired. V12 uses the exposed seed only for rehearsal,
waits for verified westward progress inside the safe Mart corridor, and assigns fresh train seeds
`22001`–`22005`, validation seeds `32001`–`32002`, and test seeds `42001`–`42005`.
The first v12 rehearsal passed that collision boundary and reached checkpoint 86, but the capture
settling loop crossed the battle MAIN menu between observations and selected a second Poké Ball.
Post-throw dialogue now uses CANCEL, which advances text while remaining inert on MAIN. The failed
artifact is uncounted, every v12 collection slot remains pending, and the exact repaired source
requires a new complete qualification.
The capture-safe replay proved checkpoints 87–91, then the later Route 1 semantic survey was
blocked below the source-defined horizontal youngster at `(14, 14)`. A 24-attempt maneuver now
steps east, waits, restores the exact approach, and retries only the northward crossing. Any map,
battle, or coordinate outside that bounded gate still fails closed. This second v12 artifact is
also uncounted and does not open collection.
The walker-safe replay reached checkpoint 102, where the live capture bill left a ₽2,109 Tunnel
supply shortfall but only five obsolete Potions. The route now earns ₽1,260 from the nearest
source-pinned Route 11 Gambler and liquidates unused TM24 for ₽1,000 before buying supplies. The
Gambler is a new scheduled battle, raising the exact roster from 68 to 69; its payout, identity,
event, return route, and no-item-recovery boundary are all verified. The fixed ten-Super-Potion,
three-Awakening, three-Parlyz-Heal, and four-Repel contract is unchanged.
That exact rehearsal subsequently validated every earlier repair through checkpoint **296/312**,
including the six-member balance gate, Blaine, Giovanni, the final rival, and Victory Road. It then
exposed a stale Indigo inventory assertion: the now-larger bounded capture curriculum may legally
consume all thirty Poké Balls, while cleanup required one leftover solely to enter a sale helper.
Zero is now an explicit valid remainder, the zero-quantity sale is skipped, and exact Elite Four
supplies remain the terminal proof. The run was uncounted; a fresh source-bound rehearsal remains
the collection gate.
The first replay of that correction accepted zero but selected the wrong shop item because the
zero-sale branch remained at field control while the positive-sale branch had returned through
SELL. Indigo preparation now uses an explicit two-state transition: INTERACT from the zero-remainder
field state, or CANCEL from a completed positive sale, followed by the same verified BUY selection.
That replay was also uncounted; the newly frozen source must qualify from clean power.
The corrected source subsequently passed **312/312**, **36/36**, Hall of Fame, and **68/68**
schedule audit, opening v2. Its first one-shot train root then failed at checkpoint 62 when the
Rocket thief's Drowzee knocked out Wartortle at 0/66 HP with 24/50 enemy HP remaining. The immutable
v2 ledger retains that failure, so v2 cannot provide five complete train roots. The next teacher
keeps a fifth Potion through Route 24, a fourth through Route 25, conditionally spends the third at
a bounded Rocket-thief recovery gate, and hands the original two-Potion reserve to Route 6. After the required
fresh Bite, it ranks Mega Punch before weaker cleanup attacks. A fresh-seed v3 campaign is now the
qualification target; v2 will not be retried.
The first uncounted v3 qualification attempt then reached checkpoint 44 with Wartortle at 2/56 HP
before the Nugget Rocket's Ekans trapped and fainted it. The route already reserved the needed
Potion but spent it after victory; that same recovery now occurs before the battle and preserves
the four-Potion Route 25 boundary. All counted v3 slots remain untouched pending a complete replay.
The next replay cleared that fight and survived checkpoint 62 without needing the in-battle Rocket
Potion, but the exact-one-use assertion rejected the safer outcome. Recovery is now conditional;
an unused allowance carries forward as bounded surplus instead of being wasted to normalize counts.
That repair passed both Rocket boundaries and reached checkpoint 69, where Route 6 repeated the
same mandatory-use mistake after a safe victory. Route 6 now shares the conditional rule and
protects a one-Potion minimum while preserving any surplus for S.S. Anne. The next replay reached
the S.S. Anne rival at checkpoint 79, where one Potion could not survive Ivysaur. That battle may
now spend the carried bounded surplus at recurring live low-HP gates under one stable intent.
The resulting replay cleared S.S. Anne and Surge and reached checkpoint 109, where a status-locked
DUX pivoted correctly but Wartortle used resisted BubbleBeam against Bulbasaur until its recovery
limit was exhausted. Bulbasaur now shares the Grass-matchup policy, selecting neutral Bite after
the role handoff instead of compensating for poor attacks with a larger heal cap.
That replay survived the prior fight but reached B1F trainer 4 still paralyzed; Wartortle selected
BubbleBeam, lost the turn, and the opponent self-destructed before PP could prove execution. The
route now cures status before the Hiker sequence and carries a second Parlyz Heal for the later
Grass contingency, retaining both the win contract and an executable curriculum label.
That replay cleared the complete tunnel and Pokémon Tower, then exhausted ten Great Balls and all
remaining Poké Balls at the one-time Route 12 Snorlax. The funded static-capture budget is now
twenty-five combined balls with a thirty-three-throw total bound; unused stock is sold afterward, and success no longer
depends on lucky leftovers from earlier species searches.
The first thirty-ball proposal failed closed at the Mart: ₽16,897 could not fund the ₽19,400
capture-plus-healing bill. Twenty-five balls plus both Super Potions cost ₽16,400, preserving
healing and future-use TMs while exceeding the previously exhausted eighteen-throw lineage.
The funded replay caught Snorlax in six throws and advanced through Koga to the Celadon Gym
trainers, where a Center NPC occupied the first exit tile beyond eight bounded waits. The existing
release-and-observe movement primitive now covers sixteen waits, preserving the route while
allowing a full longer NPC cycle to vacate the tile.
The replay proved that sixteen waits can still leave the NPC parked. The second Center exit now
uses the legal side corridor around that occupied tile and rejoins the same doorway below it,
removing NPC timing from this transition while retaining collision and destination checks.

The repaired v3 lineage ultimately completed **312/312 checkpoints**, **36/36 objectives**, Hall
of Fame, and **68/68** schedule attestations with a level-75–81 balanced party. Its first immutable
training root then exposed a different Route 24 failure at checkpoint 42: Sand-Attack reduced
accuracy, Nidoran poisoned Wartortle, and repeated Water Gun misses allowed the 4-HP opponent to
outlast the lead. V3 is retired with that one-shot failure preserved. V4 uses the exposed v3 seed
as its uncounted rehearsal, heals immediately before the accuracy battle, and permits one bounded
Potion recovery without reducing the four-Potion downstream reserve. V4 later qualified but its
first immutable training root failed at the final bridge trainer, so it is retired. V5 adds a
Center recovery before that fight and freezes twelve fresh counted seeds pending a complete
312/312 and 68/68 rehearsal.

## Milestone 4 — DAgger and selective RL

- Collect teacher corrections on learner-induced states.
- Use snapshot curriculum RL only for skills below their imitation gates.
- Freeze and promote specialists independently.
- Train a semantic planner to select objectives and specialists without raw-memory or
  demonstration-index inputs.
- Exercise recovery from displaced positions, unexpected encounters, damage, status, and shifted
  timing.

Exit gate: a learned skill stack completes a held-out clean-start run with teacher fallback
disabled and no save restoration.

## Milestone 5 — distilled completion

- Train a local goal-conditioned macro-policy from qualified demonstrations, perturbations, and
  learner corrections.
- Remove the deterministic router while retaining the objective graph, safe executor, and referee.
- Run a preregistered held-out multi-seed clean-start evaluation series with teacher fallback
  disabled.

Exit gate: at least one verified completion; reliability requires at least 8/10 preregistered runs.

## Milestone 6 — cross-game transfer

- Freeze a Pokémon-mainline semantic ontology that excludes revision-specific privileged state.
- Implement a second game adapter without changing the shared policy interfaces.
- Measure zero-shot behavior, few-shot adaptation, and training from scratch on the same tasks.
- Progress from a closely related title to a later-generation title only after the transfer
  protocol and leakage controls pass review.

Exit gate: a model reuses Pokémon Red training to reach preregistered objectives in a held-out
Pokémon title with less new data than the from-scratch baseline.

## Evidence lanes

Results remain separate throughout the project:

1. **Exact teacher repeat:** the frozen deterministic teacher repeats a clean route from power-on.
2. **Perturbed teacher coverage:** the teacher is measured across preregistered timing/RNG seeds
   and reports the encounter, damage, status, recovery, and position variation actually observed.
3. **Learned multi-seed policy:** the learned/hybrid actor receives semantic observations and runs
   held-out seeds with teacher/oracle fallback disabled.

All full-game evaluation lanes count every declared attempt and forbid save-state restoration.
Snapshot-based perturbation suites remain component-training evidence, not completion evidence.
Only the third lane supports a claim about learned generalization, and that result has not yet
been achieved.

Current collection gate: v12 completed its clean 312-checkpoint rehearsal, then its first counted
training schedule exposed the moving S.S. Anne waiter at `(8, 6)`. The failed root is sealed and
v12 is retired. V13 contains the bounded corridor-yield repair and entirely new rehearsal,
training, validation, and test schedules; its rehearsal must qualify before collection restarts.

V13 later qualified, but its first counted root exposed an exhausted-Full-Heal assumption after
Agatha. That root is also sealed. V14 carries the inventory-aware Full Restore fallback and fresh
rehearsal/training/validation/test schedules; no v14 formal slot opens before qualification.

V14's first rehearsal remained uncounted and stopped at checkpoint 112: three held-out sleep cures
exhausted Rock Tunnel's old three-Awakening plan. The reserve is now four, with exact funding and a
one-item Pokémon Tower carry-forward gate. Full qualification remains the current prerequisite.

The next replay reached checkpoint 309 after defeating Lance, then correctly rejected a zero-count
Champion Full Restore reserve. Indigo now overprovisions six Full Heals so status contingencies do
not consume the protected HP-recovery item. The v14 rehearsal must still prove the final three gates.

V14 did qualify all 312 checkpoints, but its first counted seed exposed an unavoidable fast-Dugtrio
knockout during the single-member pre-ship grind. That campaign is sealed. V15 relocated this one
development lesson to lower-level Route 11 grass and used wholly fresh schedules.

V15 then qualified all 312 checkpoints with the balanced party, but its first counted seed exposed
a missing disabled-move exclusion during the Route 11 lesson. The failed outcome is sealed. V16
adds that semantic action gate and receives a new rehearsal and entirely new counted schedules;
full qualification is again required before any v16 training slot opens.

V16 qualified **312/312 checkpoints**, **36/36 objectives**, and **69/69** scheduled battles. Its
first immutable training root reached the Champion's final Venusaur before failing at checkpoint
311. The controller had spent Blizzard against earlier neutral matchups; after the Champion used
Full Restore, Blastoise exhausted its effective Ice coverage and the lower-level final-form
reserves could not finish. V16 is sealed with one failed train root and eleven unopened roots. V17
uses that exposed schedule only for its uncounted rehearsal, assigns fresh counted schedules, and
teaches matchup-aware resource planning: physical damage for Alakazam and Gyarados, Surf for
Rhydon and Arcanine, and Blizzard reserved for Venusaur.
