# Current development handoff

Updated September 10, 2026. This is the single operational summary; older reports are [historical](docs/history/handoff-through-2026-09-10.md).

## Goal and current scope

Build a learned player that finishes stories and accumulates verified Pokédex registrations across games. Red first; global registration, local owned flags and physical specimens remain distinct. No level-100 quota or simultaneous living-form requirement.

The active lane is registered-objective collection learning. The learned component chooses goals/destinations; deterministic skills execute mechanics. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md) before implementation.

## Last verified gameplay: batch Y

- Three of four goals succeeded: first-floor search failed, resupply succeeded, basement acquisition caught Onix, funding succeeded.
- **59 registrations, 51 physical specimens, 47 living species** independently verified.
- Two destination outcomes fitted: **54→56 examples**. Both deterministic safety steps added no examples.
- Saved in Rock Tunnel B1F, map232 row5 col4; field-ready, outside battle, no pending trainer.
- Supplies: two capture items and1,338 money. Gameplay is stopped.
- [Collection report](docs/work-sessions/2026-09-10-post-merge-collection.md) · [Learning evidence](docs/evidence/red-post-merge-collection-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-post-merge-collection-saved-2026-09-10.json).

Exact continuation identities:

- Episode: `red-registered-collection-20260910-y-04-causal`
- Checkpoint: `3bae92f79cdd4c96bd8b27872b9a9e9e21ac636026720e8f6afcd0c0a1efc553`
- Model: `db06ba8347672e02a37bffb880a79e3366c751527d12e37d34483708c6d1a54b`
- Corpus: `30531f5fe09bd50e2910f2956fd65c96c0f24b02761b4f75e588bc0a0d4f2358`

Private storage locations and complete continuation arguments remain in private operational notes, not Git.

## This session

PR236 merged as `755ac224` after required CI passed. Y ran on that source with no runtime change, consuming four fresh steps in997.971seconds. Both actual destination choices exposed five alternatives; the proposed Mt. Moon destinations under safety resupply were not played or fitted.

The Y launcher is consumed and must never run again. Y01 failed search and Y03 successful capture each added one example; Y02/Y04 were nontraining safety support. Y04 is the latest save, but the latest actual fit is Y03/model56. Preserve this distinction.

## Next bounded development session

1. Confirm this handoff against saved evidence and private operational notes.
2. Continue from Y with all four Y checkpoint/source transitions, including support. Use the last actual fit, not an assumed fit on the final step. No new Y evolution transition was recorded. Do not restore X as latest or retry Y.
3. Run a short fresh goal-choice batch. Preserve failed costs and let the model choose supported alternatives.
4. Bound preparation optimization to30minutes. The earlier profile measured52.65seconds in preparation,40.39cumulative in history reconstruction. Repeated validation is a measured cost, not proof of a safe cache or a speedup. Any reuse must reject changed artifacts.
5. Verify saved collection/model outcomes, then update the current summary and append one dated session report.

Travel capture followed by route resumption remains unqualified: its named checklist is1/3, not a whole-project percentage. Stone evolution and broader collection mechanics remain incomplete. Do not force a destination just to close a checklist.

No full replay, sealed Red evaluation, Crystal execution, consumed-trial retry or automatic specimen release. New independent performance claims need genuinely separate evaluation lineages.

## Documentation and review

Keep this file current by replacing sections, not stacking new “Current” headings. Preserve details in [session reports](docs/work-sessions) and [historical index](docs/history/README.md). See [roles](AGENT_COORDINATION.md) and [next-step strategy](docs/model-first-roadmap.md).
