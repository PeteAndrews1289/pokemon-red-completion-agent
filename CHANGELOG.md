# Changelog

## Unreleased

- Added a versioned, game-neutral trajectory schema for semantic observations, decisions,
  executions, and sparse events.
- Added a thin Pokémon Red observation adapter that keeps revision-specific RAM details below the
  shared Pokémon ontology boundary and separates policy observations from privileged
  teacher/referee evidence.
- Added fail-closed private episode storage with an explicit external-volume sentinel, atomic
  finalization, path-free manifests, and public-safe summaries.
- Added continuous teacher instrumentation from clean power-on through the Hall of Fame, with
  semantic checkpoints and controller actions linked in one episode.
- Added privacy-safe battle move decision spans at the shared adaptive policy boundary, linking
  each validated teacher choice to every executor action used to carry out that turn without
  persisting raw game state or teacher-only encounter labels.
- Recorded and audited the first private full-game control trajectory: 41,330 executions, 300
  events, and 14,760 deduplicated semantic snapshots across all 299 checkpoints.
- Recorded and audited the first private adaptive battle decision trajectory: 422 move choices
  across 32 battle locations, linked to 3,022 executor actions with exact first-state hashes.
- Documented the measured cross-game transfer goal and its Red, near-transfer, and
  cross-generation promotion gates.

## 0.2.0 — Deterministic expert

- Completed three identical clean-power-on runs through all 299 checkpoints, all 36 objectives,
  the Champion-defeated event, and the Hall of Fame without human input or save-state restoration.
- Added a lazy, optional PyBoy 2.7 adapter that verifies the private ROM and gives PyBoy only an
  in-memory stream created from exact fingerprint-verified bytes.
- Disabled human window input, adjacent save discovery, and save-on-exit in the private runtime.
- Restricted observations to Work RAM and removed the public emulator-factory injection surface.
- Adapted the predecessor's verified clean-power-on sequence behind the frame-safe executor.
- Added a `bootstrap` command that reaches the input-ready bedroom and verifies one-tile movement.
- Added a bounded `opening` teacher that verifies all 6/6 opening checkpoints and Squirtle,
  establishing exactly 3/36 completion objectives.
- Added `opening --watch --speed 4` for a visible local run while preserving disabled human input,
  in-memory ROM handling, and no-save shutdown.
- Added a continuous `play` command that keeps one clean emulator session alive through the lab
  rival, both Route 1 crossings, Oak's Parcel, Viridian Forest, and Brock.
- Qualified 21/21 semantic checkpoints and 6/36 completion objectives across three identical
  122,999-frame / 1,573-action clean runs.
- Extended the continuous deterministic teacher through the Cerulean rival, Nugget Bridge,
  selected Route 25 trainers, Bill, the mandatory Cerulean Gym trainer, and Misty.
- Qualified 58/58 semantic checkpoints and 9/36 completion objectives across three identical
  434,510-frame / 5,936-action clean runs, with Cascade Badge, TM11, and S.S. Ticket evidence.
- Extended the same no-save session through the Cerulean Rocket thief, TM28, Route 5, the
  Underground Path, both required lower Route 6 trainers, and stable Vermilion City.
- Added bounded sleep recovery, a full-heal replay, and semantic RUN navigation that explicitly
  verifies three exact Route 6 Pidgey encounters without changing PP or trainer events.
- Qualified 73/73 semantic checkpoints and 10/36 completion objectives across three identical
  501,922-frame / 7,242-action clean runs, with a sanitized v5 evidence receipt.
- Added fail-closed rival, parcel, Pokédex, forest, Brock-identity, battle-readiness, badge, and
  TM34 and post-dialogue movement evidence gates plus an explicit bounded safe stop that cannot be
  mistaken for completion.
- Added typed opening phases and fail-closed checks for maps, coordinates, scripts, events,
  controller masks, party state, and starter species.
- Added a source-bound, sanitized receipt for three identical clean-start Squirtle runs.
- Pinned the new opening corridors and semantic gates to pret/pokered commit
  `1e96034092686d006e863cace09e87273051a3d8`.
- Added a private integration gate and expanded the ROM-free emulator coverage.
- Documented the reference, behavioral cloning, DAgger, and private trajectory strategy.

## 0.1.0 — Completion foundation

- Defined the clean-power-on, no-intervention Hall-of-Fame evaluation contract.
- Added an immutable semantic state model and a validated 36-objective completion DAG.
- Added exact ROM revision verification with sanitized public fingerprints.
- Added read-only memory translation and persistent semantic progress tracking.
- Required concurrent Champion-event and Hall-of-Fame evidence for completion.
- Added deterministic A* navigation with stable tie-breaking.
- Added typed macro-actions, specialist plans, deterministic teacher routing, and a frame-safe
  executor that releases buttons after failures.
- Added source, route, configuration, ROM, and model identity hashing.
- Added public-artifact and documentation guards plus 42 ROM-free tests.
- Isolated Continual Harness as an optional, pinned external baseline rather than a core dependency.
