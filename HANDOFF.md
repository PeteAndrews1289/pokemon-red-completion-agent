# Current development handoff

Updated September11,2026. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Shared registrations, local flags and physical stock stay separate.

## Latest verified endpoint: BS03/model94

BR01 continued from the audited Horsea endpoint. The model selected evolution and deterministic mechanics trained Horsea into Seadra, advancing69→70registrations and90→91examples. BS then completed three more model-facing decisions: earn550, buy one capture item for600, and restore the injured party. All three outcomes succeeded and were fitted, advancing91→94examples.

- Episode: `red-collection-20260911-bs-03-causal`
- Checkpoint: `d1f93b41db0faaa1cdd01af342aa6b92dfdcc1bee01302d62e08a4cf1d8c3c87`
- Manifest: `938e4a2fe34b387c4cfb404c310e5c1e530092b36451eeac79e0280de32362f7`
- State: `e2f0221f8467caa5465ae73d5400bb59b5de439965a6055dc2c786140fbaaa05`
- Played source: `782f811cdcef79406a3f1382b2dabe25cba84338`
- Model: `d065d38230b92adcdf0a5e8d674d1de96b5a170737ed86e2310aeb0fd8d9d5fc`
- Model file: `dd836a978e8af20faaedaff9b2def1fabfbacd4c98ff1eda910d30d45be1f4a5`
- Corpus: `285d85c49f597d7d1cbaf1be90d5129e5afe85dfce2d9e96e013d12c97f71bc5`

SeafoamB4F map154,row3,column3,input-ready,battle0;493money,four capture items. HP88/118/150/90/120/249.70local/global registrations,58specimens,54living species,54required registrations remain. BR+BS used4,827actions/397,860frames across four successful steps. No retry, teacher fallback, sealed evaluation, Crystal access or full-game replay occurred.

BR01 selected evolution and registered national#117 Seadra from the retained Horsea. BS01 earned550, BS02 bought one capture item for600, and BS03 restored the party. The regional proposals in BS were not fitted because all six destinations had identical title-neutral feature rows; the learned parent policy still owned each actual high-level goal.

## Continuation state

Continue only from audited BS03/model94. Reconstruction must preserve BQ, BR01 and all three BS transitions in executed order. Do not replay or silently deduplicate any retained transition.

Route-plan sharing preserved the exact six-source order and menu hash, but improved the exact inventory only257.442→246.736seconds. Keep the safe refactor; do not spend another session chasing this 4.2% gain.

Continue from SeafoamB4F with493money, four capture items and the restored party. Seek another bounded model-selected acquisition or useful evolution; the next acceptance result is a new verified registration, not another infrastructure-only optimization. No Crystal execution, sealed Red evaluation or fresh-game autonomy claim.

## Engineering and review

Commits `41edcbb5`, `bf291a38` and `782f811c` narrow acquisition routing, share route plans inside one inventory and prevent indistinguishable regional identities from becoming fake training labels. The final focused and registry runs passed345 tests before gameplay. CI remains informative, not a training dependency.

The current learner ranks high-level goals and regional sources. Deterministic code still executes routes, menus, battles, captures and recovery. It has not demonstrated fresh-game autonomy, arbitrary-seed reliability, independent learned advantage, complete Red collection, ROM-hack competence or transfer.

[Latest report](docs/work-sessions/2026-09-11-seadra-and-prerequisite-learning.md). Recommend **Sol High** for routine continuation; use Astra High only for a milestone architecture audit.
