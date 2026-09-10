# Current development handoff

Updated September 10, 2026. Earlier results remain in dated reports and [history](docs/history/handoff-through-2026-09-10.md).

## Goal and scope

Build a learned player that completes stories and accumulates one shared registered Pokédex across games. Red first; global credit, local owned flags and physical stock remain separate. No level-100 or simultaneous-living-form requirement. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), then [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md).

## Latest verified save: AG02

- **63 global/local registrations, 53 specimens, 49 living species**, independently checked from the exact save.
- AG01 evolved Doduo into Dodrio: 17,950 actions / 1,616,756 frames, one recorded Fly. This forced setup produced no fit.
- AG02 exposed seven executable destinations. The existing model-plus-exploration policy selected Power Plant and reached it. Both remaining balls were spent without a capture; a later no-balls encounter raised a generic error.
- The actual failed destination outcome was fitted: **model60 → model61**. This is development experience, not improved independent performance.
- AG02 used 1,273 actions / 70,285 frames. Total batch: 19,223 actions / 1,687,041 frames, 1,390.502 seconds including preparation.
- Exact terminal: Power Plant/map83, row19 col17, input-ready, battle0, no pending trainer; **zero balls and 1,638 money**.
- Gameplay is stopped after the failed second goal. The third goal was never attempted.
- [Session report](docs/work-sessions/2026-09-10-surf-collection-access.md) · [Outcome evidence](docs/evidence/red-surf-access-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-surf-access-saved-2026-09-10.json).

Exact identities:

- Episode: `red-registered-surf-choices-20260910-ag-02-causal`
- Checkpoint: `445f68aac643a6482f41972ead962d5ba75ef69b0d84b946326c02c41d48d871`
- Manifest: `74db044a6836694a1e777d3a9338c561034049e8a34c8c81118b9ab094b8e951`
- State: `d3be0828db030c995aa00013fb31a68029920093f667f0369189fdfa91351840`
- Model61: `a699c3f740fad9182273140d98cfe0f77827765eb5b73b484dc6730cf13c3476`
- Corpus: `4b27c0e83c0edfb40c14c2facdfb513d7abe5433344e241b0c8f4b237c8fe0d0`
- Played source: `282bb30b0ce7c5cbe7c5a4ed35ad1d16cc3048ad`

Preserve all earlier support episodes and costs. AF and AG01 are historical ancestors, not restart points. Never rerun the AG launcher.

## Repair and limitations

The first Surf-only projection exposed zero candidates. Diagnosis found eleven unnamed land-encounter maps and two unnamed water maps. Thirteen independent map-ID tests failed before repair. All actual nonempty encounter maps now have adapter names; names do not grant access.

Capture-only Surf is explicitly enabled, requires observed badge/healthy holder/title permission, shares the original primitive budget, and preserves Cut/Strength boundaries. After map repair, seven routes remained preparation-blocked by the injured helper. Legitimate evolution/recovery restored that helper; seven actual destination choices then became executable.

347 targeted tests passed, plus a separate 127 checkpoint/fit/cycle tests. Ruff and configured mypy passed (471 source files). These are not a full-suite claim. Field counts survive successful composition (AG01 Fly), but AG02's downstream exception prevented its completed route summary from propagating. Do not invent retained Surf counts.

The last streamed AG02 snapshot was not ready; the exact final checkpoint is ready. Always use the authenticated terminal for continuation decisions. AB's earlier incidental-arrival repair remains unqualified; capture/resume stays 1/3.

## Next bounded session

1. Continue from AG02/model61 with all ancestry and capture-Cut/Surf options. Reconstruct AG's transitions in order: its owned Doduo→Dodrio transition plus evolution-Fly/indoor options, AG01 checkpoint, then AG02 checkpoint and selected Power Plant warp-safe/discovery source. The private read-only next-menu script reconstructs these exact arguments.
2. The exact native preflight offers no goal: resupply resources are available, but transport reports missing capability. Extend the existing supply transport to truthful indoor departure/required field movement; do not weaken capture-only permissions globally.
3. Qualify one legitimate purchase from the actual terminal, then one productive collection choice. Preserve the failed AG label and costs; no old-save replay.
4. Return ball exhaustion as a typed bounded outcome and preserve completed transport evidence when the destination stops. An exception must not masquerade as successful capture.
5. Time box 60–90 minutes. Duplicate unchanged-state route inspections are a measured secondary cost; optimize only where it directly unblocks this loop.

No reset, sealed Red, Crystal, full replay, release or independent-performance claim. Stage exits are unchanged.

## External work and publication

No external agents ran this session; no fresh external quota was queried. Flash's prior stone draft remains isolated at `895b4d6b`, not integrated or live-qualified.

PR241 merged as `83038a7b`. Played source is published on `codex/red-surf-choices-20260910` and must remain recoverable. Publish this evidence closeout as one tested batch; ordinary gameplay does not wait on hosted CI.
