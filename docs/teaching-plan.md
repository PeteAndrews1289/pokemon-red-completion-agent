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

The deterministic teacher currently verifies all **284/284 qualified checkpoints** through
Victory Road and therefore **30/36 completion objectives**. Three clean runs were identical at
the 4,427,245-frame / 37,535-action boundary. The evidence includes the earlier Brock
and Mt. Moon gates,
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
22, Route 23, and Victory Road.

The same segment can run headlessly or be observed locally with:

```bash
pokemon-red-completion play --watch --speed 4
```

Watch mode does not provide a human controller, record the screen, expose the ROM path, load a
save, or change the teacher. It renders the same bounded execution while checkpoint progress is
printed to the terminal.

## What each learning stage needs

### Behavioral cloning

Action-aligned examples for individual skills:

- semantic observation and current objective;
- macro-action plus button press/release duration;
- resulting observation and event delta;
- success, retry, recovery, or terminal label; and
- both nominal and deliberately perturbed starts.

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

- **Episode manifest:** ROM, source, configuration, teacher and policy hashes; assistance class;
  seed; start type; outcome; terminal reason; attempt denominator; and completion evidence.
- **Decision table:** emulator frame; structured observation; objective and skill; macro and
  primitive action; duration; teacher label; next-state hash; event delta; and recovery state.
- **Sparse event log:** map, objective, badge, party, item, battle, checkpoint, recovery, and
  terminal transitions.

Decision tables should use Parquet. Manifests and sparse events should use canonical JSON or JSONL.
Screens, ROMs, saves, snapshots, and recordings remain private and content-addressed.

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

- **Exact teacher:** repeat the frozen clean-power-on route and report its own attempts,
  checkpoints, actions, frames, recoveries, and terminal reasons.
- **Perturbed teacher:** run preregistered timing/RNG schedules without restoration and report
  outcomes stratified by observed encounters, damage, status, displaced positions, and recovery.
- **Learned multi-seed:** run held-out clean starts with frozen weights and configuration,
  teacher/oracle fallback disabled, and every attempt counted.

Targeted snapshot-start specialist suites may measure position, battle, menu, and recovery
coverage, but must be labeled component tests. Official full-game attempts start clean and never
restore, rewind, or import state from another run.

## Collection order

1. Freeze the trajectory schema and logger.
2. Record and exactly replay the clean-start bedroom trace.
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
14. Extend and replay-qualify Route 12 Snorlax through stable Fuchsia Center. **Done.**
15. Extend and replay-qualify the Safari Zone, HM03 Surf, Fuchsia Gym, Koga, and HM04 Strength.
    **Done.**
16. Extend and replay-qualify all remaining badges, the final Route 22 rival, Route 23, Victory
    Road, and Indigo Plateau preparation. **Done.**
17. Generate clean demonstrations plus perturbed starts and recoverable mistakes for each
   qualified skill.
18. Train a small behavior-cloning baseline per specialist.
19. Run DAgger until there are zero teacher interventions across 20 preregistered held-out rollouts
   from the frozen perturbation suite for that skill.
20. Extend the teacher through the Elite Four, Champion, and Hall of Fame.
21. Produce multiple clean teacher completions with timing and RNG variation.
22. Train the semantic planner and full-game composition only after that coverage exists.
23. Evaluate the frozen learned/hybrid stack across held-out seeds with teacher fallback disabled.

The current evaluation gate is three intervention-free clean-power-on runs through Victory Road.
A first Hall-of-Fame success is a milestone; reliability requires at least 8/10
frozen clean-start runs. No learned robustness or multi-seed completion result is claimed yet.
