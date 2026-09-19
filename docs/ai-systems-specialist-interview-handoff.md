# AI systems interview handoff

Current checkpoint: September19,2026. Historical reports remain evidence, not instructions.

## Product and authorship

Build a transferable Pokémon player, beginning with Red, that finishes stories and accumulates
one shared verified registered Pokédex. Pete Andrews owns the product, priorities, acceptance
criteria and validation. AI coding assistants contributed implementation and review. Do not
present this as wholly hand-written or already completed.

## Verified capabilities

| Evidence | Result | Limitation |
| --- | --- | --- |
| Collection development |96/124 registrations,74 specimens,198 cash | Not a fresh run |
| Goal model137 |137 examples,92 successes,58 economy-qualified | Related development states |
| Battle training |318 TRAIN contexts, four origins | Supported small battle domain |
| Unused generated3v3 | J9/24 wins; H7/24 | Descriptive, not statistically conclusive |
| Natural Brock | J6/6; H5/6; first-legal0/6 | Two origins × three timings; one own Pokémon |
| Earned natural switching | Two wins, two voluntary switches,33 decisions | Same two origins; not six-member mastery |
| Main-player battle entry | Four J decisions; exact failure retained | Funding goal failed; battle unfinished |
| Fresh Red acceptance |0/5 | No fresh start-to-finish model-directed completion |

The main-entry probe used three earned Potions and a new trainer. J switched once and selected
three attacks. Wartortle fainted; the existing no-faints funding guard stopped before replacement.
It earned no payout. This verifies wiring/failure handling, not reliable autonomous funding.

## Architecture and stack

Observe coherent state → semantic goals → learned selection → bounded skills → independent
verification → saved evidence → eligible outcome learning.

| Layer | Technology / responsibility |
| --- | --- |
| Runtime | Python3.11+, PyBoy2.7.0 |
| Observation | Revision-specific readers; semantic policy-facing state |
| Goal learner | NumPy regularized multi-outcome option values with declared exploration |
| Battler | Three learned heads: move, attack/switch control, replacement target |
| Mechanics | Cartridge maps/encounters; deterministic navigation and menu execution |
| Memory | SQLite shared registrations; separate local flags and physical inventory |
| Persistence | SHA-256 bindings, create-once records, exact endpoints and decision logs |
| Verification | pytest, Ruff, mypy, documentation/private-artifact guards |
| Viewer | Read-only dashboard distinguishing live runtime from saved evidence |

No LLM supplies each gameplay action. Coding agents are development collaborators. Source
interfaces prevent accidental misuse, not malicious-code access in a security sandbox.

## Authority and integrity

- The model selects declared semantic alternatives; only executors issue controller inputs.
- The referee verifies outcomes and cannot substitute a better action.
- J is bound per run, not installed as a global controller replacement.
- Wild-capture and Elite Four controllers are unchanged.
- Learned trainer actions share player action/frame budgets and resource checks.
- Failures preserve real costs and saves rather than resetting into success.
- Disclosed teacher assistance is allowed in TRAIN scaffolding, not the final actor.
- DEVELOPMENT is never silently fitted; timing variants are not independent origins.

## Difficult problems and lessons

The central challenge is composing learned authority with reliable mechanics without counting
teacher success, test coverage or infrastructure as model competence. Coherent observation,
changing geometry, dialogue, crash continuation, outcome labels, evaluation leakage and shared
registration accounting are major engineering concerns.

A first action followed by a strong teacher is not equivalent to one followed by the learner.
Measuring16 training contexts under learner continuation produced J and a limited unused-team gain.

A no-faints funding goal can fail while a battle still has a living reserve and a valid replacement
decision. The checkpoint preserves this contract mismatch; it does not label the unfinished battle
a win or a completed loss. General battle completion and strict funding acceptance must be separated.

## Remaining product sequence

1. Resolve that lifecycle/recovery boundary with a bounded retained-state test.
2. Resume useful model-selected collection and sustainable legitimate income.
3. Complete fresh model-directed Red with Champion/Hall of Fame and124 native registrations.
4. Verify the deferred-dependency ledger, then test an unfamiliar compatible Red modification.
5. Learn Crystal and continue through at least Emerald.

Mew and unavailable version/link/event dependencies await legitimate later sources. Registration
is required, not level100 or simultaneous living forms. Red/Blue linking is desirable later,
not permission to fabricate owned flags.

## Pete's interview-safe role

“I defined the product and acceptance criteria, directed AI coding and review agents, challenged
shortcuts and focus drift, and validated outcomes against preserved gameplay evidence.
My contribution is systems direction and evaluation, including deciding what evidence establishes.”

[Mission](../MISSION.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) · [Handoff](../HANDOFF.md) ·
[Integration evidence](evidence/red-player-battler-integration-2026-09-19.json) ·
[Architecture](architecture.md) · [Roadmap](model-first-roadmap.md)

Private ROMs, saves, datasets and fitted models are not distributed. Superseded interview details
remain in Git and the [historical archive](history/README.md).
