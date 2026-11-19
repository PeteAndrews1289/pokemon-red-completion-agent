# Pokémon Red Completion Agent

A local player for Pokémon Red that chooses goals, fights battles and works toward 124 legitimate Pokédex registrations on one save. The player uses Pokémon game state, small learned models and a Game Boy emulator. It makes zero runtime calls to an LLM.

## What works today

**Four development campaigns started from power-on on the same seed. All four earned eight badges, entered the Hall of Fame and finished the 124-species route on their own saves.** An independent read of each terminal save verified the result. All four needed external continuations. The fastest used 8h 12m 59s of active campaign time and 10h 52m 12s from launch to exit. [Four-run results and all 40 splits](docs/work-sessions/four-run-splits-2026-11-19.md)

Together, those campaigns spent 63.3% of active time **after** the Hall of Fame. One run spent 165 minutes progressing from 75 to 100 registrations, against 75 minutes for the fastest run. The slower player repeatedly tried to acquire Pokémon and restored the party. That difference gives us a specific behavior to improve and a frame-based way to measure it. [Split and cost evidence](docs/evidence/red-campaign-comparison-2026-11-19.json)

## What is not solved

**The next delivery test is one unchanged run from power-on to Champion and 124.** A fifth, solo attempt exposed a stopping error before Brock. Its only Pokémon fainted from poison while walking to heal. We repaired the handoff to the game's blackout sequence, verified it from both sides on copies, then resumed that same save. The solo attempt counts as externally assisted. [Solo campaign and repair](docs/work-sessions/solo-field-blackout-2026-11-19.md)

## How it works

The observation layer reads semantic game state. A local policy chooses among available goals. Reusable skills perform legal navigation, menu and battle actions. A separate verifier checks the result and records its costs. Failures, cash losses and restores remain in the history. Fitting happens offline on eligible training examples. Experience points earned by a Pokémon are a game outcome. [Architecture](docs/architecture.md) · [Completion contract](docs/completion-contract.md)

## Where to start

- For an interview or portfolio review, start with the [interview handoff](docs/ai-systems-specialist-interview-handoff.md) or [one-page brief](docs/portfolio-brief.md).
- For the development history, read the [project narrative](docs/project-narrative.md), [research retrospective](docs/research-retrospective.md), [chronicle](docs/chronicle/README.md) or [historical log](docs/worklog.md).
- For the current work, use the [handoff](HANDOFF.md), [active product state](ACTIVE_PRODUCT_STATE.md), [roadmap](docs/model-first-roadmap.md) and [seven goals](docs/seven-goals.md).
- For the code, see the [setup guide](docs/getting-started.md), [dashboard guide](docs/progress-dashboard.md) and [documentation map](docs/README.md). Native campaign reproduction also requires the private ROM, saves, weights and runtime inputs.

## Authorship

Pete Andrews defines the product, directs AI-assisted development, watches the player's decisions and sets the evidence required for acceptance. Codex, Claude and Antigravity have contributed engineering or review at different stages. The local player makes the gameplay decisions. [Project mission](MISSION.md) · [Research and assistance policy](docs/assistance-policy.md)

[Source for the November 19 development player](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/tree/codex/red-same-seed-20261119)
