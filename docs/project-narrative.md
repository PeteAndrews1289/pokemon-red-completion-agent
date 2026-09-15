# Project story: learning to play Pokémon

Pete's goal is a model that makes useful decisions, reacts when the game differs and carries skills
into unfamiliar titles. This is an AI-assisted project; coding assistants build and review the system
rather than secretly choosing its live game actions.

The first finish line is a fresh model-directed Red run with Champion/Hall-of-Fame evidence and all
151 local registrations. Then comes an unfamiliar compatible Red hack, Crystal and Emerald.

## Latest chapter: end the isolated battle gate and return to the Pokedex

Campaign C ran three prospectively fixed battle cases and stopped on its first failure. One battle
settled. The second showed that Red's Wrap can continue dealing damage automatically while hiding
the move-selection menu; the third case never opened. Exact action and frame costs survived, and no
case was replayed or replaced.

The shared runtime now recognizes that observable multi-turn continuation without a route, species
or case exception. Local regression and compatibility tests pass, but the repair has not been
rerun on cartridge and creates no learning claim. Model121 remains at 121 examples/83 successes and
86/151 registrations.

The project will not create another disposable campaign merely to discover the next isolated
mechanic. The next bounded session returns to a real heterogeneous collection choice, where a
retained registration and learning example are the desired outputs and ordinary play supplies any
further battle evidence.

[Campaign evidence](evidence/red-local-battle-cartridge-campaign-c-2026-09-15.json) ·
[Roadmap](model-first-roadmap.md) · [Mission](../MISSION.md) ·
[Active state](../ACTIVE_PRODUCT_STATE.md) · [AI-assisted authorship](../README.md)
