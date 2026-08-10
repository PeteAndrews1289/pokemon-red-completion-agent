# Current capability audit — 2026-08-10

## Executive verdict

The project has crossed two important lines. First, one noncanonical, derived-timing clean start
completes Pokemon Red through Hall of Fame with all six learned roles active and battle-teacher
queries forbidden. Second, the next fresh root legitimately lost the lab rival and the teacher now
continues through Misty without rerolling or claiming a win. That second result matters because it
turns a single successful trajectory into the beginning of a real outcome-conditioned curriculum.
Neither result is yet a reliability campaign or proof that a monolithic model learned Pokemon from
pixels.

The repaired loss branch trains only on bounded level-four-or-lower Route 1 Pidgey/Rattata, returns
to the Viridian Center after every lesson, and authenticates full HP, clear status, and restored PP
before continuing. It reaches level nine with Bubble, clears the Forest trainer and Brock, survives
Route 3, weakens and catches Zubat with the sole ball, balances the reduced-money route, accepts
Wartortle's evolution, defeats Misty, and preserves the level-24 Bite lesson for the Vermilion
Rocket. The long replay that proves this prefix began on a dirty tree with temporary tracing, so it
is diagnostic rather than promotable. The exact committed source now needs its own clean-power
replay.

Counted v95 remains deliberately unopened at **0/10**. Crystal, cross-title transfer, and a living
Pokedex remain future milestones.

## Strongest result this session

Seed `990026` completed the full game from power-on under its derived timing schedule:

- 49,085,008 emulator frames and 699,050 macro actions;
- 21/21 selected executable objectives and 36/36 observed semantic objectives;
- 74/74 scheduled battles;
- 3,165 high-level battle-control decisions, including 55 typed non-move actions;
- 3,110 learned move decisions;
- 12/12 learned switch-target bindings with zero fallback;
- 61,497 training-control decisions at 100% agreement and zero operational errors;
- 120,161 trainee/venue decisions, including 119,271 genuine choices at 99.5867%; and
- zero battle-teacher query, teacher fallback, safety fallback, or low-confidence fallback.

The exact receipt is
[perturbation 12](evidence/portable-clean-start-six-role-perturbation-12-qualification-2026-08-10.json).
It is intentionally marked `promotion_eligible: false` because it is an uncounted rehearsal.

## Model selection was causal, not cosmetic

The high-level control artifact was rebuilt from a 3,259-label full-run lineage using feature schema
v5. The schema removes raw active party-slot identity and keeps the representation permutation-safe.
A regression test permutes the party and requires the same semantic action.

The calibration sweep also demonstrates why top-line accuracy was not the selection rule:

| Power | Accuracy | Balanced accuracy | Live result |
| ---: | ---: | ---: | --- |
| 0.10 | 99.3918% | 90.7879% | Lorelei passed; full replay missed Koga's accuracy setup |
| 0.15 | 99.2958% | 92.6601% | Lorelei passed; not selected |
| 0.20 | 99.1677% | 96.7996% | Lorelei passed; full seed `990026` passed |
| 0.25 | 99.0397% | 96.7779% | Lorelei passed; full replay requested unavailable Route 24 recovery |

Power `0.20` was selected because it preserved rare-class behavior in live causal execution. A model
with higher ordinary accuracy failed the task.

## What the code now proves

The runtime is a hybrid learned agent, not a single end-to-end policy:

1. A learned objective ranker chooses among executable semantic objectives.
2. Bounded specialists perform navigation, dialogue, acquisition, and known mechanics.
3. A learned high-level battle controller chooses attacks, recovery, boosts, and switches.
4. A learned move policy chooses ordinary legal moves.
5. A learned candidate-relative switch head binds living reserves without party-slot identity.
6. Learned training heads choose when to seek, fight, flee, heal, or stop and which trainee/venue to
   use.
7. Independent observers and chapter reports verify outcomes and reject unsupported success.

That architecture is appropriate for the stated transfer goal: title-specific mechanics can be
replaced while semantic decisions, candidate-relative features, curricula, and evidence contracts
remain stable.

