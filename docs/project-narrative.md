# Project story: learning to play Pokémon

Pete's goal is a model that makes useful decisions, reacts when the game differs and carries skills
into unfamiliar titles. This is an AI-assisted project; the coding assistants build and review the
system rather than secretly choosing its live game actions.

The first finish line is a fresh model-directed Red run with Champion/Hall-of-Fame evidence and
all 151 local registrations. Then comes an unfamiliar compatible Red hack, Crystal and Emerald.

## Latest chapter: the cartridge gate catches its own evidence gap

The disposable campaign first proved that a forced battle-runtime failure could be stored and
reopened without touching the cartridge. Three Route11 cases then completed across varied menus and
timing in 223 actions / 19,851 frames. One case naturally put the battler to sleep: the first
selection spent no PP, the next one executed, and the shared runtime settled the battle correctly.

The first Diglett's Cave case returned a materializer exception. Its type and runner control flow
place it before battle, but that phase did not survive in the durable episode. Only the exception
class did—not the semantic phase or exact action/frame cost. That was enough to fail qualification.
Work stopped without replaying the case or opening the remaining executable declarations.

This is honest engineering evidence, not model progress. Model121 stays at 121 examples / 83
successes and the development save at 86/151 registrations. The next task is a V2 journal that
covers failures across setup and battle components; only then can new cartridge qualification and
the heterogeneous collection lesson resume.

[Session and limits](work-sessions/2026-09-15-bounded-battle-cartridge-qualification.md) ·
[Roadmap](model-first-roadmap.md) · [Mission](../MISSION.md) ·
[Active state](../ACTIVE_PRODUCT_STATE.md) · [AI-assisted authorship](../README.md)
