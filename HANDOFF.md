# Current development handoff

Updated September 10, 2026. Earlier results remain in dated reports and [history](docs/history/handoff-through-2026-09-10.md).

## Goal and scope

Build a learned player that completes stories and accumulates one shared registered Pokédex across games. Red first; global credit, local owned flags and physical stock stay separate. No level-100 or simultaneous-living-form requirement. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), then [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md).

## Latest verified save: AJ01

- **64 global/local registrations, 54 specimens, 50 living species**, checked from the exact final save. All 53 prior specimens remain.
- AI01 exited Power Plant, flew to town and bought two Great Balls for 1,200 money:209 actions/12,588 frames, one verified Fly. Forced supply produced no training row.
- AI02 offered capture and restoration. The actual model chose restoration and succeeded:153 actions/5,424 frames. That real native choice fitted model61→62. The proposed Seafoam B4F destination was not played or separately fitted.
- AJ01 was a separately declared extra choice after AI's two-goal batch. The model-plus-exploration policy selected Seafoam B3F among seven destinations. It caught Shellder30 with one ball on Seafoam 1F, resumed travel to B3F, then failed to catch Seel33 with its remaining ball.
- AJ01 failed with the verified `capture_items_exhausted` reason:565 actions/40,633 frames. Its completed Surf and survey counts survived composition. The actual failed destination outcome fitted model62→63.
- Total: 927 actions/58,645 frames; combined batch elapsed 1,425.094 seconds including preparation. **One new registration: Shellder.** These are related development outcomes, not independent performance.
- Exact terminal: Seafoam B3F/map 161,row 9col 12; input-ready,battle 0; zero balls,593 money. Gameplay is stopped.
- [Session report](docs/work-sessions/2026-09-10-supply-transport.md) · [Outcome evidence](docs/evidence/red-supply-collection-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-supply-collection-saved-2026-09-10.json).

Exact identities:

- Episode: `red-registered-collection-20260910-aj-01-causal`
- Checkpoint: `c0e01cb2956b9346195fc8c5e8055f441b0b06a8e407710be789ff2f3b6af89a`
- Manifest: `1967542465ccfaa4c1fd7a8f1aecb1571d29b8b70cf82148fef4f47cd9f3099e`
- State: `c2099e7420bc96559a7ba30aa35b5da5fc5c473a31bd501e2b3ba8b0b5490ed5`
- Model63: `dd47c6e9b329ffbae5882c1908b869d89aa0d8515f2f5e96620100823ea90f74`
- Corpus: `e647cc1669e0c33ea1c9a7e151c5ef9692559eeefa7aa143f4e32184977a25f9`
- Played source: `63aa4647bfad022c5a746a3f7892978a495dd2e6`

AG02 and AI01/02 are ancestors, not restart points. Never rerun the AI/AJ launchers.

## What changed and what remains

Mart supply can explicitly opt into the existing indoor-exit/Fly composition. Observed badge, healthy holder, destination, stale-state and shared-budget checks remain. Capture-only Cut/Surf permissions were not generalized to every resource task.

Ordinary-ball exhaustion now stops between encounters and returns typed evidence. The strict public summary also preserves that flag and completed transport costs. AH preparation was interrupted during read-only historical validation when review caught the initial missing parser support. AH has no created episode or gameplay; its declaration remains preserved.

The travel trace places the helper's HP loss from 73 to 36 during the Shellder encounter; it does not identify the exact damaging move. The later Seel33 remained at 88/88 HP with zero status attempts, and its single ball failed. The helper was already below half health, so the status-support safety guard correctly withheld it. Improve endurance and adequate supplies without lowering those protections.

271 focused tests passed; a separate overlapping 372-test router/checkpoint/continuation group passed; the report-parser correction passed 160 tests including actual-provider serialization and composed failure accounting. Ruff, configured mypy(471 files), registry and focus checks passed. No full-suite claim.

The bounded capture/resume checklist is now 3/3: a travel capture, resumed route and fitted positive collection gain are verified. The failed destination retains success target 0 alongside completion gain 1/124. Evidence is the exact save, trace, guarded runtime and fitted row; no nested travel receipt was persisted, and none is invented. The already-satisfied-destination shortcut remains unqualified. This does not complete Phase 5, Red, or prove independent performance; North Star and stage exits are unchanged.

## Next bounded session

1. Reconstruct from the private AJ arguments, then append AJ01's checkpoint and its Seafoam B3F warp-safe/discovery profile. Carry model63 and all previous resource/field options, including AI's proposed B4F profile used by its actual restoration.
2. Inspect capture preparation and the helper's safe fallback. Choose the smallest safe conditioning/party-support repair with a measurable capture benefit; keep target identity, non-KO and party protections.
3. Qualify sufficient legitimate ball funding from the actual zero-ball/593 money save. Existing Mart transport is implemented, but this exact Seafoam supply journey has not been played.
4. Attempt one productive model-selected collection outcome. Retain failed costs and stop safely if the concrete repair is falsified; no repeated full-health two-ball batches.
5. As a small throughput repair, avoid rebuilding source history for inventory-only calls whose returned menu is discarded. Actual policy decisions must still consume authenticated history and fresh observations.

Allow 60–90minutes for this bounded objective, not Red completion. No reset, sealed Red, Crystal, full replay or release.

## Ownership and publication

Codex owns integration. No external agents ran this session; no fresh external quota was queried. Flash's older stone draft remains isolated at`895b4d6b`, not integrated or live-qualified.

PR242 passed CI34537307137 and merged as`0d58f492`. Preserve the played source on`codex/red-supply-transport-20260910`. Publish the current closeout as one tested batch; ordinary gameplay does not wait on hosted CI.
