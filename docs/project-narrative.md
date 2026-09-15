# Project story: learning to play Pokémon

Pete's goal is a model that makes useful decisions, reacts when the game differs and carries skills
into unfamiliar titles. This is an AI-assisted project; the coding assistants build and review the
system rather than secretly choosing its live game actions.

The first finish line is a fresh model-directed Red run with Champion/Hall-of-Fame evidence and
all 151 local registrations. Then comes an unfamiliar compatible Red hack, Crystal and Emerald.

## Latest chapter: improve how failures are found

After repeated runtime interruptions, Pete challenged the reactive development loop. The collection
save had already been safely recovered, so this session examined the shared battle contract.

Synthetic tests exposed seven false successes: extra PP spending could pass alongside an HP change,
and a forced switch could look like move learning. The controller now verifies the full original
PP vector before accepting an effect. It also retains bounded failure traces.
604 affected tests pass, one skipped, including 108 combinations of slot, timing, menu and outcome.

This is engineering progress. Model121 stays at 121 examples/83 successes and the development save
at 86/151 registrations. No game input, training example or learned authority was added.
The old failure's exact cause is unknown; real-cartridge qualification is the next task.

The next campaign uses disposable bounded cases with retained failures before collection resumes.
It must distinguish an observed move effect from a completely settled turn.

[Session and limits](work-sessions/2026-09-15-battle-runtime-refocus.md) ·
[Roadmap](model-first-roadmap.md) · [Mission](../MISSION.md) ·
[Active state](../ACTIVE_PRODUCT_STATE.md) · [AI-assisted authorship](../README.md)