## What changed in source

The session published thirteen source-bound repairs before the latest checkpoint:

- semantic trainer-switch versus evolution handling;
- fossil-route money accounting;
- collision-aware and bounded Mart customer handling;
- schedule reentry identity;
- DUX's low-HP boundary;
- portable battle-control label collection;
- opponent-healing history;
- party-permutation invariance for high-level control;
- authenticated lab-loss recovery and immutable outcome threading;
- a semantic level-six recovery floor;
- correct Red Forest species identifiers; and
- a balanced Kakuna/Weedle recovery sequence; and
- a loss-aware Forest lesson sequence with an explicit safe-target level ceiling.

Commit `d9a7beb` adds the subsequent loss-route curriculum and downstream resource, capture,
move-selection, and semantic switch-prompt repairs. Its v95 registry identity is
`829c0fa8236ac976c37912559d4c6dbf543e0938694e22756b4d56f8456d09c4`. Public-artifact and
documentation checks, regenerated registry verification, Ruff, mypy over 128 source modules, and
2,227 tests pass; three integration tests are deselected and one expected failure remains expected.
GitHub Actions run `31368161467` independently passed the same source commit.

## The new branch is the right kind of work

Seed `990027` lost the lab rival before any learned battle or training decision. Treating that loss
as a valid game outcome is essential if the teacher is meant to cover Pokemon rather than replay a
single lucky speedrun. The published branch now distinguishes win from loss, preserves the outcome
after later battles overwrite `BATTLE_RESULT`, and recovers the level deficit without pretending
the rival was beaten.

The clean published failure at 171,585 frames remains preserved in
[perturbation 13](evidence/portable-clean-start-six-role-perturbation-13-failure-2026-08-10.json).
It led to the Route 1 redesign. Temporary traced replays then verified thirteen low-defense lessons
with thirteen Center heals, the weaker Pewter and Cerulean ledgers, every required Route 3 trainer,
one weakened Zubat capture, Misty, evolution, and the Bite transition. Those traces are explicitly
non-promotable because they began outside the final source digest. This is the correct boundary:
the repair is implemented and deeply exercised, but the claim waits for a clean replay.

## Honest capability rating

| Capability | Rating | Evidence |
| --- | ---: | --- |
| Deterministic Red expert | 9/10 | Repeated full completions and bounded chapter contracts |
| Learned objective selection | 8/10 | Full clean-start authority, one real branch, no expected labels |
| Learned battle control | 8/10 | Full teacher-free completion with typed recovery/boost/switch actions |
| Learned balanced-team curriculum | 8/10 | Full six-member development and live training authority |
| Perturbation reliability | 5/10 | One full derived-timing pass and one deep loss-route diagnostic |
| Learned navigation | 2/10 | Navigation remains mostly specialist code with semantic receipts |
| Cross-game transfer | 1/10 | Architecture and benchmark exist; no Crystal causal result yet |
| Living-Pokedex completion | 1/10 | Contracts exist; no complete acquisition/trade campaign yet |

## Recommended next sequence

1. Replay `990027` from clean power and exact committed source until it either completes or exposes
   a later causal boundary. Preserve every failure and its source identity.
2. If it completes, run at least one fresh uncounted root. Only then freeze and open v95.
3. Run the ten-root v95 campaign without code or model changes. Eight valid successes are the
   minimum promotion gate.
4. After Red reliability closes, build the thin Crystal observer/mechanics adapter and run the
   predefined transfer probes before authoring a complete Crystal teacher.

## Portfolio and video story

The strongest story is no longer merely “an AI beat Pokemon.” It is: **a six-role learned stack
completed Red under a timing perturbation, and the very next seed revealed that the teacher—not the
models—did not know how to lose the first battle.** The project then refused to reroll,
authenticated the loss, learned thirteen local lessons with a heal after each, and carried the
weaker economy through Misty and evolution. Every newly exposed assumption became a state contract
rather than a seed reroll.

That story shows model evaluation, systems debugging, experiment lineage, calibrated claims, and
the difference between solving one trajectory and building an agent that can survive a game.
