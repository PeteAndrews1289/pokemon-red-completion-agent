# Pokémon Red Completion Agent

An AI-assisted project building a local Pokémon player that learns useful goals,
battle decisions, preparation and recovery. Semantic observations and declared
execution skills support the models. This is active development, not a finished
autonomous or pixel-only player.

## What works today

- Supported DEVELOPMENT ancestries completed Champion/Hall of Fame and124 declared
  registrations. Repairs and assistance remain disclosed.
- Scoped local models demonstrate preparation, stopping, recovery and battle wins.
- The shared public entry now progresses Bill/rival/Cut and10→12 registrations
  from a preserved checkpoint, with8 repair relaunches and6m15s native-player time.
- Historical finite two-worker capacity checks passed; all game runs are paused.

[Latest lessons](docs/project-lessons-2026-10-28.md) ·
[Seven goals](docs/seven-goals.md) · [Native scoreboard](docs/work-sessions/2026-10-28-play-first.md)

## What is not solved

Capture support repeatedly knocks out intended catches. Supplier coverage has a
frozen, unrun correction. Numerical fit passes and scoped wins do not establish
broad autonomous reliability. Fresh same-save Champion/HOF+124 and the declared
repeated-run gate remain unproved; later games stay behind Red.

The source snapshot has known lint/type debt. The current player also depends on
the declared external private helper bundle and model artifacts; a clean clone
alone cannot reproduce the private player. See the lessons for validation limits.

## How it works

Semantic observation → local model choice → bounded skill execution → native
verification and retained continuation. The runtime player makes no LLM calls.
Fitting is a separate explicit process; in-game XP does not update model weights.
Python, PyBoy, NumPy and SQLite support the system.

## Read and review

[HANDOFF.md](HANDOFF.md) is the sole current work order. Read
[MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and the generated
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) first.

[Documentation map](docs/README.md) · [Review brief](docs/review-brief.md) ·
[Architecture](docs/architecture.md) · [Setup](docs/getting-started.md) ·
[Dashboard](docs/progress-dashboard.md) · [Remaining work](docs/model-first-roadmap.md)

ROMs, raw saves, training corpora and the playable private runtime are not included
in the public source or read-only review copy. No gameplay starts from this page.

## Authorship

Pete Andrews defines the product, directs development and validates outcomes.
Coding assistants implement and review software; they are not the runtime student.
Codex, Claude and Antigravity have contributed to the project's engineering/review.

[YouTube narrative](docs/youtube-video-narrative.md) ·
[Research retrospective](docs/research-retrospective.md) ·
[Chronicle](docs/chronicle/README.md) · [Historical work log](docs/worklog.md)
