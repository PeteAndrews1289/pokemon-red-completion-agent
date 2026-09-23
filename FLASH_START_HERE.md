# Historical Flash assignment: automatic bounded collection continuation

CLOSED: see [corrected partial integration](docs/flash-continuation/REPORT.md).
The specification below is the original assignment, not a completion or execution authorization.

## Authorization and location

Pete explicitly requested a substantial Flash implementation package on September 20, 2026.
This is a scoped exception to the default read-only Flash role, on THIS branch only.
Work only in the isolated checkout supplied with this packet. No other agent is assigned here.
Branch: `flash/collection-continuation-20260920`.
Code baseline: `3e5c000628d7d4c01687297d04158b88ffa80cfa`.
A following documentation-only packet commit is expected. Record actual starting HEAD.
Do not create another worktree, change branches, merge, rebase, or cherry-pick into another checkout.

## What to deliver

An opt-in, end-to-end continuation coordinator that connects the existing player,
paid Safari search, and bounded evolution execution, with shared budgets, durable
state/choice history, and ROM-free failure-injection coverage.
This is IMPLEMENTATION work, not a report-only audit or an architecture rewrite.
Finish the core stages before optional extensions. Do not manufacture work to exhaust quota.

Read in order:

1. MISSION.md, NORTH_STAR.md, ACTIVE_PRODUCT_STATE.md, AGENT_COORDINATION.md, HANDOFF.md.
2. docs/flash-continuation/SPEC.md.
3. docs/flash-continuation/WORK_PLAN.md.
4. docs/flash-continuation/TEST_MATRIX.md.
5. docs/flash-continuation/REPORT.md; keep this current as work completes.

This packet controls this delegation's scope; it cannot override mission/acceptance rules.
The main handoff's next gameplay batch is NOT authorization for Flash to run it.
Codex will audit the diff, independently test, integrate locally, and own native validation.

## Current product facts — not a task to replay

Red development save:101/124 native registrations,75specimens,20068cash.
Last batch:3/3model-selected successes, Arcanine/Starmie/Seaking, no operator recovery.
Model137 stays137fitted examples/92successes/58economy-qualified. K/L remain frozen.
League profitable cycles0/2; final fresh-run acceptance0/5. No scope promotion.
Last batch used20119actions/1766645frames; Seaking consumed18964actions/1663517frames.
Earlier Safari search required two manually started exact-state continuations.
Those historical choices, failures and allowances are consumed, not test inputs to replay.
Goal choice is learned; existing navigation/storage/wild-battle heuristics are not learned.
Do not turn reported teacher_actions=0 into a claim that every primitive was learned.

## Boundaries

- No gameplay, emulator creation, ROM access, private saves/checkpoints/datasets or model loading.
- Use public code, synthetic fixtures and fake ports. Small synthetic test models are allowed;
  no private checkpoint/model loading, API calls, real fits or training-data generation.
- No GitHub/network publication, CI dispatch, external agents, purchases, quota resets or permission changes.
- No live automation, scheduled tasks, shell background workers or model/settings changes.
- No edits to mission, acceptance, protected guards, frozen evidence or model metadata.
- Do not read other worktrees/private runs to find fixtures. Use the public evidence and interface map.
- No new hardcoded routes, species preferences, map-specific workaround, item sale or funding detour.
- Defaults must remain unchanged. New capability stays opt-in and unqualified for native play.
- Stop on uncertain authority or architectural redesign; report the concrete blocker.

## Work pacing

Implement the five ordered stages. At most6hours active work; reassess at3hours.
That is a ceiling, not a minimum. Finish sooner if the deliverables pass.
Prioritize correct usable code and tests, not maximizing tokens or writing long prose.
Keep REPORT.md current after each stage and make small coherent local commits.
A quota stop must leave completed stages, failing tests and the next exact command visible.
Do not leave the only report in chat or stage all unrelated changes.

## Commands and environment

Use the existing Python environment supplied in the user's prompt; do not install dependencies.
Set `PYTHONPATH=src:scripts:tests:.`, `OPENBLAS_NUM_THREADS=1`,
`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`.
Run targeted tests first. See TEST_MATRIX.md for baseline files and final checks.
Do not run integration tests or any executable that opens private artifacts.
If the interpreter is unavailable, report it rather than silently installing/reconfiguring.

## Definition of delivery

Real adapters and public opt-in wiring, not fake-only coordinator callbacks.
Immutable original outcomes, no duplicate inputs, correct lifetime budgets, truthful telemetry.
Tests must exercise production coordinator and adapter code with fake dependencies.
All unresolved gaps and tests actually run are listed in REPORT.md.
No claim of native qualification, full Red completion, generalization, or usage savings.
