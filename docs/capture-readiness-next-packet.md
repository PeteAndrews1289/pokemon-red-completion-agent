# Next packet: preparation before an irreversible capture

Prepared September25,2026 after the [completed bird checkpoint](work-sessions/2026-09-25-articuno-master.md).
Status: bounded steps1–5 completed; [verified result](work-sessions/2026-09-25-capture-readiness.md).
One model-selected native purchase,0fits/registrations. The prospective plan below is retained.
This elaborates packetB of the [roadmap](model-first-roadmap.md), subordinate to
[active state](../ACTIVE_PRODUCT_STATE.md). It does not reopen completed captures.

## Outcome we need

The model can see and select a feasible preparation option instead of entering a
one-off encounter underprepared. After preparation, it sees the changed resources
and chooses again. Merely filtering capture out, or automatically buying supplies
inside the capture executor, is not proof of model-owned preparation.
Ordinary-ball capture can still fail; success is not a promised catch rate.

## Six-part mission check

1. **Capability:** resource-aware preparation for a costly or irreversible goal.
2. **Learned authority:** expose prepare/resupply/heal/storage versus attempt/defer
   through existing semantic goal interfaces; retain the actual model selection.
   First test the frozen model, without assuming it already ranks these well.
3. **Transfer test:** change ball stock, helper PP/health and storage independently;
   include an ordinary target as well as one-off semantics. Same-source variants
   are engineering diagnostics, not independent evaluation lineages.
4. **Cheapest falsifier:** a ROM-free low-stock case fails if it starts the encounter,
   counts the Master Ball as ordinary reserve, or hides every executable alternative.
5. **Time box:** first implementation/test packet90–120minutes. At its end retain
   the result and identify the next decision; no open-ended capture replay.
6. **Stop condition:** stop this packet on a verified choice/re-observation result,
   a measured policy failure, or a representation/executor gap needing redesign.
   Never substitute a teacher choice, rewrite a failed trial or fit DEVELOPMENT.

## Implementation order

### 1. Inventory the existing seam and lock regression cases

Start with `red_static_capture_goal.py`, `red_routed_static_capture.py`,
`red_capture_party.py`, `red_capture_status_runtime.py`, `red_capture_weakening.py`,
`red_resource_goal_router.py` and `red_capture_funding_budget.py` under
`src/pokemon_red_completion/`. Existing helper readiness, lead swaps, status,
nonlethal weakening, Mart resupply and storage should be reused, not rebuilt.

Observed gaps: static capture currently receives caller-selected ball/throw/status
budgets; default risk/effort values are supplied constants. The funding-budget
helper explicitly says its live connection is not established. Trace actual
callers before treating either seam as connected or introducing a new wrapper.
Record which existing goal kinds/features can represent the alternatives. If they
cannot distinguish the choice, report that gap rather than inventing policy inputs.

### 2. Produce one action-free semantic readiness assessment

Expose actual ordinary-ball stock by type, separately held Master Ball, affordable
purchase quantities and reserve costs; usable status moves with PP and helper health;
available safe weakening support; party condition; capture storage space; and native
target availability. Preserve unknown values rather than inventing certainty.
Keep cartridge-specific reads inside adapters and coordinates out of policy features.

Separate hard impossibility (no balls/storage, consumed target, stale state) from
risk (limited supply, fragile helper, no safe weakening). HP percentage alone must
not be described as a proven number of survivable turns. Sleep and low-HP support
are optional capabilities, not an excuse for a new grinding or moveset campaign.
No fixed stock threshold or probability estimate may claim guaranteed capture.

### 3. Bind genuine alternatives to existing executors

Offer only reachable, affordable preparation that can actually execute. Use current
cash first; do not silently sell items or launch League farming. If unavailable,
retain the exact dependency and a valid defer/other-goal path where supported.
Keep ball allocation and Master Ball use explicit; never silently substitute one
ball for another. Until measured otherwise, disclose tactical ball/turn support as
supported control, not learned control. A single final run has one Master Ball.

The selected binding must control execution. Re-observe after travel, purchases,
healing or storage and invalidate stale capture offers before encounter activation.
Preserve finite throw/status/weakening allocations and all costs on failure.

### 4. Verify discrimination before any native attempt

Required ROM-free cases: zero/low/adequate ordinary stock; Master-only inventory;
unaffordable or unreachable Mart; full bag; full capture storage; zero-PP or fainted
helper; no safe weakening move; target unavailable; observation changed after offer;
resources depleted during travel; exhausted allocation; preparation leaves target
untouched. Include contrasting cases where more preparation is unnecessary.

Run existing capture-readiness, preparation, static/routed capture, funding and
resource-router tests plus new cases. Evaluate frozen model rankings only through
the admitted interface; fixtures are synthetic diagnostics, not new learned outcomes.
Do not tune constants until the model picks a preferred answer and call that learning.

### 5. Qualify the selected preparation on a bounded development copy

After the first packet passes, record an exact authenticated source, model identity,
eligible alternatives and action/frame/wall limits before execution. Prefer a nearby
shop/heal/storage scenario; do not replay Seafoam or Victory Road to test preparation.
Initial diagnostic: at most3goal choices and one preparation execution followed by
re-observation. No legendary engagement or Master Ball consumption is needed here.
Retain unsuccessful choices as results. Do not claim useful autonomy if only one
action was possible. Native ordinary-ball/status/weakening qualification follows
separately if a specific supported mechanic remains unproved.

## Narrow correctness dependency

Before new trainer labels are admitted, reproduce the postbattle enemy-roster alias
with ROM-free fixtures. Trace the episode reporter and
`red_trainer_battle_lifecycle.py`: distinguish in-battle observations from authenticated
settled event/payout evidence. Test won, lost, interrupted and ambiguous outcomes,
including capped money/Pay Day where supported. A payout alone is not sufficient.
Preserve historical unresolved reports; do not rewrite them as clean wins.
This correction must not become another broad battler refit or trainer replay.

## Evidence and completion gate

Retain source/model/code identities, available alternatives and exclusion reasons,
scores/selection, decision latency, readiness before/after, actions/frames, cash and
ball deltas, HP/status/PP, storage/specimen delta, interventions and typed failures.
Separate engineering tests, frozen choices, training and native registrations.
PacketB closes only when preparation is executable, actually model-selected in a
useful contrast, and stale/irreversible actions remain guarded. A policy failure is
a valid result but not closure; it defines a later declared TRAIN task, not a refit here.

Then proceed to packetC: exact missing-method inventory, stones/trade prerequisites,
prize funding and Safari gaps. Reuse qualified methods rather than stitching copy
captures into one ledger. PacketsD–F retain strategic ownership, sustained play and
the fresh124-registration Red final exam. No full-run launch is authorized here.

Completion: source-bound readiness and costed purchase, changed-state tests, one
native model-owned spending decision and future trainer terminal correction verified.
The native contrast was fossil acquisition versus resupply, not legendary engagement.
Remaining strategic allocation and sustained autonomy stay in roadmapD–F.
All gameplay stopped; protected campaign/models unchanged. No publication.
