# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 16, 2026.

## Capture initialization repaired; Haunter caught; Red 93/124

The capture helper latched enemy HP before the battle introduction finished. Generic tests
reproduced the false guard stop with stale, zero and missing HP. It now settles at the shared
MAIN boundary before latching stats, verifies the declared original target, protects party/bag
through initialization and retains all damage/identity guards during setup. The historical
Model130 entry value was not recorded; its full-health terminal and unchanged party HP/PP are
consistent with this timing defect but do not prove the exact old callback value.

One separately qualified continuation from the retained battle caught **Haunter**, using
158 actions / 13716 frames, one Great Ball and one verified paralysis move. Target HP stayed
63/63. Red is **93/124**, with **74 specimens**, 1608 cash and six Great Balls. The field terminal
is safe, SHA-256 `8569b536859dc6ab0882b2c1bed28c0e029ced050b07b35b00741d17498a59aa`.
**Model131 remains 131 examples / 89 successes / 52 economy-qualified examples.** Support recovery
adds no learner example; the original Model130 failure remains fitted. No route replay occurred.

## Exact next bounded work

An action-free menu inspection stopped before any model query: only one resupply binding,
zero regional acquisitions, and restoration unavailable (`no_legal_target`). The capture helper
is now 34/70 HP. `autonomous_collection_options` constructs its main `RedResourceGoalRouter`
with routed recovery disabled; the existing generic Center recovery offer is therefore absent.
Qualify that capability in the mixed menu with bounded action-free planning and genuine resource
costs. Permit one fresh Model131 decision only if verified executable alternatives exist, retaining
and fitting its actual result. The prepared next plan was inspected only; no run output exists.
Do not force a species, replay Model130 or turn support recovery into training success.

[Session evidence](docs/evidence/red-capture-initialization-recovery-2026-09-16.json) retains hashes
and boundaries. 217 focused ROM-free tests, lint and type checks passed. Flash 3.8 High completed
a read-only design review; settled stats and declared identity were accepted, while automatic
flee, full-HP-only capture and its incorrect battle-state value were rejected. Quota unavailable;
Claude not used. No GitHub push. Next: **Sol / High / Fast off**, about 45-75 minutes.
