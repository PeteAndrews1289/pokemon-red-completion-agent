# Portfolio brief

## Thirty-second explanation

I direct an AI-assisted project to build a Pokémon player that learns useful goals and battle
decisions, verifies what happened, and eventually transfers those skills between games.
It combines small learned models with deterministic navigation/menu skills. It is active
development, not a finished autonomous player.

## Demonstrated

- Model-selected collection/resource choices and fitting from actual outcomes, including failures.
- Main Red development save:96/124 registrations; Model137:137 examples,92 successes.
- Frozen battle learner J: modest unused-team improvement,9/24 wins versus predecessor7/24.
- Natural small-party wins with voluntary switching and no teacher battle choices.
- Explicit integration into the main player's ordinary trainer-funding entry.
- Durable saves, decision/timing logs, independent verification and shared registration memory.

The first main-entry goal failed after Wartortle fainted. The old funding guard stopped the
unfinished battle; four decisions and the exact state were retained without reset or teacher
substitution. This establishes integration and honest failure handling, not successful funding.

## Remaining work

General battle lifecycle/recovery, sustainable resource planning,28 remaining native registrations
and a fresh model-directed Red run. Fresh-run acceptance remains0/5. ROM-hack transfer, Crystal
and Emerald follow Red acceptance. Prior checkpoint-based Champion/Hall-of-Fame work used
deterministic battle mechanics and is not the required fresh-game completion.

## Role and technology

Pete Andrews defines requirements, directs the AI workflow and validates outcomes. Codex, Claude
and Antigravity have contributed implementation or reviews; authorship is explicitly AI-assisted.
Python, PyBoy, NumPy, SQLite, typed skills, hash-linked evidence, pytest, Ruff and mypy.
Coding assistants are not secretly choosing the gameplay actions.

[Evidence](evidence/red-player-battler-integration-2026-09-19.json) ·
[Architecture](architecture.md) · [Interview handoff](ai-systems-specialist-interview-handoff.md)
