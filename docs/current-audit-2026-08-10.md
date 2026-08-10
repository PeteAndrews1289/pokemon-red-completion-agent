# Current capability audit — 2026-08-10

## Executive verdict

The project has crossed an important line: one noncanonical, derived-timing clean start now completes
Pokemon Red through Hall of Fame with all six learned roles active and battle-teacher queries
forbidden. That is stronger than the earlier canonical completion because it proves the composed
stack can survive at least one real timing perturbation. It is still one uncounted root, not a
reliability campaign and not a claim that a monolithic model learned Pokemon from pixels.

The next fresh root did exactly what a useful evaluation should do: it produced a legitimate loss
to the lab rival. The old teacher assumed that battle must be won. The published code now recognizes
the cartridge's real loss state, carries that outcome across later mutable battle RAM, and reaches a
bounded Viridian Forest recovery. The remaining failure is narrower: that extra recovery changes
encounter RNG, experience, HP, and Tackle PP, so the victory route's three fixed Kakuna lessons are
not a valid suffix. The current clean-source replay completes two loss-specific lessons and fails
closed only when no safe third Weedle appears within the single-origin bounded search. Diagnosis
shows the safe design is to earn the loss-only experience on Route 1, heal in nearby Viridian City,
then enter the unchanged Forest curriculum from a restored semantic floor.

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

The session published thirteen source-bound repairs after the previous checkpoint:

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

The clean tree at `c2aeb12` passes public-artifact and documentation checks, regenerated registry,
Ruff, mypy over 128 source modules, and 2,217 tests; three integration tests are deselected and one
expected failure remains expected.

## The new failure is the right kind of work

Seed `990027` lost the lab rival before any learned battle or training decision. Treating that loss
as a valid game outcome is essential if the teacher is meant to cover Pokemon rather than replay a
single lucky speedrun. Six small published changes now distinguish win from loss, preserve the
outcome after later battles overwrite `BATTLE_RESULT`, and recover the level deficit without
pretending the rival was beaten.

The latest official replay from clean published source reaches 171,585 frames, completes two
post-loss lessons, and fails because it cannot find a safe level-four-or-lower third Weedle from the
same search origin. Private instrumented probes established both sides of the safety boundary: a
level-three Caterpie leaves the level-seven starter healthy but short of Bubble, while a level-five
Weedle reaches level eight and Bubble at only 3/25 HP while poisoned. Tail Whip is not a PP solution
against Kakuna because Harden cancels the defense reduction. Those probes are explicitly
non-promotable because their runtime monkeypatches were outside the source digest. The public
failure receipt records both the official boundary and the diagnostic limitation:
[perturbation 13](evidence/portable-clean-start-six-role-perturbation-13-failure-2026-08-10.json).

## Honest capability rating

| Capability | Rating | Evidence |
| --- | ---: | --- |
| Deterministic Red expert | 9/10 | Repeated full completions and bounded chapter contracts |
| Learned objective selection | 8/10 | Full clean-start authority, one real branch, no expected labels |
| Learned battle control | 8/10 | Full teacher-free completion with typed recovery/boost/switch actions |
| Learned balanced-team curriculum | 8/10 | Full six-member development and live training authority |
| Perturbation reliability | 5/10 | One derived-timing pass; next root exposes a real optional-loss gap |
| Learned navigation | 2/10 | Navigation remains mostly specialist code with semantic receipts |
| Cross-game transfer | 1/10 | Architecture and benchmark exist; no Crystal causal result yet |
| Living-Pokedex completion | 1/10 | Contracts exist; no complete acquisition/trade campaign yet |

## Recommended next sequence

1. Move the authenticated-loss catch-up to Route 1's low-defense Pidgey/Rattata venue, where the
   Viridian Center is available before the Forest curriculum.
2. Prove the Center visit restores HP, status, and PP, returns to the exact expected route gate, and
   preserves the authenticated lab outcome. Then reuse the unchanged three-Kakuna curriculum.
3. Replay `990027` from clean published source until it either completes or exposes a later causal
   boundary. Preserve every failure.
4. Run at least one fresh uncounted root after `990027` passes. Only then freeze and open v95.
5. Run the ten-root v95 campaign without code or model changes. Eight valid successes are the
   minimum promotion gate.
6. After Red reliability closes, build the thin Crystal observer/mechanics adapter and run the
   predefined transfer probes before authoring a complete Crystal teacher.

## Portfolio and video story

The strongest story is no longer merely “an AI beat Pokemon.” It is: **a six-role learned stack
completed Red under a timing perturbation, and the very next seed revealed that the teacher—not the
models—did not know how to lose the first battle.** The project then refused to reroll, authenticated
the loss, recovered toward the same semantic curriculum, and exposed a second-order PP budget.

That story shows model evaluation, systems debugging, experiment lineage, calibrated claims, and
the difference between solving one trajectory and building an agent that can survive a game.
