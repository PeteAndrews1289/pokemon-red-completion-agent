# Current development handoff

Updated September11,2026. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Shared registrations, local flags and physical stock stay separate.

## Latest verified endpoint: BQ03/model90

BQ completed three consecutive model-facing decisions. The model chose to earn700, then spend600 on one ball, then choose among six regional acquisition sources. Its declared exploration policy sampled SeafoamB1F, where deterministic mechanics used Surf and verified paralysis support to register Horsea. All three outcomes succeeded and were fitted:87→90examples and68→69registrations.

- Episode: `red-collection-20260911-bq-03-causal`
- Checkpoint: `8bd9694358be28c07db2a33788010fc94f8e3330cb4391afa3fe526081b61f80`
- Manifest: `b5a08451c50245d30bb63b06c02e595551171c1327829b8f18b6fcd80a5cf453`
- State: `8f8019e053e929d090087efe60a10f6e605105795abe0b06d87df81976616fa8`
- Played source: `a137457345e74edf3ace74a6f9af5426c04b5780`
- Model: `b5df2b4e73be7255de8d6c4c18c05198fd79144df80cacc514e01b5a1fee2f37`
- Model file: `7eeec8c2874fe1c2cdae9019aa108c8f11a84863b2e910cf4ba45ec6d60ee461`
- Corpus: `2c7aea2d21a4e1288bc54c55c316c068d6150577eb858a69916c45c641aa2668`

SeafoamB1F map159,row9,column9,input-ready,battle0;543money,three balls. HP249/118/150/90/120/73.69local/global registrations,58specimens,54living species,55required registrations remain. BQ used1,018actions/60,805frames across three successful steps in1,143.875seconds. No retry, teacher fallback, sealed evaluation, Crystal access or full-game replay occurred.

BQ01 selected earning and increased cash443→1,143. BQ02 selected a one-ball purchase, changing cash1,143→543 and capture stock3→4. BQ03 ranked six regional sources; SeafoamB4F scored highest, while the declared25% exploration policy sampled SeafoamB1F. The regional choice was committed before input. Travel and capture mechanics registered national#116 Horsea and consumed one ball. All three actual outcomes were fitted.

## Continuation state

Continue only from audited BQ03/model90. Reconstruction must preserve the complete selected-source ancestry: the prior BP continuation plus BQ01 `warp-safe`/`discovery` PowerPlant, BQ02 PowerPlant again, and BQ03 `warp-safe`/`discovery` SeafoamB1F, in executed order. Do not replay BQ or silently deduplicate those transitions.

The next engineering task is input-free: reduce the fresh regional inventory cost while preserving live feasibility. A measured BQ readiness pass authenticated226 continuation episodes in39.135seconds but spent252.24seconds enumerating the regional inventory. Commits `caf87d4f` and `a1374573` already remove duplicate readiness and inventory within one step. Cache or precompute only cartridge-static work; party, inventory, blockers and route feasibility must remain live.

After proving an identical candidate menu/order/hash, continue from SeafoamB1F with543money, three balls and full party HP through another bounded model-selected acquisition or evolution. No Crystal execution, sealed Red evaluation, BQ retry or fresh-game autonomy claim.

## Engineering and review

Published commits `caf87d4f` and `a1374573` make the aggregate cycle pass one authenticated readiness object and one immutable regional inventory into its child runner. Focused tests verify one ancestry authentication and one inventory enumeration per prepared episode. A broad local run reached7,371passed/4skipped/1expected failure before it was intentionally stopped; three stale registry failures were regenerated and the39 registry tests then passed. The final focused set passed67 tests. CI remains informative, not a training dependency.

The current learner ranks high-level goals and regional sources. Deterministic code still executes routes, menus, battles, captures and recovery. It has not demonstrated fresh-game autonomy, arbitrary-seed reliability, independent learned advantage, complete Red collection, ROM-hack competence or transfer.

[Latest report](docs/work-sessions/2026-09-11-horsea-capture-and-loop-speedup.md). Recommend **Sol High** for continuation and performance work; use Astra High only for a milestone architecture audit.
