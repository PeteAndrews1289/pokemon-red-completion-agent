# Model-first development roadmap

The product is a model that plays Pokémon and accumulates a shared, verified Pokédex across games—not a fixed Red walkthrough. See the [mission](../MISSION.md) for the permanent goal.

The [development infographic](development-roadmap.md) shows the complete sequence and fixed exit criteria. The [active state](../ACTIVE_PRODUCT_STATE.md) owns current counters; [the handoff](../HANDOFF.md) owns the latest saved endpoint. This page explains priorities rather than duplicating every session.

## Where we are

The observation/control/verification loop works. Model-selected goals have produced sustained bounded Red progress, and checkpoint-based story integration reached the Champion and Hall of Fame under disclosed deterministic battle control.

Current work is Red collection: 64 verified registrations and 63 examples under the registered-only learning objective. Supply access, travel capture/resumption and a safe ball-exhaustion stop are now live-qualified. The latest session fitted successful model-selected healing and a failed destination choice with a real Shellder registration gained along the way. Earlier datasets remain historical; their counts are not silently added. Fresh-game autonomy and independent reliability are not established.

## Next sequence

1. **Sustain useful collection.** Let the model choose missing-species acquisition, supported evolution, supplies and recovery. Keep actual costs and failed searches.
2. **Remove demonstrated mechanic gaps.** Build on the qualified incidental capture/resumption path, improve capture-support endurance, and add missing acquisition/evolution mechanisms as real collection outcomes require them.
3. **Measure learner value.** Compare with appropriate baselines on genuinely separate situations before claiming better planning, reliable new-seed play or greater authority.
4. **Broaden Red coverage and fresh-run sequencing.** Collect all declared reachable registrations and account for unsupported or externally dependent entries.
5. **Integrate Blue/shared memory.** Reuse global registration credit without fabricating local flags or transferable specimens.
6. **Test a compatible unfamiliar Red modification, then Crystal.** Report initial performance and adaptation separately. Semantic interfaces make reuse possible; they do not prove transfer.
7. **Extend to later titles.** Add adapters and mechanics only when measured reuse supports the expansion.

These priorities do not change the [baseline's stage exits](../configs/development-roadmap-baseline-v2.json).

## Immediate session boundary

PR242 merged after green CI. AI completed legitimate resupply and a model-selected restoration. AJ chose Seafoam B3F among seven destinations, caught Shellder on 1F, resumed travel and failed to catch Seel at B3F. Its typed exhaustion stop retained completed Surf, spending and a safe checkpoint. Model61 grew to model63; registrations grew from 63 to 64.

Resume only from AJ01/model63: Seafoam B3F, 54 specimens, zero balls and 593 money. Prioritize capture-support endurance and adequate legitimate supplies before another collection choice. The helper lost health during Shellder's encounter; Seel later remained at full HP with no status attempts because the helper was already below its safety threshold. Do not lower that protection. A small planned optimization can avoid rebuilding search history for inventory-only calls that discard their menu, while retaining full history for actual policy choices. Allow 60–90 minutes. The bounded capture/resume checklist is 3/3, supported by an actual resumed capture and a fitted positive gain, not a successful final Seel goal. Stone procurement and the already-satisfied-destination shortcut remain unfinished; Phase 5 and Red are not complete.

## How to stay focused

Each work session names a reusable capability, model-controlled choice, transfer test, cheapest falsifier, time box and stop condition. Evidence and tests support progress; they are not substitutes for played learning results.

Update the current summary in place. Put details in one dated report; never prepend another “Current” block. Record material roadmap changes in [roadmap decisions](roadmap-decisions.md).

[Latest collection report](work-sessions/2026-09-10-supply-transport.md) · [Historical roadmap](history/model-roadmap-through-2026-09-10.md)
