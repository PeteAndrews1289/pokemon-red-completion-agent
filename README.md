# Pokémon Red Completion Agent

An experimental Pokémon player that learns which goals to pursue—catching, evolving, resupplying or healing—then uses tested game-control skills to carry them out.

**Active development, not a finished autonomous player.** The long-term goal is a model that finishes Pokémon games and builds one shared, verified Pokédex across versions and generations. Red is the first environment.

## What works today

- A learned goal/destination selector drives short Red episodes and updates from their actual outcomes, including failures.
- The latest verified collection contains **64 registered species**. The current registered-objective model has **63 training examples**—a small development dataset, not a measure of general intelligence. The latest session restored supplies, learned from a healing choice and caught Shellder during a model-selected journey. Its later Seel capture failed; that failure and the partial collection gain are both retained.
- A checkpoint-based, hierarchical story run reached the Champion and Hall of Fame. The final boss continuation was forced, and battle execution was deterministic—not a learned fresh-game playthrough.
- Saved-state recovery, collection tracking and a local spectator dashboard preserve the distinction between live gameplay, saved results and training.

The [latest collection report](docs/work-sessions/2026-09-10-supply-transport.md) and [story-completion audit](docs/audits/red-phase4-closeout-2026-09-09.md) explain exactly what ran.

## What is not solved

Fresh-game autonomy, reliable play across arbitrary seeds, complete Pokédex collection, learned low-level combat and transfer to Blue, ROM hacks or Crystal remain unfinished. Good results from related training states do not establish independent reliability.

## How it works

**Observe → choose a goal → execute a bounded skill → verify the result → save → learn.**

Python and PyBoy provide game observation and control. A small NumPy-based goal-value model ranks available choices. Deterministic code handles navigation, menus, battles and capture/evolution mechanics. A SQLite-backed shared registration ledger keeps global credit separate from each save's Pokédex and physical inventory. LLM coding assistants help develop the software; they are not secretly choosing each live action.

[Architecture and code map](docs/architecture.md) · [Development roadmap](docs/development-roadmap.md) · [Dashboard guide](docs/progress-dashboard.md)

## Try the public code

[Setup and verification](docs/getting-started.md) covers ROM-free tests and the local dashboard. ROMs, emulator saves, training datasets and model artifacts are deliberately not distributed. Reproducing private gameplay requires your own lawful assets and compatible setup; this is not yet a one-command public demo.

## Authorship

**Pete Andrews** defines the product, directs development, challenges design decisions and validates observed behavior. AI coding agents—including Codex, Claude and Antigravity—have contributed implementation and review. This is an explicitly AI-assisted engineering project, not a claim that Pete hand-wrote every component.

[Project story](docs/project-narrative.md) · [Concise portfolio brief](docs/portfolio-brief.md) · [Historical work log](docs/worklog.md)

Contributors: use [AGENTS.md](AGENTS.md), the [active development state](ACTIVE_PRODUCT_STATE.md) and the single current [handoff](HANDOFF.md). Session reports belong in the history, not at the top of this README.
