# Project story: learning to play, not repeat a walkthrough

Pete's goal is a model that genuinely plays Pokémon: make useful decisions, react when the game
differs and carry skills into unfamiliar titles. AI assistants help build and review the system;
they do not secretly choose its live actions.

The first finish line is a fresh start-to-finish model-directed Red run with Champion and
Hall-of-Fame evidence and all151 local registrations before any ROM hack. Then comes an unfamiliar
compatible Red hack, Crystal and at least Emerald.

## Latest chapter: preserving travel skills was necessary, but not sufficient

Direct full-Pokédex retargeting had been forgetting reusable capture travel skills. It now preserves
eight generic capabilities already earned by the profile while replacing the old encounter target;
species, source and coordinates do not carry over. Focused386 integration tests pass.

That repair did not make the menu playable. In an exact zero-input check, capture still failed as a
missing capability. Evolution also failed in the repaired profile, contradicting the previous
legacy-profile diagnostic that called it ready. The project preserves the discrepancy and treats
neither family as executable; it did not spend another reset to force an answer. Nine unused
sources remain untouched.

This is engineering progress, not learning: Model121 remains121 examples/83 successes and86/151
registrations. A fourth consecutive no-learning session keeps the anti-drift alarm active.
Next is one generic route-feasible candidate check and, only if both families pass, a real lesson.

Claude Opus High reviewed the working implementation; an intermediate-plan fit guard was accepted.
Flash supplied test themes from an older checkout, so no exact-source audit credit is claimed.

Today's learning remains one resupply example:120→121 (+0.83% dataset size). The development save
remains86/151 (56.95%); neither number measures whole-project completion.

[Latest evidence](evidence/red-capture-route-capability-repair-2026-09-14.json) ·
[Detailed session](work-sessions/2026-09-14-capture-route-capability-repair.md) ·
[Model-first roadmap](model-first-roadmap.md)

Checkpoint story completion is a component result, not the required fresh run.
[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) ·
[Authorship and public overview](../README.md)
