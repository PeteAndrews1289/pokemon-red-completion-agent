# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 14, 2026.

## Shared-departure redesign: implemented and action-free qualified

The existing travel-aware router now feeds the full-Pokédex proposal and the existing player.
A real recheck of the same historical field state exposed both wild capture and native level
evolution, with zero controller actions/frames and unchanged save bytes. ROM-free tests also
cover routed capture from a Center while native evolution is available there.

Correction: the previous check used only the source-local enumerator. It did not establish
structural location incompatibility. No new route engine or historical-menu search was needed.
The historical catalog identity also does not establish disjoint upstream lineage.

An explicit `local_red` policy now targets all151 local flags while preserving actual shared
history and physical stock. New versioned checkpoints/rewards count local novelty over151;
old shared124 documents, hashes and rewards remain unchanged. The runtime joins actual capture
demand/allowlists, retains other available goals, and rejects stale or twice-consumed menus.
The observer permits one attempt, then keeps the fresh terminal ledger readable even when a
successful goal removes one acquisition family; terminal observations cannot authorize input.

## Learning and completion status

Model121 remains121 examples,83 successes and86 local registrations. No gameplay, model query,
example, outcome, fit, promotion or independent evaluation occurred. Gameplay is stopped and
the anti-drift alarm remains active. The18 registrations in the diagnostic are not the retained
Model121 checkpoint's86; they are separate saves.

Red must finish from a fresh start under model-directed decisions with concurrent Champion and
Hall-of-Fame evidence and all151 local registrations before any ROM hack, then Crystal/Emerald.
Version, trade, supporting-save and event dependencies remain unresolved requirements.

## Next bounded work

Use `build_red_full_pokedex_player_observer` with an explicit prospective local-Red registration
session and the existing durable bounded collector. First establish an eligible authenticated
train departure; the diagnostic grants neither training eligibility nor permission to replay a
consumed assignment. Freeze one real model choice, execute only its binding under the existing
hard action/frame budget, retain success or failure and the fresh terminal ledger, then admit
only that measured outcome. No Model121 resource-loop row, teacher fallback or diagnostic fit.

Estimate: one60–90minute session. Stop before input if eligibility, two executable acquisition
families or the durable outcome path is missing. Do not restart architecture work or a full replay.

## Verification and reviewers

363 focused ROM-free tests and164 documentation/focus/roadmap tests passed; repository Ruff and
configured mypy passed. Source plus both
changed scripts passed mypy across499 files. An expanded, non-CI sweep of every historical script
reported107 errors in24 files; it was not repaired in this scope. Full pytest was not repeated.
Collection metadata and documentation checks are part of publication, not learning.

Claude Opus4.8 High completed the initial read-only audit. Accepted binding/config and capture
allowlist defects; rejected its shared-as-local recommendation. A follow-up delta audit hit the
session limit before a final verdict; the CLI reported reset at13:00 America/New_York today.
No final-review approval is claimed. Flash3.8 High supplied the accepted regression categories.
Remaining percentages and weekly Claude quota are unavailable; Flash headless quota is unavailable.

Next-session recommendation: **GPT-5.6 Sol / High / Fast off**. The redesign is settled; the next
job is bounded execution, failure retention and outcome admission rather than another broad audit.

[Session](docs/work-sessions/2026-09-14-full-pokedex-shared-departure.md) ·
[Evidence](docs/evidence/red-full-pokedex-shared-departure-2026-09-14.json)
