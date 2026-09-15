# Project story: learning to play Pokémon

Pete's goal is a model that makes useful decisions, reacts when the game differs and carries skills
into unfamiliar titles. This is an AI-assisted project; coding assistants build and review the system
rather than secretly choosing its live game actions.

The first finish line is a fresh model-directed Red run with Champion/Hall-of-Fame evidence and all
151 local registrations. Then comes an unfamiliar compatible Red hack, Crystal and Emerald.

## Latest chapter: a reusable response to a retained failure

Campaign B previously stopped after its active battler spent every move's PP without defeating the
opponent. Its exact cost and phase survived. We did not replay that consumed case.

This session built a bounded response using existing party switching. The disclosed maintenance
policy can switch once after four PP-spending turns without damage, or no usable move. It preserves
the original action/frame budget and records the claim before input. Simulated tests cover party
reordering, exhausted moves, stale menus and partial switches. 537 focused tests passed.

Flash 3.8 High reviewed the contract in Antigravity and emphasized two limits: lack of damage does
not explain the cause, and a reserve can still faint on entry. The implementation claims neither.
A second stall stops rather than starting a new budget.

This is engineering progress, not Pokémon learning. No cartridge ran this session. Model121 stays
at 121 examples/83 successes and 86/151 registrations. Next is a distinct cartridge campaign to test
the new policy; only a passing gate opens the heterogeneous acquisition lesson.

[Session and roadmap](work-sessions/2026-09-15-battle-stall-contingency.md) ·
[Roadmap](model-first-roadmap.md) · [Mission](../MISSION.md) ·
[Active state](../ACTIVE_PRODUCT_STATE.md) · [AI-assisted authorship](../README.md)
