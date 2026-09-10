# Current development handoff

Updated September 10, 2026. Older results remain in dated reports and [history](docs/history/handoff-through-2026-09-10.md).

## Goal and scope

Build a learned player that completes stories and accumulates a shared registered Pokédex across games. Red first; global credit, local owned flags and physical stock stay separate. No level-100 or simultaneous-living-form requirement. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), then [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md).

## Latest verified save: AF01

- Cut-enabled acquisition reached Route 16 and caught Doduo.
- **62 global/local registrations, 53 specimens, 49 living species**, independently verified.
- **Model60 unchanged: zero new fitted choices.** One available capture goal meant forced singleton authority.
- One successful goal: **480 actions / 26,868 frames**; one encounter, one capture, paralysis support, one ball spent.
- Route16/map27, row5 col35; input-ready, outside battle, no pending trainer. Two capture balls and 138 money remain.
- The batch stopped at its one-goal limit after 392.530 seconds including preparation. Gameplay is stopped.
- [Session report](docs/work-sessions/2026-09-10-cut-collection-access.md) · [Outcome evidence](docs/evidence/red-cut-access-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-cut-access-saved-2026-09-10.json).

Exact identities:

- Episode: `red-registered-cut-access-20260910-af-01-causal`
- Checkpoint: `ac8cb149fc869c166f4ab1ede83b95bcc6e22e56ca5e08ebc6723fccee1caece`
- Manifest: `978ff7ac7cc9c2bf6bd9f351ae6a6441591a631567085eab05684ebc10f0df99`
- State: `68fe0eed489f8eccb20237a5e79d04864b9bfe66b43c459f2bde71cfc9b776fd`
- Model60: `260efe95e444c5035283a613442f84da2528ea1ad9b8c95a17c997fa881ecb0c`
- Corpus: `3ac77782801f56728484b6ea7926ffd48985e7d5757eadfdc8d9c80db3d2b8b3`
- Played source: `14116b475ee6325d307bf2ccb2bcf17b61985b1e`

The latest fit still belongs to AB. Preserve unfitted AC/AE/AF support artifacts and costs. Full arguments and audits remain private.

## Repair and qualification

A read-only AE comparison found no walking acquisition but one Cut-enabled source. The prospective `--capture-cut-transport` transition preserves old profiles and survives source retargeting. Navigation uses observed Cut capability and the existing field-move port; expanded inputs share the original action/frame budgets. Surf and Strength remain unavailable through this option.

430 targeted tests passed at closeout, including documentation checks. A separate overlapping group of 83 route/capture tests also passed; do not add overlapping counts. Configured mypy covered 470 source files. These are not a full-suite claim.

The primitive trace shows blocked movement, a field-menu sequence, then movement through the cartridge tree. The higher-level Cut receipt was not persisted, and a final-map comparison showed no remaining changed blocks. Do not fabricate a retained receipt or infer the reset cause. Preserve field receipts prospectively. The earlier incidental-arrival reporting repair remains unqualified by this destination capture; AB remains failed and capture/resume stays 1/3.

## Next bounded session

1. Start from AF01/model60, never replay AF or restore AE. Inherit AF's complete declaration and append the AF checkpoint, then `warp-safe-wild-source wild:Route16:grass` and `discovery-source wild:Route16:grass`, as prior source continuations do. Retain the existing capture-Cut flag. AF proposed that source; it did not sample among multiple destinations.
2. Check current resources and stock. Only two capture balls remain; establish legitimate funding before a long acquisition loop.
3. Qualify one observed Surf acquisition path using the existing field executor, with missing-badge/holder and blocked-water tests. Pair a genuinely new acquisition option with supported owned evolution so the learner has real alternatives.
4. Persist higher-level field receipts and measure preparation overhead while integrating that path. Do not start a separate broad infrastructure campaign.
5. Allow 60–90 minutes for one access/choice qualification, not full collection or independent reliability.

No full replay, sealed Red, Crystal, consumed retry, release or independent-performance claim. No stage exit changed.

## External work and publication

No external agents were dispatched in this session; no fresh Flash or Claude quota was queried. Flash's earlier isolated stone draft remains at local commit `895b4d6b`, with 40 tests passing after Codex corrections, **not integrated or live-qualified**. Its procurement, move-learning admission and native-provider work remain incomplete.

PR240 passed CI and merged as `8abdc7ab`. Played source `14116b47` is separately published and must remain recoverable. Publish this closeout as one tested batch; CI is not a dependency for ordinary development gameplay.
