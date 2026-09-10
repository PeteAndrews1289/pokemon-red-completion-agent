# Architecture: a learned planner with deterministic game skills

This is a hierarchical player, not an end-to-end visual neural network. The active learner selects semantic goals and destinations; existing skills translate those choices into game actions.

## Active Red collection loop

```text
PyBoy game state
  → Red observation adapter
  → semantic state + collection memory + available goals
  → learned goal/destination choice, with declared safety overrides
  → deterministic skill and controller executor
  → independent outcome checks
  → saved state + recorded costs/results
  → fit the goal-value model from eligible real outcomes
```

A failed skill remains a failed outcome even if it made partial collection progress. A safety-driven or single-option action is not automatically an additional learned choice.

## Components and technology

| Component | Current implementation and responsibility |
| --- | --- |
| Runtime | Python3.11+; PyBoy2.7.0 for the private Red cartridge. |
| Observation | Title-specific readers decode location, party, inventory, battle and Pokédex state. High-level policy receives semantic features rather than memory addresses. |
| Knowledge and routing | Cartridge-derived Gen1 map, terrain, encounter and acquisition data; deterministic route planning and execution. Access restrictions and unsupported mechanics still limit coverage. |
| Goal model | NumPy-based option-value learning with a regularized multi-outcome regression objective. Ranks available goals or destinations; not a language model controlling buttons. |
| Exploration | Eligible choices mix25% uniform exploration with75% model softmax. Deterministic safety support remains identified separately. |
| Skills | Navigation, battle/menu control, capture, supported evolution, resources and storage. Their availability and completion are checked against actual state. |
| Shared memory | SQLite-backed registration ledger plus separate per-save owned flags and physical party/box inventory. A global credit is not a local specimen. |
| Persistence | Private episode streams, exact state checkpoints and model/corpus records linked by hashes. Continuation authenticates the recorded history. |
| Viewer | Local, read-only HTTP dashboard with HTML/CSS/JavaScript; live frames, saved evidence, training and engineering status are distinct. |
| Verification | pytest, Ruff, mypy, documentation/publication checks and GitHub Actions. Tests are engineering evidence, not model training. |

## Who decides what?

The goal selector owns eligible high-level alternatives. Safety gates may constrain or override a choice, and those interventions must be visible. The executor owns controller input. The verifier checks what actually happened; it must not quietly choose a better action for the player.

LLMs are used as development and review assistants. They are not the active goal-value model and are not called to supply each battle move. Historical research includes other learned components, but those experiments do not imply live authority in today's collection loop.

The source-level boundaries prevent accidental misuse; Python interfaces are not a security sandbox against malicious code.

## Learning and evidence

Training retains actual selected choices and outcomes, including losses and resource costs. Interrupted choices remain incomplete rather than becoming invented successes or failures. Incremental fitting retains earlier eligible data.

The active registered-objective model has 61 examples from related development states. Those are not 61 independent games. In-sample fit quality and a successful collection batch cannot establish generalization.

Champion and Hall-of-Fame evidence exists for checkpoint-based hierarchical story integration. It does not prove that the present collection model can start from the title screen and independently complete the game.

## Code map

All module paths below are under [the Python package](../src/pokemon_red_completion).

| Concern | Starting points |
| --- | --- |
| Semantic observation | `observation.py`, `red_player_observer.py`, `red_party.py` |
| Cartridge knowledge | `gen1_maps.py`, `gen1_terrain.py`, `gen1_traversal.py`, `gen1_acquisition.py` |
| Learned choice | `living_dex_option_value.py`, `living_dex_player_exploration.py`, `red_player_model.py` |
| Runtime and routing | `red_bounded_player.py`, `red_routed_semantic_goal.py`, `red_travel_capture.py` |
| Registration | `registration_memory.py`, `registered_collection.py`, `registered_checkpoint.py` |
| Training | `red_player_incremental_fit.py`, `red_player_training_dataset.py` |
| Evidence and recovery | `private_artifacts.py`, `red_player_checkpoint.py`, `provenance.py` |
| Orchestration | [Regional learning-cycle runner](../scripts/run_red_regional_learning_cycle.py) |

ROMs, states, recordings, datasets and model artifacts are private. Public summaries contain selected metrics and hashes, not enough material to reproduce every private run.

[Current roadmap](model-first-roadmap.md) · [Historical architecture claims](history/architecture-through-2026-09-10.md)
