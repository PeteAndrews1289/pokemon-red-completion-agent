# Completion contract

## Success condition

A run completes Pokémon Red only when the referee observes both:

1. the verified Champion-defeated event; and
2. the Hall-of-Fame map or sequence state.

Entering the Champion room, winning an isolated battle, reporting eight badges, or reaching an
adjacent map is insufficient.

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

## Reporting

Every declared attempt counts. Report:

- attempts, successes, and terminal reasons;
- actions and wall time;
- objectives completed and recovery events;
- battles, blackouts, loops, and restarts;
- teacher/fallback usage;
- model calls, if any; and
- exact final evidence.

One completion is a milestone. A reliability claim requires a preregistered repeated-run threshold;
the initial target is at least 8 successes in 10 held-out clean-start attempts.
