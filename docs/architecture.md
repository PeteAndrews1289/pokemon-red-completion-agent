# Architecture and authority boundaries

Python and PyBoy run Pokémon Red locally. The observation layer reads cartridge state and exposes facts such as party health, legal moves, reachable locations and inventory. The player calls no runtime LLM.

## From a goal to game inputs

1. The available-goal builder constructs executable alternatives from current state.
2. A local model selects a goal. Battle policies make move and switch decisions where that authority is declared.
3. An executor sends legal controller inputs for navigation, menus, battles, training or collection.
4. A verifier compares before and after state, including the intended Pokémon, target XP, cash, items and registrations.
5. Paired checkpoints retain the save, decision history and costs. Compulsory control recovery returns the game to a state in which the model can choose again.

## A complete example

The solo player selected healing and lost its last party member to poison. The repaired handoff recognized the exact failed route and the pending native blackout. The game itself charged ₽633, restored the party and returned to field control. The next story goal came from the model. [Solo recovery](work-sessions/solo-field-blackout-2026-11-19.md)

## Learning and evaluation

The project fits models offline on eligible TRAIN comparisons. A development campaign can reveal a bottleneck or reproduce a failure. Its exposed outcomes stay in the evaluation partition. Learned goal choices, deterministic support, in-game experience and new parameter fitting are separate evidence. [Completion contract](completion-contract.md) · [Assistance policy](assistance-policy.md) · [Project narrative](project-narrative.md)
