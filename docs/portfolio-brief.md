# Portfolio brief

## Thirty-second explanation

I’m directing an AI-assisted project to build a Pokémon player that learns which goals to pursue—catching missing species, evolving them and managing resources—and eventually reuses that knowledge across games. The current system combines a small learned planner with deterministic game-control skills, then verifies the actual outcome before using it for training.

## Demonstrated work

- Model-selected collection and resource goals in bounded Red episodes.
- Incremental learning from actual outcomes, including failures.
- 86 verified local registrations and121 settled examples/83 successes. Model121's next menu was only resupply versus restoration, so the repeated lineage stopped before another query or gameplay. These are development results, not independent improvement.
- Checkpoint-based Champion/Hall-of-Fame integration with deterministic battle mechanics; not a fresh-game autonomous win.
- Persistent save/model tracking, a shared registration ledger and a dashboard separating live activity from saved evidence.

[Evidence for the current model](work-sessions/2026-09-13-model120-frozen-field-restore.md).

The automatic runtime now derives useful fishing sources from current cartridge and save data
instead of a named-species route. Capture preparation can retrieve a status-move helper from any
verified box after selection. The first five-choice execution stopped at a dialogue boundary after
228 actions; the attempt was not retried, and its measured failure advanced model111 to model112.
The next checkpoint recovered in 8 actions and preserved every registration and specimen. Its
frozen restore produced Model113; the following frozen fishing choice added registration84 and
produced Model114. The subsequent income-verification failure became Model115. Cartridge source
then explained the extra58 as opponent Pay Day; the exact continuation's stale-accumulator failure
became Model116. A later frozen fishing success produced Model117, whose verified resource purchase
produced Model118. Its verified restoration produced Model119; a separately labelled forced bridge
then captured Poliwhirl without fitting it. Model119's next genuine choice selected a one-item
restore; the verified success produced Model120. Model120 then selected trainer resupply and earned
360 cash, producing Model121. The next action-free inventory repeated resupply and restoration, so
the loop stopped. A full-151 inventory now exposes the actual 65-entry dependency gap.

## My role and the stack

Pete owns requirements, directs AI coding agents, challenges architecture and scope decisions, observes runs and validates results. Codex, Claude and Antigravity contribute implementation and review. The stack is Python, PyBoy, NumPy, SQLite, a local web dashboard and automated verification with pytest/Ruff/mypy/GitHub Actions.

## The engineering lesson

A system can report a success without having learned a useful choice. The important design work is separating model authority from fixed mechanics, preserving failures and actual costs, and distinguishing saved-state progress from independent competence.

## Honest limitations

The project is still active. It does not yet demonstrate arbitrary-seed fresh-game play, a complete Pokédex, learned low-level combat or cross-game transfer. The small current dataset contains related development examples, not independent games.

The required gate is a fresh start-to-finish model-directed Red run and the full local Red
Pokédex before any ROM hack, then Crystal and at least Emerald. Version/trade/event dependencies
cannot be silently removed from that requirement.

[Architecture](architecture.md) · [Roadmap](model-first-roadmap.md) · [Historical brief](history/portfolio-through-2026-09-10.md)
