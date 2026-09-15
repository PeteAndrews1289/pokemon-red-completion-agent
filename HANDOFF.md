# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 15, 2026.

## Battle contract qualified without gameplay

The user requested a refocus after repeated runtime repairs. The audit reproduced seven false
successes: additional PP spending could be hidden by effects or exit, and a forced switch could
be mistaken for move learning. Shared verification now checks the original battler's entire PP
vector before accepting an effect. The final bounded no-effect transition is also checked.

The runtime now attaches bounded phase, selected-move, observation, action and exception-location
diagnostics. An optional failure sink persists them before outer exception handlers discard detail.
604 affected tests pass, one skipped; 108 cases vary slots, timing, stale menus and outcomes.
These are synthetic results, not cartridge or learned reliability.

Recovery was already successful: the exact save is stable with 86/151 registrations,
66 living species and 70 specimens. Model121 stays at 121 examples/83 successes.
The recovered menu contains restoration and resupply. Evolution and recovery identities remain
consumed. Expanded collection checklist 25/26; final fresh-Red gate 0/5.

## Next bounded work

Run the disposable cartridge qualification in the [session report](docs/work-sessions/2026-09-15-battle-runtime-refocus.md).
Bind and verify durable failure recording before input. Use fixed case/action/frame bounds, retain
all outcomes and stop on an unexplained transition. No protected-root search, source four,
consumed-identity replay, fit, full run, ROM hack or Crystal.

The old exception's exact cause remains unknown. Same-battler move replacement retains a legacy
inference, and an observed effect does not prove the next decision boundary is settled.
Cartridge qualification must test those distinctions before official collection resumes.
Off-slot move learning currently fails the strict PP-vector check; include it as an explicit
qualification gap before extended training.

Next: **Sol / High / Fast off**, approximately 1–2 hours for the bounded qualification.
The design and falsifiers are specified; use Astra again only if evidence requires a new contract.

[Qualification evidence](docs/evidence/red-battle-runtime-refocus-2026-09-15.json)
