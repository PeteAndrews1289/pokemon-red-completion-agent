# Portfolio brief

## Thirty-second explanation

I’m directing an AI-assisted project to build a Pokémon player that learns which goals to pursue—catching missing species, evolving them and managing resources—and eventually reuses that knowledge across games. The current system combines a small learned planner with deterministic game-control skills, then verifies the actual outcome before using it for training.

## Demonstrated work

- Model-selected collection and resource goals in bounded Red episodes.
- Incremental learning from actual outcomes, including failures.
- 58 verified registered species and 54 examples in the current collection-learning dataset.
- Checkpoint-based Champion/Hall-of-Fame integration with deterministic battle mechanics; not a fresh-game autonomous win.
- Persistent save/model tracking, a shared registration ledger and a dashboard separating live activity from saved evidence.

[Evidence for the current collection](work-sessions/2026-09-10-collection-continuation.md).

## My role and the stack

Pete owns requirements, directs AI coding agents, challenges architecture and scope decisions, observes runs and validates results. Codex, Claude and Antigravity contribute implementation and review. The stack is Python, PyBoy, NumPy, SQLite, a local web dashboard and automated verification with pytest/Ruff/mypy/GitHub Actions.

## The engineering lesson

A system can report a success without having learned a useful choice. The important design work is separating model authority from fixed mechanics, preserving failures and actual costs, and distinguishing saved-state progress from independent competence.

## Honest limitations

The project is still active. It does not yet demonstrate arbitrary-seed fresh-game play, a complete Pokédex, learned low-level combat or cross-game transfer. The small current dataset contains related development examples, not independent games.

[Architecture](architecture.md) · [Roadmap](model-first-roadmap.md) · [Historical brief](history/portfolio-through-2026-09-10.md)
