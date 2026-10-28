# Whole-player lesson contract: first implementation slice

Pete approved extending the [pre-campaign goal](../pre-campaign-completion-plan.md).
The app goal is active again. Previous status-only goal turn was no progress;
this slice changes executable admission and verifies backward compatibility.
No gameplay,production fit,model decision,registration or save change occurred.

## Ownership and training boundary audit

| Decision | Existing implementation | Remaining learning/integration boundary |
| --- | --- | --- |
| Story | MIDGAME_STORY providers and dependency-legal objective bindings; goal policy maps to UNLOCK_ACCESS. | Frozen ordinary corpus has no selected story rows. New V3 teacher admission requires the exact new declared objective; broader learned choice still needs data. |
| Development | Wild/team providers and target-member level verifier; policy maps to DEVELOP. | V3 lesson verifies the retained specimen, actual XP and declared level. Target-aware readiness representation and comparison remain. |
| Healing | V3+ goal features support RESTORE; deterministic emergency safety remains disclosed. | New lesson checks HP/PP/status improvement without another member regressing. Safety pressure must match the recorded party. |
| Earning/spending | Resource quotes, observed economy context and a separate economy head already exist. | New general teacher-economy admission, complete resource demand and currency/scarcity features remain; this slice does not claim them. |
| Acquisition/dependencies | Registered acquisition, evolution, gifts, typed NPC exchange and optional composite trade execution exist. | Native composite-wrapper trial and Game Corner execution remain. Preserve capture/trade/evolution-specific verification. |
| Scarcity | Finite procurement and one-off preparation exist as bounded mechanics. | Current generic candidate projection uses resource_cost=0; quoted cash penalties do not represent lost future uses of a unique item. Versioned features remain necessary. |

The high-level selector already supports story/development kinds. Rebuilding those
executors is not the next step. Existing unit-weight teacher demonstrations remain
explicitly non-comparative; a successful forced lesson is not a learned choice.

## Implemented

`red_player_lesson.py` reads richer XP/party evidence through the existing native
party adapter, checks it matches the goal observation without advancing a frame,
and retains session-local specimen fingerprints outside policy features. Duplicate
fingerprints fail closed. The selected story target must be previously incomplete.
Development must improve the declared retained member's XP and reach its level.
Healing must improve HP,PP or status without regressions; passive level-up HP is
not a healing lesson. Successful lessons require an input-ready nonbattle endpoint.
Readable failed/partial attempts and faints remain failures with measured costs.
The initial contract uses closed-membership lessons: catches,trades,evolutions or
substitutions need their own typed extension rather than fabricated continuity.

`red_native_curriculum.py` adds declaration/outcome V3 for these three families.
It retains the same real inference projection,unit regression weight,TRAIN-only
source requirement,predeclared limits,native audit and no execution interventions.
V1 acquisition and V2 exchange bytes are unchanged. Existing fit/retention machinery
accepts and reauthenticates the new family lessons in ROM-free integration tests.
The V4 feature projection is deliberately unchanged in this slice; richer features
and economic targets are still open,not silently treated as implemented.

Compatibility testing exposed an earlier regression:adding `roaming=False` to the
runtime trade descriptor changed `asdict` output for the frozen stationary-trade
contract. New explicit stationary serialization excludes that runtime-only field,
rejects roaming offers and checks the original two authenticated offer digests.
No frozen digest,lesson or acceptance test was relaxed to accept changed history.

## Verification and limits

- 201 focused tests passed across the new lesson contract,native/exchange curriculum,
  fitter,incremental retention,registered outcomes,goal policy/context and trade options.
- All three new lesson families pass fitting and subsequent retention/re-authentication
  in temporary ROM-free stores. These test fits are not production learner updates.
- The actual frozen corpus was hash-authenticated;all4native lesson rows reconstructed
  to their original exact hashes. No source states or evaluation payloads were opened.
- Scoped lint and typing pass. Default import-following typing reports12errors in6
  other existing modules;no whole-repository typing or full-suite pass is claimed.
- Metadata-only inspection found81entries in the known legacy catalog. That catalog
  alone does not prove partition,unconsumed status or independent eligibility. Census
  remains incomplete;no roots were claimed or replayed.

[Path-free evidence](../evidence/red-player-lesson-contract-2026-09-25.json).

## Next

Complete source eligibility and the live recorder/binding boundary,then richer
readiness/resource features and general economy lessons alongside missing mechanics.
Freeze budgets and evaluation supply before collection. Preserve all existing fits,
primary saves,failed attempts and retired protocols. The overall goal remains open;
no full campaign or GitHub publication. Next review:Astra High,Fast off.
