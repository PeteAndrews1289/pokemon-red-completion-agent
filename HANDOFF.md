# Current development handoff

Updated September 10, 2026. This is the single operational summary; older reports are [historical](docs/history/handoff-through-2026-09-10.md).

## Goal and current scope

Build a learned player that finishes stories and accumulates verified Pokédex registrations across games. Red first; global registration, local owned flags and physical specimens remain distinct. No level-100 quota or simultaneous living-form requirement.

The active lane is registered-objective collection learning. The learned component chooses goals/destinations; deterministic skills execute mechanics. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) before implementation.

## Last verified gameplay: batch X

- Four successful goals: resupply, Mt. Moon B2F acquisition, safety-driven resupply, restoration.
- Clefairy caught; **58 registrations, 50 physical specimens, 46 living species**.
- Three admitted choices fitted: **51→54 examples**. The deterministic safety step added no example.
- Saved at Mt. Moon Pokémon Center, map68 row3 col3; field-ready, outside battle.
- Supplies: two capture items and938 money. Gameplay is stopped.
- [Collection report](docs/work-sessions/2026-09-10-collection-continuation.md) · [Learning evidence](docs/evidence/red-collection-continuation-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-collection-continuation-saved-2026-09-10.json).

Exact continuation identities:

- Episode: `red-registered-collection-20260910-x-04-causal`
- Checkpoint: `6c0fbbfb89a5877c58239f39182c1519fb3c09e650a967b1c64760e7204a0da8`
- Model: `e972cca70f12267c841a2885ed06c6dba26a8fc7d98396709aa6b095c15d1b46`
- Corpus: `074e47c312b975e72d2aadc4d3f8aaeaec51782b3f9b7e9a21eea681623be239`

Private storage locations and complete continuation arguments remain in private operational notes, not Git.

## This session

The user redirected work to public presentation and merge before the next gameplay batch. A read-only preparation profile completed in52.65seconds: continuation reconstruction accounted for40.39seconds cumulative, with repeated episode/checkpoint validation. Instrumentation affects timing; this is not an unprofiled benchmark or a measured speedup.

The prospective Y launcher has **not run**. No Y gameplay declaration, controller input, prediction or fit exists. X remains latest. Documentation cleanup does not increase model counters.

## Next bounded development session

1. Confirm this handoff against saved evidence and private operational notes.
2. Continue from X with all four X checkpoint/source transitions, including its unfitted safety support. Do not replay X or restore older endpoints as latest.
3. Run a short fresh goal-choice batch. Preserve failed costs and let the model choose supported alternatives.
4. Keep preparation optimization bounded; any reuse of validation must still reject changed artifacts. No broad cache project.
5. Verify saved collection/model outcomes, then update the current summary and append one dated session report.

Travel capture followed by route resumption remains unqualified: its named checklist is1/3, not a whole-project percentage. Stone evolution and broader collection mechanics remain incomplete. Do not force a destination just to close a checklist.

No full replay, sealed Red evaluation, Crystal execution, consumed-trial retry or automatic specimen release. New independent performance claims need genuinely separate evaluation lineages.

## Documentation and review

Keep this file current by replacing sections, not stacking new “Current” headings. Preserve details in [session reports](docs/work-sessions) and [historical index](docs/history/README.md). See [roles](AGENT_COORDINATION.md) and [next-step strategy](docs/model-first-roadmap.md).
