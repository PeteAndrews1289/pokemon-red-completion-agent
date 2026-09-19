# Pokémon Red Completion Agent

An experimental Pokémon player that learns which goals to pursue—catching, evolving, resupplying or healing—then uses tested game-control skills to carry them out.

**Active development, not a finished autonomous player.** The long-term goal is a model that finishes Pokémon games and builds one shared, verified Pokédex across versions and generations. Red is the first environment.

## What works today

- A learned goal/destination selector drives short Red episodes and updates from their actual outcomes, including failures.
- The collection development save has **96/124 native registrations**. Model137 has **137 settled examples / 92 successes**; this is not fresh-game completion.
- Frozen battler J has demonstrated learning and natural small-party switching wins. It is now explicitly connected to the main-player trainer-funding entry, with shared budgets and retained decision logs.
- A checkpoint-based, hierarchical story run reached the Champion and Hall of Fame. The final boss continuation was forced, and battle execution was deterministic—not a learned fresh-game playthrough.
- Saved-state recovery, collection tracking and a local spectator dashboard preserve the distinction between live gameplay, saved results and training.

The first integrated funding goal failed after Wartortle fainted. A separate continuation
from its retained state let J choose a replacement and four attacks. The party lost; normal
blackout restored field control and halved cash. Both the loss and recovery are verified,
without reset or teacher fallback. This proves battle lifecycle handling, not profitable funding.
See [continuation evidence](docs/evidence/red-battle-lifecycle-continuation-2026-09-19.json),
[earlier battler qualification](docs/evidence/red-battler-earned-switch-result-2026-09-19.json)
and the [current handoff](HANDOFF.md).

## What is not solved

Fresh-game autonomy, broad battle reliability and move support, complete Pokédex collection and transfer to Blue, ROM hacks or Crystal remain unfinished. Small-party successes do not establish six-member mastery or independent reliability across arbitrary seeds.

**Complete Red comes first:** one fresh start-to-finish model-directed run, Champion/Hall-of-Fame evidence and the declared124-species legitimate native route before any ROM hack. Unavailable version, trade and event dependencies remain explicit for later legitimate acquisition. After Red: a compatible unfamiliar hack, Crystal, then at least Emerald.

## How it works

**Observe → choose a goal → execute a bounded skill → verify the result → save → learn.**

Python and PyBoy provide observation and control. A small NumPy goal-value model ranks choices. Deterministic code handles navigation, menus and capture/evolution mechanics. Frozen J can own supported ordinary trainer battles through an explicit per-run setting; wild captures and Elite Four controllers remain unchanged. SQLite-backed registration memory separates global credit, local flags and physical specimens. LLM coding assistants develop the software; they are not secretly choosing each live action.

[Architecture and code map](docs/architecture.md) · [Development roadmap](docs/development-roadmap.md) · [Dashboard guide](docs/progress-dashboard.md)

## Try the public code

[Setup and verification](docs/getting-started.md) covers ROM-free tests and the local dashboard. ROMs, emulator saves, training datasets and model artifacts are deliberately not distributed. Reproducing private gameplay requires your own lawful assets and compatible setup; this is not yet a one-command public demo.

## Authorship

**Pete Andrews** defines the product, directs development, challenges design decisions and validates observed behavior. AI coding agents—including Codex, Claude and Antigravity—have contributed implementation and review. This is an explicitly AI-assisted engineering project, not a claim that Pete hand-wrote every component.

[Documentation map](docs/README.md) · [Project story](docs/project-narrative.md) · [Concise portfolio brief](docs/portfolio-brief.md) · [Interview handoff](docs/ai-systems-specialist-interview-handoff.md) · [Historical work log](docs/worklog.md)

Contributors: use [AGENTS.md](AGENTS.md), the [active development state](ACTIVE_PRODUCT_STATE.md) and the single current [handoff](HANDOFF.md). Session reports belong in the history, not at the top of this README.
