# Changelog

## Unreleased

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
- Added typed opening phases and fail-closed checks for maps, coordinates, scripts, events,
  controller masks, party state, and starter species.
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
