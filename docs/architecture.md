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
| Frozen battlers | Learned move, attack/switch control and replacement heads; explicitly bound qualified variants |
| Cartridge routing and skills | Navigation, menus, capture, evolution, storage and recovery |
| Executor | Sole controller-input owner; action and frame budgets |
| Referee | Verifies outcomes without choosing an alternative action |
| Shared memory | SQLite registrations; global credits, local flags and specimens stay distinct |
| Persistence | Hash-linked choices, model identities, exact saves and resource costs |
| Dashboard | Read-only saved evidence, live runtime and engineering status |

## Learned trainer integration

An authenticated private collection plan may declare a `trainer_battler` model binding.
The loader requires an admitted frozen identity: J's small-party binding or exact K with its
pinned qualification receipt for supported one-to-six-member ordinary trainer execution.
The runtime passes an explicit per-run controller; there is no global replacement or teacher fallback.

The bridge advances the introduction, captures the live boundary, and borrows the running emulator
without loading or closing it. Actor actions use the player's counted, limited executor. The outer
preservation guard runs at each decision. Logs record choices/timings; failures retain final saves.

J retains one-to-three own-member scope. K's measured six-member execution does not establish
arbitrary-party/move mastery. Wild captures and default Elite Four controllers remain unchanged.
Unsupported moves and healing-item choices are not implicitly enabled by those bindings.

## Current authority boundaries

| Workload | Model-owned choice | Support / limitation |
| --- | --- | --- |
| Collection episodes | Goal and destination among executable offers | Deterministic navigation, storage, capture/evolution mechanics and verification |
| Ordinary trainer funding | Explicit J/K attacks and supported switches | Eligibility and strict funding acceptance remain separate from general battle completion |
| Earned story combat | Exact owner-admitted frozen additive actor | Admission follows a failed efficiency screen; no final-player promotion |
| Wild reserve preparation | K knockout attacks and switches | Targets, trainee, venue, navigation and healing remain support; not a wild-capture policy |
| Recovery | Supported goal choice in measured collection contexts; battle replacement choices | Completing blackout dialogue or a programmed healing trip is not strategic learned recovery |
| Story routing | A measured Model141 destination contrast; not all story decisions | Cartridge graph, prerequisites, trainer selection and much progression remain supporting code |

The additive story actor's 72/128 wins versus K's 66 required349decisions versus276.
The original efficiency gate failed; explicit owner acceptance permits bounded DEVELOPMENT only.
The latest routing stop is missing forced-motion endpoint geometry. Longer neutral waits can
settle movement but do not qualify a route. Verification must read actual postconditions:
the full-party Viridian Center visit did not change the recovery anchor from Celadon.

## Historical integration: battle lifecycle versus funding contract

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

Model141 has141 fitted outcomes,96 successes and58 economy-qualified outcomes from related
development states, including four unit-weight teacher gift lessons. Its primary collection
save is109/124 registrations. The separate earned story save has17registrations and seven badges;
they must not be merged. Wild preparation XP is game progress, not a model fit.

J has318 physical TRAIN contexts from four origins. Its unused generated-team comparison was9/24
wins versus H7/24: descriptive learning evidence, not statistically conclusive mastery.
Natural attack/switching probes provide additional scoped evidence. DEVELOPMENT is not fitting data.
Teacher construction may edit isolated TRAIN states; no such intervention is exposed as a final
player action. Semantic emulator/cartridge observations are privileged inputs, not pixel-only play.
LLMs develop and review software; they do not secretly supply live model choices.

## Code map

| Concern | Starting points under the Python package |
| --- | --- |
| Goal runtime | `red_goal_context.py`, `red_autonomous_collection.py`, `red_resource_goal_router.py` |
| Trainer binding | `red_learned_trainer.py`, `red_routed_trainer_funding.py` |
| Story combat and rewards | `red_story_battle.py`, `red_gym_reward.py` |
| Preparation and routing | `story_preparation.py`, `red_wild_preparation.py`, `gen1_story_routing.py` |
| Actor and learning | `red_trainer_practice_episode.py`, `red_trainer_practice_outcome_policy.py`, `red_trainer_practice_fit.py` |
| Decision logs | `red_trainer_practice_log.py` |
| Resource verifier | `red_trainer_funding_battle.py` |
| Registration | `registration_memory.py`, `registered_collection.py` |
| Main entry | [Bounded collection runner](../scripts/run_red_autonomous_collection.py) |

[Latest evidence](evidence/red-giovanni-readiness-2026-09-22.json) ·
[Research record](research-retrospective.md) ·
[Setup](getting-started.md) · [Roadmap](model-first-roadmap.md) ·
[Historical architecture](history/architecture-through-2026-09-10.md)
