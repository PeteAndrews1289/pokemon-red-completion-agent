# Portfolio brief

## Thirty-second explanation

I’m directing an AI-assisted project to build a Pokémon player that learns which goals to pursue—catching missing species, evolving them and managing resources—and eventually reuses that knowledge across games. The current system combines a small learned planner with deterministic game-control skills, then verifies the actual outcome before using it for training.

## Demonstrated work

- Model-selected collection and resource goals in bounded Red episodes.
- Incremental learning from actual outcomes, including failures.
- 84 verified registered species and 114 settled examples in the current collection-learning dataset. Model113's frozen fishing choice added one registration and became row114 without a teacher label. From the durable Model114 checkpoint, the model selected resupply/income from six choices across three goal families; that choice remains unexecuted. These are same-lineage development results, not independent improvement.
- Checkpoint-based Champion/Hall-of-Fame integration with deterministic battle mechanics; not a fresh-game autonomous win.
- Persistent save/model tracking, a shared registration ledger and a dashboard separating live activity from saved evidence.

[Evidence for the current model](work-sessions/2026-09-13-model114-frozen-fishing-learning.md).

The automatic runtime now derives useful fishing sources from current cartridge and save data
instead of a named-species route. Capture preparation can retrieve a status-move helper from any
verified box after selection. The first five-choice execution stopped at a dialogue boundary after
228 actions; the attempt was not retried, and its measured failure advanced model111 to model112.
The next checkpoint recovered in 8 actions and preserved every registration and specimen. Its
frozen restore produced Model113; the following frozen fishing choice added registration84 and
produced Model114. The new three-family menu selected resupply/income as the next bounded goal.

## My role and the stack

Pete owns requirements, directs AI coding agents, challenges architecture and scope decisions, observes runs and validates results. Codex, Claude and Antigravity contribute implementation and review. The stack is Python, PyBoy, NumPy, SQLite, a local web dashboard and automated verification with pytest/Ruff/mypy/GitHub Actions.

## The engineering lesson

A system can report a success without having learned a useful choice. The important design work is separating model authority from fixed mechanics, preserving failures and actual costs, and distinguishing saved-state progress from independent competence.

## Honest limitations

The project is still active. It does not yet demonstrate arbitrary-seed fresh-game play, a complete Pokédex, learned low-level combat or cross-game transfer. The small current dataset contains related development examples, not independent games.

[Architecture](architecture.md) · [Roadmap](model-first-roadmap.md) · [Historical brief](history/portfolio-through-2026-09-10.md)
