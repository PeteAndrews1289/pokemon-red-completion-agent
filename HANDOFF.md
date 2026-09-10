# Current development handoff

Updated September10,2026. Older results remain in dated reports and [history](docs/history/handoff-through-2026-09-10.md).

## Goal and scope

Build a learned player that completes stories and accumulates a shared registered Pokédex across games. Red first; global credit, local owned flags and physical stock stay separate. No level100 or simultaneous-living-form requirement. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), then [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md).

## Latest verified save: AE01

- Paras8→Parasect24 completed through the existing bounded training skill.
- **61 global/local registrations,52 physical specimens,48 living species**, independently verified.
- **Model60 unchanged: zero new fitted choices.** AC healing and AE evolution were forced singleton goals.
- AC:80actions/5,316frames. AE:16,826actions/1,464,245frames. Combined16,906actions/1,469,561frames; no lost specimen or reset.
- Route11/map22,row6col0, input-ready, outside battle, no pending trainer; three capture items/138money. Gameplay stopped.
- AD had no executable goal and no gameplay. AE completed one of at most two goals, then stopped at another empty menu.
- [Session report](docs/work-sessions/2026-09-10-owned-evolution-access.md) · [Evidence](docs/evidence/red-evolution-access-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-evolution-access-saved-2026-09-10.json).

Exact identities:

- Episode: `red-registered-evolution-access-20260910-ae-01-causal`
- Checkpoint: `2f433f99febc8fa3a2be399539b29bd202f3ffc6e21be0cb70fe3a87f99a4a96`
- Manifest: `28bd491424992aaaa57602cfcc21505fcf1e46038184a37e08449022f1654198`
- State: `93e4539fa70fd6eac97a8e8deb2d5c09495a8a789bd5191a916792c53126b113`
- Model60: `260efe95e444c5035283a613442f84da2528ea1ad9b8c95a17c997fa881ecb0c`
- Corpus: `3ac77782801f56728484b6ea7926ffd48985e7d5757eadfdc8d9c80db3d2b8b3`
- Played source: `f7cc883bec3e0e96d911e156d2a4c098c643c05c`

The latest fit still belongs to AB. Preserve unfitted AC/AE support artifacts and costs. Full arguments and audits remain private.

## Repair and limitations

New owned-evolution proposals dropped transport settings. A read-only AC-state probe exposed Paras evolution by enabling existing Fly/indoor access. The new `--owned-evolution-fly-transport` option applies the same settings during admission and execution, retaining ordered transitions for future ancestry. Historical profile construction is unchanged.250targeted tests passed; configured mypy covered470source files.

AE initially refused unpublished source before private admission or input. The unchanged declaration resumed once after publication; no played/claimed trial was retried. Push tested development source before the next declaration; CI is not a development-play dependency.

The earlier travel-arrival summary repair is still not live-qualified: this session exercised evolution, not incidental capture. AB remains failed. Capture/resume remains1/3, not a project percentage.

## Next bounded session

1. Start from AE01/model60. Inherit AE's declaration; append its selected `evolution:46:47:24`, then `evolution-fly` and `indoor-fly-departure`, then the AE checkpoint. Keep the owned-evolution Fly opt-in. AE recorded no selected/proposed capture source.
2. Reorient after zero new learning examples: broaden executable mechanics, not empty-menu or cleared-source loops.
3. Qualify one generic Cut-enabled collection route using the existing field-move executor and observed HM/badge capabilities. Begin with read-only feasibility and changed-party/blocked-access tests. Do not merely relax walking-only guards or hand-route a species.
4. Expose real destination alternatives; fit only eligible actual outcomes. Estimate45–90minutes for first-access qualification, not full collection.
5. Stone evolution remains isolated. Seven missing stone targets have precursors, but no stones are carried; reserves, procurement and boxed access still need verification.

No full replay, sealed Red, Crystal, consumed retry, release or independent-performance claim. No stage exit changed.

## External work and publication

Flash3.8High completed a read-only audit and two-file isolated draft repair. Codex corrected three remaining fixtures and lint;40draft tests pass. Local draft commit`895b4d6b` is **not merged or live-qualified**. Move-learning admission, real menus, native provider and stone procurement remain unfinished.

Accepted: wrong mocked IDs, incomplete guards and missing integration. Rejected: blanket no-move-learning and mandatory Pokédex-modal claims after primary-source checks. See the session adjudication.

Refreshed Gemini-group allowance:85.74%five-hour/78.00%weekly remaining around20:08UTC; shared counters, not per-task usage. Both Flash tasks stopped; Claude unused. PR239 merged as`72b0c0d4` after green CI.
