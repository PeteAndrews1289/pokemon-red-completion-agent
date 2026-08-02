# Teaching and data plan

## Teacher role and final goal

The deterministic player is the project's disclosed reference policy: it proves semantic gates,
supplies demonstrations, labels corrections, and provides a safety baseline. The final goal is
different: a learned/hybrid actor must decide what to do from semantic observations when it sees
unseen timing/RNG schedules and variable positions, encounters, damage, or status. Replaying the
teacher route, even perfectly, does not establish that capability.

## A complete run is not the starting requirement

The deterministic teacher can be built and verified one chapter at a time. It needs an exact ROM,
route knowledge, maps and transitions, semantic state predicates, bounded controller routines, and
recovery rules. It does not need a human video or an existing Hall-of-Fame trajectory to begin.

A complete clean teacher run is this project's promotion gate before:

- calling the deterministic teacher finished;
- training or evaluating a student on full-game composition; or
- promoting the learned stack to official full-game evaluation.

This is a project policy, not a logical claim that another system could not complete the game
without a teacher completion. Any completion claim still stands or falls on the frozen evaluation
contract and its own clean-run evidence.

One successful trace is also not enough for reliability. It contains little evidence about wrong
turns, shifted menu cursors, battle variance, blackouts, or other learner-induced states.

## Reference stack

The teacher may use these disclosed references:

1. the repository's 36-objective dependency graph;
2. a deliberately safe route for starter, team, items, HMs, healing, and badge order;
3. collision maps, warps, interactions, and declared read-only symbols;
4. bounded preconditions, success predicates, timeouts, and recovery rules for every skill; and
5. the predecessor's public clean-power-on bootstrap routine.

