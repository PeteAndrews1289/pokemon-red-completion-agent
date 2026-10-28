# Ordered implementation stages

## 0. Map and baseline — no broad audit

Read the actual functions and their tests, then put a compact implementation map in REPORT.md.
Run baseline targeted tests before changing executable code. Record existing failures separately.
Use this source map:

- src/pokemon_red_completion/red_autonomous_player.py:
  run_autonomous_options; run_autonomous_goal_continuation; continuation_binding; _write/_record.
  Default player stops on error; wall time currently gates next-decision admission only.
  Continuation rebinding is evolution-only; don't widen it with an untyped wildcard.
- scripts/run_red_autonomous_collection.py:
  _verify_goal_continuation, _verify_reserve_lineage, snapshot, runtime/limiter setup,
  --inspect, continue_selected_goal and include_league_funding.
- src/pokemon_red_completion/red_autonomous_collection.py:
  autonomous_collection_options and autonomous_evolution_continuation_bindings.
- src/pokemon_red_completion/red_autonomous_capture_recovery.py:
  existing recovery validator is narrow and expects unsafe failed acquisition;
  do not weaken it to admit safe paid-search stops. Add a separate typed path.
- src/pokemon_red_completion/red_acquisition.py:
  RedAreaExecutionPolicy, RedAreaExecutionError.reason_code, run_red_area_survey.
  Semantic-action limit is an exception; capture_items_exhausted currently conflates callbacks.
- src/pokemon_red_completion/red_safari_acquisition.py:
  LiveSafariPatrol.resume_from_endpoint, LiveSafariAreaExecutor, session reader.
- src/pokemon_red_completion/red_indoor_safari.py, red_live_safari.py:
  paid admission, private area binding and registered-only capture catalog.
- src/pokemon_red_completion/red_indoor_collection_departure.py:
  normal observed indoor departure; do not replace with a fixed walk.
- src/pokemon_red_completion/goal_manager_composition_qualification.py:
  HardCompositionActionLimiter; preserve action accounting.
- src/pokemon_red_completion/executor.py:
  frame-budget wrappers, CountingExecutor, ReadOnlyController.
- src/pokemon_red_completion/red_live_option_menu.py:
  existing selection modes; preserve model/equivalent/safety distinctions.
- Public evidence: docs/evidence/red-recovery-connection-and-collection-2026-09-20.json
  and docs/evidence/red-celadon-collection-2026-09-20.json.

Output: module/API proposal, default compatibility plan and test baseline.
Proceed without another approval if within SPEC; report contradictions rather than broadening scope.

## 1. Typed boundary and shared budgets

Implement a small ROM-free core. Suggested module: collection_continuation.py.
Keep title-specific memory/map details behind adapters.
Validate configuration, finite counters, reservation/settlement, deadline and no-progress limits.
Represent continue-same-goal / replan / complete / safe-stop / ambiguous-stop explicitly.
A policy is prospectively declared; it never invents a goal based on the desired species.
Tests: core state transitions and budget/error matrix. Commit coherent passing stage.

## 2. Durable coordinator and resume

Suggested module: red_collection_continuation.py or a title-neutral journal plus Red adapter.
Connect intent/choice/dispatch/terminal/result records, authenticated chain and exclusive claims.
Add explicit resume from completed boundaries; uncertainty is a stop, not at-least-once execution.
A new process inherits remaining budgets and original goal lineage.
Use injected fake clocks and file faults; don't sleep in tests or create background processes.
Test crash before/after each publication boundary, duplicate claims, tampering and interrupted queries.
Commit core plus tests; update REPORT with exact durable formats.

## 3. Real adapter wiring

Connect paid Safari and existing evolution APIs, not only generic fake callbacks.
Extract minimal reusable pieces where runtime construction otherwise duplicates the existing script.
Keep new behavior off unless a plan explicitly selects it; default run stays stop-on-error.
An omitted or malformed opt-in must not silently activate continuation.
Use native session facts through existing readers; fake those dependencies in tests.
Do not open ROMs or start an emulator to validate this stage.
Typed search stop telemetry must distinguish balls, steps reserve, encounter cap, local quantum,
global budget and native session end. Preserve legacy report meanings/consumers explicitly.
Tests must execute real adapter assembly with fake ports, including shared ledger installation.
Public CLI must reject invalid plans before emulator construction.
Use a fake runtime factory for opt-in CLI tests to prove orchestration is actually connected.
Commit once targeted regressions pass.

## 4. Adversarial composition and diagnostics

Add seeded fake-environment scenarios across different budgets and interruption positions.
Mandatory scenarios are in TEST_MATRIX; test actual production core/adapter code.
Use a small deterministic seed set, not a costly random search or invented pass percentage.
Add a read-only campaign summarizer that authenticates records and checks reconciled totals.
Compare uninterrupted vs chunked fake runs for equivalent conserved-resource outcomes,
without assuming identical RNG trajectories or treating fixtures as independent native evidence.
Include one scenario with capture failures followed by success and one with no capture success.
If feasible, measure fake menu/verification timing separately; don't optimize real menu discovery here.
Commit complete test/report stage.

## 5. Package and self-review

Inspect the diff for authority leakage, reset paths, swallowed errors, new model inputs and privacy.
Check that all TEST_MATRIX cases map to named tests; mark gaps explicitly.
Run final targeted suite, lint touched code and applicable typing checks.
Regenerate collection registry metadata and --check using existing script if source changed.
Do not weaken guards or rewrite old evidence to get checks green.
Record exact commands/exit codes/counts, commits, changed files and limitations in REPORT.md.
Run docs/focus checks and documentation-surface tests before final commit.
No full suite unless targeted results justify it and it stays ROM-free/bounded;
exclude integration tests explicitly if using a broad invocation.

## Useful optional stretch — only after stages1–5

Add seeded crash/ledger tests across BOTH adapters and additional exception paths.
Add a concise read-only summary export for unresolved goal/cost/operator-intervention analysis.
Extend strict input validation and meaningful telemetry for cases already supported.
Do NOT add fishing/trade/legendary/League support, a new policy, UI, CI or generic plugin framework.
Stop when required work is complete; quota remaining is not a defect.

## Scope of edits

Allowed: new continuation modules/tests; the listed player/runner/Safari/evolution integration
files and minimal imported interfaces needed to connect them; this packet's REPORT.md.
Generated registry metadata is allowed through its existing generator only.
Do not edit unrelated code, README, mission, active focus counters, roadmap, historical evidence,
battle models, teachers, CI or acceptance configuration.
If a needed change falls outside this list, explain necessity in REPORT and stop that substage.
No merge or main-checkout modifications. Local commits on this branch only.
