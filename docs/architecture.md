# Architecture: learned choices, bounded game-control skills

This is a hierarchical player, not an end-to-end visual network or an LLM choosing buttons.

## Runtime

Observe coherent emulator state → propose semantic goals → learned selection → bounded skill
execution → independent verification → durable saves and actual-outcome learning.

| Component | Responsibility |
| --- | --- |
| Python3.11+ / PyBoy2.7.0 | Runtime and private cartridge execution |
| Observation adapters | Party, inventory, battle, map and Pokédex facts; raw addresses stay below policy |
| Goal learner | NumPy multi-outcome option-value model; semantic goals and destinations |
| Frozen battler J | Three small learned heads for moves, attack/switch control and replacement targets |
| Cartridge routing and skills | Navigation, menus, capture, evolution, storage and recovery |
| Executor | Sole controller-input owner; action and frame budgets |
| Referee | Verifies outcomes without choosing an alternative action |
| Shared memory | SQLite registrations; global credits, local flags and specimens stay distinct |
| Persistence | Hash-linked choices, model identities, exact saves and resource costs |
| Dashboard | Read-only saved evidence, live runtime and engineering status |

## Learned trainer integration

An authenticated private collection plan may declare a `trainer_battler` model binding.
The loader requires frozen J's qualified digest. The runtime passes an explicit per-run controller
into ordinary trainer funding; there is no module-global replacement or teacher fallback.

The bridge advances the introduction, captures the live boundary, and borrows the running emulator
without loading or closing it. Actor actions use the player's counted, limited executor. The outer
preservation guard runs at each decision. Logs record choices/timings; failures retain final saves.

This entry supports one to three own party members, not arbitrary six-member teams. Wild captures
and Elite Four controllers remain unchanged. Healing-item decisions and unsupported moves are not
enabled. Default plans retain their historical controllers.

## Verified battle lifecycle and separate funding contract

The first live integration used an earned two-member save, three ordinary Potions and a78-step
route to a new trainer. J made four decisions through the main-player prepared battle seam.
Wartortle fainted; the unchanged no-faints funding guard stopped before replacement. The goal
failed, leaving the battle unfinished at that checkpoint; no payout was earned.

This verifies invocation, budgets, logging and failure retention—not successful autonomous funding.
The probe called the main-player battle entry directly; it did not run Model137's high-level
selector or bypass its conservative funding-offer eligibility.

A separate exact-state continuation now uses `continue_learned_trainer_battle` and the bridge's
`continue_battle` entry. A faint/prompt starts at its owned boundary without driving toward MAIN.
J chose one forced replacement and four attacks, then lost. Bounded terminal dialogue completed
normal blackout; the verifier proved restored party, recorded recovery map, half cash and field
control. Typed outcomes are won/lost/unresolved and never issue a funding-success verdict.
The strict funding verifier is unchanged. No consumed source was replayed.

## Learning and claims

Model137 has137 examples,92 successes and58 economy-qualified outcomes from related development
states, not independent games. Its collection save remains96/124 registrations.

J has318 physical TRAIN contexts from four origins. Its unused generated-team comparison was9/24
wins versus H7/24: descriptive learning evidence, not statistically conclusive mastery.
Natural attack/switching probes provide additional scoped evidence. DEVELOPMENT is not fitting data.
LLMs develop and review software; they do not secretly supply live model choices.

## Code map

| Concern | Starting points under the Python package |
| --- | --- |
| Goal runtime | `red_goal_context.py`, `red_autonomous_collection.py`, `red_resource_goal_router.py` |
| Trainer binding | `red_learned_trainer.py`, `red_routed_trainer_funding.py` |
| Actor and learning | `red_trainer_practice_episode.py`, `red_trainer_practice_outcome_policy.py`, `red_trainer_practice_fit.py` |
| Decision logs | `red_trainer_practice_log.py` |
| Resource verifier | `red_trainer_funding_battle.py` |
| Registration | `registration_memory.py`, `registered_collection.py` |
| Main entry | [Bounded collection runner](../scripts/run_red_autonomous_collection.py) |

[Integration evidence](evidence/red-player-battler-integration-2026-09-19.json) ·
[Setup](getting-started.md) · [Roadmap](model-first-roadmap.md) ·
[Historical architecture](history/architecture-through-2026-09-10.md)
