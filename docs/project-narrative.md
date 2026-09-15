# Project story: learning to play, not repeat a walkthrough

Pete's goal is a model that genuinely plays Pokémon: make useful decisions, react when the game
differs and carry skills into unfamiliar titles. AI assistants help build and review the system;
they do not secretly choose its live actions.

The first finish line is a fresh start-to-finish model-directed Red run with Champion and
Hall-of-Fame evidence and all151 local registrations before any ROM hack. Then comes an unfamiliar
compatible Red hack, Crystal and at least Emerald.

## Latest chapter: the safe evolution made partial progress

After the acquisition alternatives failed, a safe Tentacool-to-Tentacruel level evolution ran once
as a forced non-learning singleton. It retained61 verified training quanta and advanced Tentacool
from level5 to24 before `BattleRuntimeError`. The exact terminal is sealed mid-battle with no
fainted party member, pressed button, registration loss or specimen loss. The identity is consumed
and cannot retry.

This is real gameplay progress, but not learning or Pokédex progress: Model121 remains121
examples/83 successes and86/151 registrations. An eighth consecutive no-learning session keeps the
anti-drift alarm active. The next step is to diagnose and settle the actual retained battle through
a separately frozen recovery-only action, then rebuild the normal menu from a stable save.

Claude Opus High returned GO on the safe transition and initial executor, and its suggestion to
persist the raw terminal before richer inspection was adopted. Flash3.8 is reachable through
`agy`, but its attempted review returned no verdict because its own command permission was denied.

Today's learning remains one earlier resupply example:120→121 (+0.83% dataset size). The development
save remains86/151 (56.95%); neither number measures whole-project completion.

[Latest evidence](evidence/red-safe-singleton-evolution-result-2026-09-15.json) ·
[Detailed session](work-sessions/2026-09-15-safe-singleton-evolution.md) ·
[Model-first roadmap](model-first-roadmap.md)

Checkpoint story completion is a component result, not the required fresh run.
[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) ·
[Authorship and public overview](../README.md)
