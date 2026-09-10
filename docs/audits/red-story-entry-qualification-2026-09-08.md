# Story entry: dependency legality is not executable readiness

This is engineering qualification, not a learning result. Model76 and checkpoint21445916
are unchanged: 30 specimens, 28 living species, 33 registered, 619 currency, zero balls.
All inspections authenticated the retained train checkpoint and verified unchanged emulator
bytes, frame count and released controls. No gameplay, fitting, sealed access or replay ran.

## Findings and repairs

The old Lorelei skill advertised readiness from Indigo's location and story flags alone.
Its executor additionally required a particular entrance square, ordered party core, lead
moves and exact consumable quantities. One shared read-only predicate now governs admission
and execution, including rechecking after a stale offer. Missing events/inventory and duplicate
inventory entries fail closed. Named `legacy_` failures are implementation restrictions,
**not** a shopping or party-training recipe for a general player. The old battle policy,
timing, route strings and stock thresholds were not broadened.

Current state fails six old-contract checks: entry map, entry square, party core, lead moves,
Full Restore count and Hyper Potion count. Even arriving at Indigo would not fix the other four.
The reusable battle successor must avoid those exact-party/exact-stock assumptions.

The current party can use Surf and Strength, but not Cut or Fly. The existing planner finds
a 52-step static candidate to Cerulean (49 walks, two connections, one ledge), but no bounded
feasible ground route to Indigo. This is not proof that Indigo is unreachable in the game.
Neither the candidate route nor a safe return has been live-qualified.

To replace speculation about stored helpers, the observation adapter now inventories moves
in any PC box, reusing both saved-bank and individual-box checksum checks. The live box wins
over stale SRAM; uninitialized inactive boxes are logically empty. Index bounds, masked PP,
multiple banks/slots and changed box selection have independent tests. It sends no inputs
and does not assert that a boxed Pokémon is already a healthy usable party member.

Actual saved data identifies an owned level55 Farfetch'd with Slash/Sand Attack/Cut/Fly
and PP20/15/30/15. No HM acquisition or species-specific inference is needed to establish
that stored capability. Retrieval and Indigo's Fly unlock remain unverified.

## Review and verification

353 focused tests passed across story admission, observation, PC, goal binding/context and
boxed-evolution integration; this is not a full-suite result. Full source typing and lint
are checked separately at publication. No hosted CI gate or manual rerun was introduced.

111 product/roadmap/work-status tests and44 spectator tests also passed. The previous
hosted failure at b9affcfd was the last-fit/support-episode dashboard identity mismatch;
4a8d9f49 already repaired it, and the affected spectator suite passes locally here.
Funding source runs34249064006 and34249920442 passed hosted CI. The dashboard's saved
collection reference still pointed at the older29-specimen/9-currency endpoint; it now
points at the newly reverified30-specimen/619-currency state, explicitly not live gameplay.

Flash High gave a bounded no-tools review of supplied facts, not a code audit. Accept the
PC/Fly-first direction. Reject its description of the 52-step candidate as proven travel and
its suggested deposit choice based only on level. Preserve required field skills, viable
battle roles and all living specimens. Confirm Indigo is selectable before confirming flight.
Gemini quota after review:91.08% five-hour,94.22% weekly remaining. Claude was not invoked;
Antigravity's other-model pool is not the user's Claude subscription quota.

## Reorientation and next gate

The no-learning alarm is real: this follows an engineering-only income slice. Stop work on
legacy chapter adaptation here. Do not turn the six failed predicates into another teacher
reconstruction campaign or count inventory inspection as training. The mission and Phase4
Champion/Hall-of-Fame exit are unchanged; the current income-to-story checklist remains1/3.

Next time-boxed slice: retrieve an observed field capability via existing verified PC operations,
then qualify generic destination-observed Fly. A route candidate, withdrawal or successful flight
alone is support, not a learned story win. Separately qualify a species-independent boss battle
binding, expose it alongside real alternatives and retain the actual model-selected outcome.
If transport requires expanding a walkthrough or general battle readiness remains undefined,
stop and explicitly redesign the story composition seam. No repeated collection/heal detour.

[Path-free evidence](../evidence/red-story-entry-qualification-2026-09-08.json).
[Next bounded plan](../work-sessions/2026-09-08-field-transport-plan.md).
