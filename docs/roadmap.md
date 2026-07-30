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

Current qualification: **287/287 bounded checkpoints** and **31/36 completion objectives**, ending
after the final Route 22 rival, every Route 23 badge gate, all Victory Road boulder switches,
Indigo Plateau preparation, and a qualified Lorelei victory. Three clean runs reached the
identical 4,496,270-frame / 38,258-action Bruno-room boundary.
This is an exact deterministic-teacher milestone, not a
learned-policy, timing/RNG-generalization, or completion result.

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
- [x] Replay every qualified objective across three clean-power-on runs.

Next sequence: defeat Bruno, Agatha, and Lance, then defeat the Champion and verify the
Hall of Fame.
The qualified corridors and
semantic gates are pinned to pret/pokered commit
`1e96034092686d006e863cace09e87273051a3d8`. See the
[Lorelei three-run evidence receipt](evidence/qualified-play-lorelei-2026-07-29.json).

Exit gate: three intervention-free clean-power-on runs reach the healed Bruno-room
boundary with identical evidence rules.

## Milestone 2 — deterministic expert

**Status: in progress — July 2026**

- Complete the route graph through all eight badges, Victory Road, Elite Four, and Hall of Fame.
- Add navigation transitions, menus, inventory, party management, HM/puzzle, battle, and recovery
  specialists.
- Record failure categories, deterministic recovery behavior, and semantic action rationales.
- Generate clean demonstrations plus corrected trajectories for timing, encounter, battle,
  status, and nearby-position variations.

Exit gate: the teacher completes at least three clean runs without save-state restoration.

## Milestone 3 — demonstration learner

- Record private teacher and recovery trajectories.
- Publish schemas, aggregate statistics, and dataset cards without game assets.
- Train goal-conditioned navigation, interaction, battle, puzzle, and recovery specialists with
  behavioral cloning.
- Evaluate each specialist on held-out seeds and deliberately perturbed semantic states.

Exit gate: learned specialists meet preregistered local reliability thresholds.

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
