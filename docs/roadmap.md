# Roadmap

## Milestone 0 — completion foundation

**Status: complete — July 2026**

- [x] Define the clean-run completion contract.
- [x] Separate training assistance from evaluation assistance.
- [x] Add exact ROM identity checks and public-artifact guards.
- [x] Add deterministic grid navigation.
- [x] Validate the semantic objective graph and specialist interfaces.
- [x] Add source-bound run manifests and the independent completion referee.

Exit gate: all foundation modules pass ROM-free CI and no document claims gameplay progress.

## Milestone 1 — verified opening chapter

**Status: in progress — July 2026**

Current qualification: **11/11 bounded checkpoints** and **4/36 completion objectives**, ending
with the lab rival defeated, Oak's Parcel delivered, the Pokédex received, and controls restored.
Three clean runs reached the identical 52,956-frame / 619-action boundary. This is not a badge,
learned-policy, or completion result.

- [x] Build the no-save PyBoy bridge and read-only state adapter from pinned symbols.
- [x] Add controller timing and one authoritative action executor.
- [x] Qualify clean power-on through the input-ready bedroom and one-tile movement probe.
- [x] Qualify leaving home, Professor Oak's escort, and Squirtle selection through six closed-loop
  checkpoints.
- [x] Add an optional visible watch mode that leaves human input and saving disabled.
- [x] Qualify the lab rival, Oak's Parcel delivery, and Pokédex objective in one clean session.
- [x] Add a continuous `play --watch` command with 11 visible semantic checkpoints and a safe,
  explicit bounded stop.
- [ ] Qualify the route to Pewter City and defeat Brock.
- [ ] Replay every opening objective from multiple private timing perturbations.

Next sequence: Pewter City, then Brock. The qualified corridors and semantic gates are pinned to
pret/pokered commit `1e96034092686d006e863cace09e87273051a3d8`. See the
[Pokédex three-run evidence receipt](evidence/qualified-play-pokedex-2026-07-28.json).

Exit gate: three intervention-free clean-power-on runs defeat Brock with identical evidence rules.

## Milestone 2 — deterministic expert

- Complete the route graph through all eight badges, Victory Road, Elite Four, and Hall of Fame.
- Add navigation transitions, menus, inventory, party management, HM/puzzle, battle, and recovery
  specialists.
- Record failure categories and deterministic recovery behavior.

Exit gate: the teacher completes at least three clean runs without save-state restoration.

## Milestone 3 — demonstration learner

- Record private teacher and recovery trajectories.
- Publish schemas, aggregate statistics, and dataset cards without game assets.
- Train goal-conditioned specialists with behavioral cloning.
- Evaluate each specialist on held-out and deliberately perturbed states.

Exit gate: learned specialists meet preregistered local reliability thresholds.

## Milestone 4 — DAgger and selective RL

- Collect teacher corrections on learner-induced states.
- Use snapshot curriculum RL only for skills below their imitation gates.
- Freeze and promote specialists independently.

Exit gate: a learned skill stack completes with teacher fallback disabled.

## Milestone 5 — distilled completion

- Train a local goal-conditioned macro-policy from the verified teacher and specialist dataset.
- Remove the deterministic router while retaining the objective graph, safe executor, and referee.
- Run a fixed held-out clean-start evaluation series.

Exit gate: at least one verified completion; reliability requires at least 8/10 preregistered runs.
