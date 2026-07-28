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

Current qualification: **6/6 bounded opening checkpoints** and **3/36 completion objectives**,
ending with a semantically verified Squirtle. This is not a rival, Pokédex, badge, learned-policy,
or completion result.

- [x] Build the no-save PyBoy bridge and read-only state adapter from pinned symbols.
- [x] Add controller timing and one authoritative action executor.
- [x] Qualify clean power-on through the input-ready bedroom and one-tile movement probe.
- [x] Qualify leaving home, Professor Oak's escort, and Squirtle selection through six closed-loop
  checkpoints.
- [x] Add an optional visible watch mode that leaves human input and saving disabled.
- [ ] Qualify the lab rival, Oak's Parcel delivery, and Pokédex objective.
- [ ] Qualify the route to Pewter City and defeat Brock.
- [ ] Replay every opening objective from multiple private timing perturbations.

Next sequence: Oak's Parcel/Pokédex, then Brock. The qualified corridors and opening semantic gates
are pinned to pret/pokered commit `1e96034092686d006e863cace09e87273051a3d8`.

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
