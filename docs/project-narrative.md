# Project story: learning to play Pokémon

Pete's goal is a model that makes useful decisions, reacts when the game differs and carries skills
into unfamiliar titles. This is an AI-assisted project; the coding assistants build and review the
system rather than secretly choosing its live game actions.

The first finish line is a fresh model-directed Red run with Champion/Hall-of-Fame evidence and
all 151 local registrations. Then comes an unfamiliar compatible Red hack, Crystal and Emerald.

## Latest chapter: make failures measurable before playing again

The previous cartridge campaign stopped after three Route11 successes and one Diglett setup
failure. Its failed episode survived, but its semantic phase and exact cost did not. Rather than
replaying it, this session built a journal that follows the whole case from source inspection
through relocation, encounter setup, battle and settlement.

Synthetic failures now prove that attempted actions, completed actions and actual frames survive
independently—even when an action advances time and then fails. Limits stop setup before it
exceeds the permitted requests. Unknown cost remains explicitly unknown. The same journal spans
separate emulator sessions, and the real battle runtime's diagnostic reopens exactly.

371 focused tests passed. That is an engineering prerequisite, not model learning or cartridge
reliability. No game was opened. Model121 stays at 121 examples / 83 successes and the development
save at 86/151 registrations. Next comes a new bounded cartridge campaign, then the heterogeneous
acquisition lesson if qualification passes. The old failed case remains consumed.

[Session and detailed roadmap](work-sessions/2026-09-15-cartridge-journal-v2.md) ·
[Roadmap](model-first-roadmap.md) · [Mission](../MISSION.md) ·
[Active state](../ACTIVE_PRODUCT_STATE.md) · [AI-assisted authorship](../README.md)
