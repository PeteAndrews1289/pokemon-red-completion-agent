# Pokémon Red Completion Agent

An experimental Pokémon player that learns which goals to pursue—catching, evolving, resupplying or healing—then uses tested game-control skills to carry them out.

**Active development, not a finished autonomous player.** The long-term goal is a model that finishes Pokémon games and builds one shared, verified Pokédex across versions and generations. Red is the first environment.

## What works today

- A learned goal/destination selector drives short Red episodes and updates from their actual outcomes, including failures.
- The earned development endpoint has **109/124 native registrations**. Model141 has **141 fitted outcomes / 96 successes**. A continuous 7-decision episode handled normal failed searches and made verified progress without operator-selected destinations; no new training or fresh-game completion is claimed.
- Frozen battlers have demonstrated learning and natural switching; qualified bindings connect supported combat to the player with shared budgets and retained logs.
- Qualified K is explicitly integrated for supported ordinary trainer battles with up to six party members. Two model-selected wins earned875cash; the model chose healing and a500-cost Safari acquisition. A retained-state continuation caught Rhyhorn without a second fee.
- A checkpoint-based, hierarchical story run reached the Champion and Hall of Fame. The final boss continuation was forced, and battle execution was deterministic—not a learned fresh-game playthrough.
- Saved-state recovery, collection tracking and a local spectator dashboard preserve the distinction between live gameplay, saved results and training.
- A separate earned story lineage has seven badges. Its admitted learned actor beat Blaine and seven gym trainers; three reserves subsequently reached level39 through learned wild combat and supported preparation. Giovanni is not yet fought.

The six-member comparison used one enemy roster; K suffered16faints versus J15.
Funding integration is not mastery. Failures remain recorded; unsafe states stop.
[Integrated episode](docs/evidence/red-integrated-player-2026-09-21.json) ·
[Earning/spending](docs/evidence/red-k-earned-spending-integration-2026-09-20.json) ·
[Earlier loss](docs/evidence/red-battle-lifecycle-continuation-2026-09-19.json) ·
[Current handoff](HANDOFF.md).

## What is not solved

Fresh-game autonomy, broad battle reliability, complete collection and cross-title transfer remain unfinished. Scoped successes do not establish mastery across arbitrary seeds.

Rejected status experiments remain rejected. A later additive actor won72/128 versus
K66 but failed the original decision-efficiency screen. The owner admitted that exact
actor for bounded story development, not final-player promotion. Current story progress
has resumed after shared routing repairs and one earned Viridian gym win;
Giovanni still requires further gym clearance.
[Current evidence](docs/evidence/red-forced-motion-gym-2026-09-22.json).

**Complete Red comes first:** one fresh start-to-finish model-directed run, Champion/Hall-of-Fame evidence and the declared124-species legitimate native route before any ROM hack. Unavailable version, trade and event dependencies remain explicit for later legitimate acquisition. After Red: a compatible unfamiliar hack, Crystal, then at least Emerald.

## How it works

**Observe → choose a goal → execute a bounded skill → verify the result → save → learn.**

Python and PyBoy expose semantic emulator/cartridge state, not pixels alone. Small NumPy models rank goals and battle choices. Deterministic code handles navigation, menus and capture/evolution mechanics. Qualified J/K and narrowly admitted story bindings own supported combat; default wild-capture and Elite Four controllers remain unchanged. SQLite memory separates global credit, local flags and specimens. LLM coding assistants develop the software, not each live action.

[Architecture and code map](docs/architecture.md) · [Development roadmap](docs/development-roadmap.md) · [Dashboard guide](docs/progress-dashboard.md)

## Try the public code

[Setup and verification](docs/getting-started.md) covers ROM-free tests and the local dashboard. ROMs, emulator saves, training datasets and model artifacts are deliberately not distributed. Reproducing private gameplay requires your own lawful assets and compatible setup; this is not yet a one-command public demo.

## Authorship

**Pete Andrews** defines the product, directs development, challenges design decisions and validates observed behavior. AI coding agents—including Codex, Claude and Antigravity—have contributed implementation and review. This is an explicitly AI-assisted engineering project, not a claim that Pete hand-wrote every component.

[Documentation map](docs/README.md) · [Full project chronicle](docs/chronicle/README.md) · [Project story](docs/project-narrative.md) · [Video narrative](docs/youtube-video-narrative.md) · [Research retrospective](docs/research-retrospective.md) · [Historical work log](docs/worklog.md)

Contributors: use [AGENTS.md](AGENTS.md), the [active development state](ACTIVE_PRODUCT_STATE.md) and the single current [handoff](HANDOFF.md). Session reports belong in the history, not at the top of this README.
