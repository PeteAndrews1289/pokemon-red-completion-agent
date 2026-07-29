# Completion contract

## Success condition

A run completes Pokémon Red only when the referee observes both:

1. the verified Champion-defeated event; and
2. the Hall-of-Fame map or sequence state.

Entering the Champion room, winning an isolated battle, reporting eight badges, or reaching an
adjacent map is insufficient.

## Clean power-on

The supported runtime starts PyBoy with its packaged DMG-compatible boot ROM, immutable verified
game ROM bytes, blank cartridge RAM, no RTC input, no loaded state, and no human window input.
PyBoy is stopped without saving. This proves a fresh emulator/game start; it does not claim
cycle-identical timing to original Nintendo boot-ROM hardware.

## Frozen evaluation identity

Before an official run begins, record:

- repository commit;
- dirty-worktree status;
- ROM SHA-1 and SHA-256;
- Python, emulator, and dependency versions;
- objective-graph digest;
- model and optimizer digests, when applicable;
- configuration digest;
- random seed and initial timing perturbation;
- action and wall-time budgets; and
- assistance class.

Source, prompts, route data, models, and configuration remain frozen until the run ends.

## Permitted during training

- private emulator snapshots and cartridge saves;
- a disclosed walkthrough and objective graph;
- read-only game RAM, tiles, collision maps, and pixels;
- deterministic teachers and scripted corrections;
- demonstrations, behavioral cloning, DAgger, and local curriculum RL;
- human review between runs; and
- model or code changes between declared training iterations.

## Forbidden during official evaluation

- human-selected controller actions;
- teacher or oracle fallback in a learned-stack evaluation;
- save-state restoration or rollback;
- code, prompt, route, configuration, or weight changes;
- importing memory from another evaluation run; or
- silently replacing an action selected by the evaluated actor.

Process-crash recovery may be evaluated separately, but it is not a clean-run completion unless the
game continues without restoring or rewinding emulator state.

## Evaluation lanes

Results from different actors and assistance conditions are never pooled:

1. **Exact deterministic teacher:** a frozen route repeats from clean power-on. This establishes a
   reproducible reference policy, not learning or robustness.
2. **Perturbed/multi-seed teacher:** the frozen teacher runs preregistered timing/RNG schedules.
   Reports include the encounters, positions, damage, status, resources, and recoveries actually
   observed. This measures teacher coverage, not learned generalization.
3. **Learned/hybrid multi-seed policy:** frozen model weights and configuration run held-out
   timing/RNG schedules from clean power-on. Teacher/oracle fallback is disabled; the actor chooses
   from semantic observations.

Every full-game attempt in every lane starts clean, counts toward its declared denominator, and
forbids save restoration, rollback, or cross-run memory. Training-only snapshot suites may test
targeted nearby positions, menu states, encounters, damage, status, and recovery, but they are
component evidence and cannot be reported as clean-run completion.

The evaluation seed identifies a frozen harness schedule, including initial timing perturbation;
it is not a claim that the cartridge exposes a user-facing seed. Training/tuning seeds and
held-out evaluation seeds must be disjoint and declared before the evaluation series.

## Reporting

Every declared attempt counts. Report:

- attempts, successes, and terminal reasons;
- actions and wall time;
- objectives completed and recovery events;
- battles, blackouts, loops, and restarts;
- teacher/fallback usage;
- evaluation lane, seed, timing schedule, and observed variation categories;
- model calls, if any; and
- exact final evidence.

One completion is a milestone. A reliability claim requires a preregistered repeated-run threshold;
the initial target is at least 8 successes in 10 held-out clean-start attempts.