The bootstrap sequence was adapted from
[`pokemon-red-ai`](https://github.com/PeteAndrews1289/pokemon-red-ai) commit
`0e2df37720eec7d148187eb1001bf2d9502aa4f6`. Private blind-run checkpoints and screenshots are not
completion demonstrations and are not loaded by this project.

The qualified bedroom-to-Celadon route is new successor work. Its map dimensions,
collision-safe corridors, warps, Pallet Town, Route 1, Viridian Forest, Pewter Gym, Route 3, Mt.
Moon, Nugget Bridge, Route 25, Bill, Cerulean Gym, Route 5, the Underground Path, Route 6, the
Vermilion harbor, S.S. Anne, Route 11, Diglett's Cave, Vermilion Gym, Route 9, Route 10,
Rock Tunnel, Lavender Town, Route 8, the west-east Underground Path, Route 7, and Celadon City, and
story, party, battle, badge, fossil, and inventory gates are derived from
[`pret/pokered`](https://github.com/pret/pokered) commit
`1e96034092686d006e863cace09e87273051a3d8`, then independently exercised against the exact
supported ROM. The teacher checks the resulting semantic phase after each bounded action rather
than treating the source route as proof of runtime success.

## Current qualified teaching segment

The deterministic teacher now verifies all **299/299 qualified checkpoints** and **36/36
completion objectives** through the Hall of Fame. Three clean-power-on runs were identical at
4,796,436 frames and 41,316 actions, without save-state restoration or human input. The terminal
gate requires the Champion-defeated event and Hall-of-Fame map concurrently. The evidence includes
the earlier Brock and Mt. Moon gates,
the live Cerulean rival and required Route 24/25 trainer identities, Bill's complete story and
S.S. Ticket sequence, the mandatory Gym trainer, Misty's live identity, and concurrent Cascade
Badge and TM11 proof, plus the Rocket thief, TM28, Underground Path, exact Route 6 trainer events,
three explicitly verified wild-flee recoveries, the live S.S. Anne rival, and concurrent raw
Captain-rub event, HM01 event, inventory, and derived Cut-fact gates. The Surge segment adds
bounded Spearow capture and the DUX trade, a source-valid Diglett Ground specialist with natural
or exactly consumed TM28 Dig, the live variable `D743`/`D744` electric-lock puzzle, and concurrent
Surge victory, TM24, Thunder Badge, mirrored badge, restored-lead, and released-control proof.
The Lavender segment adds exact BubbleBeam and supply gates, 11 mandatory Route 9/Rock Tunnel
trainer identities with selected-move PP evidence, bounded sleep and wild-flee recovery, an
optional Route 10 trainer bypass, and a full three-member Center heal. The Celadon segment adds
the exact required Route 8 Lass identity and event transition, eight optional-trainer bypasses,
the west-east Underground Path crossing, exact resource preservation, and a second full-party
Center heal.
The Erika segment adds the complete collision-qualified reverse traversal from Fuchsia through
Routes 15–12 and the west-east Underground Path, explicit wild-flee recovery, tile-transition
and input-readiness gates for every Cut and re-Cut, the two unavoidable Gym trainer identities,
Erika's live identity, six Strength attacks, Rainbow Badge and TM21 mirrors, all seven deactivated
Gym trainer events, and the natural level-42 Bite-to-Skull Bash transition before a final full
Celadon Center heal.
The Saffron segment adds the exact Department Store floor and stair sequence, roof vending cursor
zero, one ¥200 Fresh Water purchase, exact reverse stair sequence, and a zero-battle Route 7 gate
crossing. It separately observes Fresh Water removal while the shared guard flag is still false,
then verifies that the flag becomes true only after dialogue completes. Soda Pop and Lemonade
remain absent, the transient drink leaves no final inventory delta, and the terminal is a fully
healed, input-ready Saffron Center boundary.
The Hideout segment adds five exact trainer identities, eight optional-trainer bypass gates,
the Lift Key and elevator, Giovanni, the Silph Scope, a PP-preserving field Dig return, and a
second healed Celadon boundary. It also records the pinned source's known B1 entered-event bug.
The Tower segment adds the exact scripted rival, five required Channelers, level-30 Marowak, three
final Rockets, eight optional-trainer bypasses, three purified-zone heals, X Accuracy and Rare
Candy progression pickups, both Fuji rescue mirrors, the Poké Flute, and the natural
Wartortle-to-Blastoise evolution. The boundary has a full-health, status-free Blastoise restored
as party lead. The Fuchsia segment adds the exact Route 12 Snorlax wake/defeat/object transition,
four mandatory Route 12/13 trainer identities, 35 optional-event and five optional-item bypasses,
four bounded wild flees, and a disclosed resource-neutral Lavender recovery before the healed
Fuchsia boundary. The Safari segment adds the exact one-admission fee and counters, the correct
North-to-West elevation transition, six RUN-only encounters without catches or Ball use, Gold
Teeth and reusable HM03 rewards, slot-four Water Gun replacement with Surf, and source-authorized
Time's Up cleanup before another healed Fuchsia boundary. No behavioral-cloning, DAgger,
timing/RNG generalization, or full-game result is implied. The Koga segment adds the exact three
mandatory-trainer minimum, two Center recoveries, six-trainer post-victory deactivation, Koga's
live identity, Soul Badge raw and mirror bits, retained TM06, and a final healed Fuchsia boundary.
Koga must precede the return to Erika here: Route 15 is one-way eastbound, Cycling Road requires
the Bicycle, and field Surf requires the Soul Badge.
The Cinnabar segment uses Route 16's upper Cut lane without a Bicycle, consumes the retained Rare
Candy to make one bag slot, proves the HM02 item/event transfer on the same dialogue pulse, teaches
Fly over DUX's obsolete Leer, and verifies the default Pallet destination. From Pallet it activates
Surf, follows a 93-move Route 21 corridor, safely flees one Rattata and two Tentacool encounters,
leaves all nine optional trainer events false, and terminates healed and input-ready in Cinnabar
Center.
The Strength segment returns the Gold Teeth to the Warden, verifies the Teeth-removal event before
the HM04 reward event, retains reusable HM04, and teaches Strength over obsolete Tail Whip while
preserving Bite, BubbleBeam, and Surf. It then returns to the same healed Fuchsia boundary without
spending money or entering battle.
The Silph segment buys a bounded Max Repel and Hyper Potion reserve, uses the live Celadon roof
sprite position to obtain TM13 without claiming the other rewards, teaches Ice Beam over
BubbleBeam, and follows the source-pinned Card Key and warp route. It verifies the required 5F and
3F Rockets, both unlocked doors, rival, 11F Rocket, Giovanni, and Master Ball events; leaves the
optional Lapras untouched; and returns with a healed, status-free party to Saffron Center.
The Sabrina segment live-qualifies the warp-pad sequence while all seven regular-trainer events
remain false, then verifies Sabrina's exact identity and four-member party. Strength handles the
three Psychic targets while Ice Beam handles Venomoth; the run uses no potion, suffers no faint or
persistent status, receives TM46 and both Marsh Badge lanes, observes all seven post-victory
trainer toggles, and returns fully healed to Saffron Center. The Cinnabar segment obtains Fly,
reaches the island through Pallet and Route 21, and then uses a one-repel Mansion route with all
six optional trainer events untouched. It verifies the three statue-switch transitions, Secret
Key inventory, all six source-correct quiz answers, Blaine's exact party and Surf-only policy,
TM38, the victory event, both Volcano Badge lanes, and a fully healed terminal state. The next
segment flies to Viridian, sells TM46 to reserve the TM27 slot, and proves the exact six-trainer
spinner-floor route. Strength and Ice Beam preserve Surf for the leader; a bounded Center return
restores health and PP before Giovanni. The run then verifies Giovanni's five-member party,
Surf-only policy, TM27, both Earth Badge lanes, both Route 22 rival events, all eight post-victory
trainer toggles, and a fully healed eight-badge Viridian terminal. The next segment crosses Route
22, Route 23, and Victory Road. The Elite Four segment verifies each exact trainer party, uses
semantic HP, status, PP, and enemy-position gates for bounded recovery and move selection, and
performs the required between-room move changes. The Champion segment consumes six verified
X Specials, reconstructs the exact six-member party without mistaking trainer healing for a
switch, and terminates only after concurrent Champion-event and Hall-of-Fame verification.

The same segment can run headlessly or be observed locally with:

```bash
pokemon-red-completion play --watch --speed 4
```

Watch mode does not provide a human controller, record the screen, expose the ROM path, load a
save, or change the teacher. It renders the same bounded execution while checkpoint progress is
printed to the terminal.

## Party composition and what the demonstrations teach

The qualified segment above completes the game with one overleveled lead. That satisfies the
completion contract, but it degrades every dataset derived from it: when a single member outclasses
every opponent, the teacher's move label is almost always "use the strongest attack," and the
switching, matchup, and resource decisions a learner needs to acquire never appear in the data.
A single carry also concentrates all route risk in one Pokémon, which is how the first held-out
schedule rehearsal ended at Route 25.

Teaching therefore targets a **balanced six-member party** instead:

- acquire and retain six members with complementary roles;
- train every final member to at least level 50 and satisfy the five-level spread before the Elite
  Four (the current Mansion specialist separately targets level 55 for its active trainee);
- always train the lowest-level suitable member;
- hold the party within a five-level spread at major training boundaries; and
- permit temporary deviations only when progression requires them, with the reason recorded.

## Collection curriculum and multi-game north star

The curriculum uses four cumulative, independently reported tiers:

1. **Finish** — complete the story and reach the title's verified terminal.
2. **Master** — finish with reusable party, battle, recovery, navigation, and resource skills.
3. **Complete** — satisfy the title-specific 100% contract, including every legitimately
   obtainable species and supported optional objective.
4. **Perfect collection** — retain every species that can coexist in the declared save lineage and
   train every retained specimen to level 100.

This ordering makes level 100 a genuine completeness proof without letting brute-force experience
grinding masquerade as the ability to understand a new game.

The balanced Hall-of-Fame route is the prerequisite, not the final collection target. After that
route qualifies, Red gains a separate completionist curriculum that surveys every encounter area,
catches every species legitimately obtainable in the supported Red cartridge, performs every
available evolution, manages the active party and PC as one living collection, and trains every
coexisting target to level 100. Trade- and version-exclusive gaps are reported explicitly rather
than silently claimed as solo-cartridge completions.

For the declared Squirtle, Helix Fossil, Hitmonlee, and Jolteon lineage, the executable contract
partitions all 151 National Pokédex entries into 124 obtainable registrations and 27 named
exclusions. Four registered earlier forms cannot coexist after evolving the route's unique
Squirtle, Eevee, and Helix Fossil specimens, so the living and level-100 gates use an honest
120-species denominator. Progress is deliberately reported through three non-interchangeable
gates: registered as owned in the Pokédex, presently retained as a living specimen, and presently
retained at level 100. The Red
adapter now reads the Pokédex and performs a checksum-verified census of the party plus all twelve
PC boxes. It overlays the active Work-RAM box on the saved-box banks exactly as the game does and
treats the other eleven boxes as logically empty before the game's first box change. The latter
two gates are therefore measurable, but remain false until the actual collection and training
curricula satisfy them.

The Red acquisition adapter now gives every one of the 124 registration targets exactly one
canonical method at the pinned pret/pokered revision: 67 ordinary wild sources, 11 Safari sources,
7 fishing sources, 4 gifts, 5 static encounters, 2 Game Corner prizes, 2 fossils, 4 in-game trades,
and 22 evolutions. Starting from the 120 living targets and propagating every evolution/trade
dependency produces **120 root specimens across 98 source species**. This catches subtle duplicate
requirements that “one of each” misses: two Pidgeotto, two Spearow, two Abra, two Slowbro, three
Poliwhirl, and three Dratini. It also derives the finite stone budget—3 Moon, 2 Leaf, 3 Water,
1 Fire, and 1 Thunder Stone—before route execution can consume an irreplaceable resource.

A bounded semantic area executor now consumes that graph. It seeks encounters, captures only a
species still required at that source, flees non-progress encounters, catches into verified PC
space when the party is full, switches boxes before the next search when needed, and proves each
capture increased the coherent living census by exactly one. Its Route 1 simulation covers the
complete Pidgey/Rattata loop and a Box 1→2 rotation. This is ROM-free executor qualification, not
yet evidence that the live game traversed and captured those two species.

Level-100 collection is deliberately a separate teacher mode. It supplies abundant capture,
storage, evolution, resource-restocking, and long-horizon grinding examples, but ordinary learner
evaluation retains level caps and variable matchups so overwhelming levels cannot substitute for
battle competence.

The project north star is a learned/hybrid agent that can reach a declared 100% contract across
every technically supported main-series Pokémon title. Shared policies own exploration, battling,
catching, party building, grinding,
evolution, inventory, economy, recovery, and collection planning. Generation adapters describe
mechanics such as abilities, breeding, and battle-system changes; game adapters provide maps,
encounters, story dependencies, puzzles, and title-specific optional objectives. Transfer is
measured by how much less title-specific teaching the next game requires, not by assuming Red's
exact route will solve it. Each title publishes exclusions for requirements that cannot be
performed in its evaluation environment, such as unavailable events or retired online services.

“Every Pokémon game” is not one universal ROM script. Each supported title must pass four frozen
evaluations: story completion on unseen seeds, its published perfect-save contract, its maximal
coexisting level-100 collection, and transfer efficiency relative to training from scratch. A
portfolio layer may combine multiple legitimate save lineages and versions for all-species
coverage, but it cannot retroactively turn an unavailable event into a completed objective.

The rules are expressed against the game-neutral party contract—membership, species, active-party
position, level, health, status, moves, power points, experience, and the derived team metrics—so
the same policy can be evaluated in a second title behind a small adapter. Only the species
bindings are Red-specific.

The declared Red roster is Blastoise, Dugtrio, DUX (Farfetch'd), Jolteon, Snorlax, and Hitmonlee,
bound respectively to the lead-attacker, speed-control, field-utility, special-sweeper,
bulky-absorber, and physical-sweeper roles. Any substitution must record why it was made; the
roster type rejects an unexplained one.

The live integration now catches Route 12 Snorlax, receives Eevee, evolves Jolteon, defeats the
five Fighting Dojo trainers, chooses Hitmonlee, and rotates all six members through bounded switch
participation. Its clean-power proof meets the level-floor and spread contract at levels 82–87
with zero faints and reaches the Hall of Fame through 312 checkpoints. The deterministic teacher
is therefore ready to generate the finalized six-member demonstrations; the learned policy has
not yet earned a completion claim.

Existing recorded demonstrations still describe single-carry play because the new balanced
lineage has not yet been collected. Any dataset card derived from those recordings must say so.

## What each learning stage needs

### Behavioral cloning

Action-aligned examples for individual skills:

- policy-observable semantic state plus a separately stored teacher objective label;
- macro-action plus button press/release duration;
- resulting observation and event delta;
- success, retry, recovery, or terminal label; and
- both nominal and deliberately perturbed starts.

Hidden story flags and completion-referee evidence may label examples, but they are never model
features. Dataset exports keep the policy view and privileged annotation view separate and test
that changing annotation-only state cannot change the policy observation hash.

Perturbations cover nearby legal positions, menu cursor state, encounter identity and timing,
remaining HP and PP, damage rolls, status conditions, inventory/resource differences, and initial
or inter-action timing offsets. Training snapshots may create targeted component states, but they
are never counted as clean-start completion attempts.

### DAgger

A queryable teacher, not a fixed recording. For learner-visited states the dataset records the
learner action, teacher correction or abstention, disagreement, confidence, intervention, and
reason. This supplies recovery examples that a perfect-path movie cannot.

### Selective reinforcement learning

Private snapshots may seed bounded skill curricula during training only. They are never valid
official-evaluation starts. RL is reserved for measured weaknesses that remain after imitation and
DAgger rather than applied to the entire game at once.

## Private trajectory schema

Three versioned artifact types remain outside Git:

- **Episode manifest:** ROM, source bundle, teacher behavior, objective graph, execution, registry,
  assignment, schedule, runtime, and policy hashes; assistance class; global and partition-local
  slot ordinals; seed; start type; outcome; terminal reason; attempt denominator; and completion
  evidence.
- **Decision table:** emulator frame; structured observation; objective and skill; macro and
  primitive action; duration; teacher label; next-state hash; event delta; v2 battle policy
  context; and a descriptive recovery marker.
- **Sparse event log:** map, objective, badge, party, item, battle, checkpoint, recovery, and
  terminal transitions. Scheduled runs additionally record one
  `battle_start_offset_applied` attestation for each of the 68 stable battle IDs and a terminal
  68/68 schedule attestation.

Recorder v1 uses canonical JSONL for inspectable, append-only episode streams. Columnar Parquet
training views are derived from validated episodes later; they are not the source of record.
Screens, ROMs, saves, snapshots, and recordings remain private and content-addressed.

A separate private campaign seal binds the registry, exact pushed source commit, live source
bundle, behavior, objective graph, teacher execution, CPython/PyBoy runtime, ROM, and full slot
roster before the first counted slot. Immutable per-slot outcome records and
a path-free ledger preserve `complete`, `failed`, `interrupted`, and `invalid` results with their
rationales. An orphan partial after a power loss becomes `interrupted` unless reconciliation can
prove that a complete valid manifest had already been written.

The recorder audits the durable episode before reporting success: each positive battle offset must
link to its exact WAIT execution and frame count, while a zero offset must not invent an execution.
The campaign status command can reconcile the same artifacts after a power loss without beginning
a new slot.

The successful non-counted rehearsal publishes a separate immutable qualification bound to its
source, runtime, ROM, schedule, episode, manifest, and 68/68 audit. A counted slot cannot create its
campaign seal or episode namespace until that qualification is reopened and re-audited. The slot's
partial episode directory is then synchronously persisted before emulator execution begins, making
the one-attempt claim durable across power loss.

The battle feature view is `pokemon.core.battle.move-ranker.v2`. It retains the inference-available
goal and move-policy context and adds `constraint.matches_required_move`. Exact-required and
free-choice decisions are counted and scored separately. The `teacher_recovery_marker` is
descriptive only: it is not a model feature, recovery budget, or sufficient recovery-policy label.

## Staged policy build

1. Qualify each deterministic chapter from clean power-on and log semantic demonstrations.
2. Re-run qualified chapters under declared timing/RNG schedules; collect natural encounter,
   damage, status, resource, and route deviations.
3. Add targeted training-only perturbations and record teacher recovery or abstention.
4. Train and freeze goal-conditioned navigation, interaction, battle, puzzle, and recovery
   specialists independently.
5. Roll out the learners, aggregate teacher corrections with DAgger, and reserve selective RL for
   specialist failures that remain after imitation.
6. Train a planner that selects objectives and specialists from semantic state, not raw addresses,
   frame numbers, trace indices, or privileged teacher state.
7. Compose the frozen planner, specialists, action masks, executor, and referee; evaluate it with
   teacher fallback disabled.

The deterministic objective graph, action executor, and referee may remain as declared safety and
verification infrastructure. A hybrid-policy result is learned only when no teacher or oracle
chooses or replaces the actor's actions.

## Evaluation sets and reporting

Evaluation seeds are preregistered harness schedules for timing and perturbation; they are not a
claim that Pokémon Red exposes a user-selectable seed. Training, tuning, and held-out seeds are
disjoint.

Before collection, the exact source/configuration/registry commit must be committed and pushed.
The registry's disjoint, unassigned, non-counted schedule dry run must then complete and attest all
68 battles before slot `01`. It is excluded from train, validation, test, and every performance
denominator.

- **Exact teacher:** repeat the frozen clean-power-on route and report its own attempts,
  checkpoints, actions, frames, recoveries, and terminal reasons.
- **Perturbed teacher:** run preregistered timing/RNG schedules without restoration and report
  outcomes stratified by observed encounters, damage, status, displaced positions, and recovery.
- **Learned multi-seed:** run held-out clean starts with frozen weights and configuration,
  teacher/oracle fallback disabled, and every attempt counted.

Targeted snapshot-start specialist suites may measure position, battle, menu, and recovery
coverage, but must be labeled component tests. Official full-game attempts start clean and never
restore, rewind, or import state from another run.

Every declared slot has one attempt. Completion, failure, invalid evidence, and interruption all
consume it and remain in the ledger denominator with an explicit reason; an outcome cannot be
replaced after inspection. A protocol-wide restart requires a new registry version.

Battle reports separate `free_choice_accuracy` from `forced_choice_accuracy` and include the
unobserved-context count. Forced-choice accuracy measures obedience to an exact move constraint,
not autonomous action selection, and cannot substitute for the free-choice result. Reports also
disclose cross-partition policy-visible snapshot overlap and novel-visible-state performance.
Visible semantic overlap is report-only because distinct hidden timing histories can converge on
the same observation; copied episode identities, manifests, assignments, schedules, or root
lineages remain hard leakage.

## Collection order

1. Freeze the first trajectory schema, private writer, and Pokémon Red adapter. **Done.**
2. Record and exactly replay the clean-start bedroom trace. **Done as part of the first full
   control trajectory.**
3. Preserve the qualified **6/6** checkpoint segment through verified Squirtle. **Done.**
4. Extend the same clean session through the lab rival, Oak's Parcel, and the Pokédex. **Done.**
5. Extend and replay-qualify the route through Pewter City and Brock. **Done.**
6. Extend and replay-qualify Route 3, Mt. Moon, the Helix Fossil, and Cerulean City. **Done.**
7. Extend and replay-qualify Misty through stable Vermilion City. **Done.**
8. Extend and replay-qualify the S.S. Anne rival and HM01 Cut. **Done.**
9. Extend and replay-qualify the DUX/Diglett party, Vermilion Gym puzzle, and Lt. Surge. **Done.**
10. Extend and replay-qualify Rock Tunnel and stable Lavender Town. **Done.**
11. Extend and replay-qualify Route 8, the west-east Underground Path, and stable Celadon City.
    **Done.**
12. Extend and replay-qualify the Rocket Hideout, Giovanni, and Silph Scope. **Done.**
13. Extend and replay-qualify Pokémon Tower, Mr. Fuji, and the Poké Flute. **Done.**
14. Extend and replay-qualify a bounded Route 12 Snorlax capture through stable Fuchsia Center.
    **Done.**
15. Extend and replay-qualify the Safari Zone, HM03 Surf, Fuchsia Gym, Koga, and HM04 Strength.
    **Done.**
16. Extend and replay-qualify all remaining badges, the final Route 22 rival, Route 23, Victory
    Road, and Indigo Plateau preparation. **Done.**
17. Freeze explicit adaptive-battle identities, planner context, and prospective train,
   validation, and test timing schedules, including exact execution identities, one-shot ledger
   accounting, global plus partition-local slots, and an authenticated fitting lane that consumes
   only complete train/validation outcomes while leaving test sealed. **Done as protocol
   infrastructure; the fitting lane has not executed because collection is pending.**
18. Commit and push the exact source/configuration state, then complete the disjoint, unassigned,
   non-counted 68/68 schedule dry run before slot `01`. **Pending; as of the current branch,
   neither the dry run nor any declared slot has executed.**
19. Generate clean demonstrations plus perturbed starts and recoverable mistakes for each
   qualified skill.
20. Train a small behavior-cloning baseline per specialist.
21. Run DAgger until there are zero teacher interventions across 20 preregistered held-out rollouts
   from the frozen perturbation suite for that skill.
22. Extend the teacher through the Elite Four, Champion, and Hall of Fame. **Done.**
23. Produce multiple clean teacher completions with timing and RNG variation.
24. Train the semantic planner and full-game composition only after that coverage exists.
25. Evaluate the frozen learned/hybrid stack across held-out seeds with teacher fallback disabled.

The deterministic-teacher gate of three intervention-free clean-power-on Hall-of-Fame runs is
complete. Learned reliability still requires at least 8/10 frozen clean-start runs on the
preregistered held-out evaluation. No learned robustness or multi-seed completion result is
claimed yet.
