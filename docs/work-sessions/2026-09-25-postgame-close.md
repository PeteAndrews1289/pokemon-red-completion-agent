# Native postgame close and one-off capture readiness

## Verified outcome

Actual471 continues actual470 through native credits, title Continue, Pallet,
Fly to Viridian and free Center healing. Independent zero-input audit passed.
210actions/15684frames;0battles/model choices/items spent/cash spent/fits/captures.
All five members now have full HP/status/PP; cash30620,17local registrations.
Party: Blastoise65,Jolteon55,Farfetch'd54,Snorlax52,Dugtrio55.
Terminal458df291, envelope2075e2c5; all prior471stages and both models unchanged.
Campaign286162actions/22587800frames;13838actionsremain;stage472absent.
Native game initialization is part of the credits flow, not an operator reset.
League flags reset during the native save; concurrent Champion/HoF evidence
belongs to470. Historical36/36 completion is retained, not reasserted live at471.
All gameplay stopped. [Evidence](../evidence/red-postgame-close-2026-09-25.json).

## One-off encounters: inspected, not attempted

| Target | Level | Location | Consumed event | Capture ready |
|---|---:|---|---|---|
| Zapdos | 50 | Power Plant | Clear | Not qualified |
| Articuno | 50 | Seafoam B4F | Clear | Not qualified |
| Moltres | 50 | Victory Road 2F | Clear | Not qualified |
| Mewtwo | 70 | Cerulean Cave B1F | Clear | Not qualified |

All four are unregistered here; descriptors mark them non-repeatable. Event
flags were unchanged. Clear flags do not independently prove access, visible
objects, route completion or adequate resources. No legendary was interacted with.
Bindings use pinned pret/pokered a1a22aaf constants/scripts and decoded ROM objects.
Articuno is object3 but eventbit2: do not derive its event from sprite index.
[Primary script](https://github.com/pret/pokered/blob/a1a22aaf84d1675bcdbaeb194592379d586d838e/scripts/SeafoamIslandsB4F.asm).

Inventory has1MasterBall,20GreatBalls,1PokeBall,0UltraBalls;1FullHeal and5ParlyzHeals.
HP medicine/Revives exhausted. One party slot and11current-box slots are free.
Neither five party members nor nine boxed members currently has a pure enemy
sleep/paralysis move. Rest is self-sleep; Body Slam's damage/secondary effect is
not a pure capture-status action. This is the actual story inventory, not the
separate collection save's78specimens.

## Next bounded implementation

1. Bind semantic one-off availability to species/object/script event, actual
   route visibility, registration, storage and the exact source state. Refuse
   the interaction before battle if supplies or execution are unsupported.
2. Reuse existing pure-status, capture-party and critical-inclusive safe
   weakening components. The trainer knockout actor is not a capture policy.
   Obtain/prepare a legitimate status helper and enough balls/healing; preserve
   the sole Master Ball provisionally for Mewtwo, pending explicit goal selection.
3. Qualify on declared isolated DEVELOPMENT copies: critical KO prevention,
   status immunity, damage-over-time/recoil, failed throws, PP/Struggle pressure,
   switches/faints, bag exhaustion, storage and interruption behavior. Ordinary
   capture's20throw/retreat/ABANDON defaults are not sufficient one-off support.
   Preserve all outcomes; copies are not independent roots or TRAIN examples.
4. Only after qualification, admit one actual target and verify both registration
   and owned specimen. Never silently rewind the campaign or copy back a win.
   A failed ball is not encounter loss; KO/escape/blackout require explicit
   irreversible-outcome handling. Do not promise zero risk from stochastic combat.

Estimate1–2bounded sessions for admission and initial copy qualification, contingent
on route/status-support findings, not a promise to finish all four in that time.
Maintain the shared109/124 ledger separately from story17; no save merge.
The remaining shared15 include other acquisition/evolution dependencies, not
only these four. All124 must ultimately be registered in the final fresh Red save.

## Boundaries and verification

This session is maintenance unblocking model-selected collection, not learning.
No learned authority, new weights, TRAIN135counter, freshRed0/5gate or shared
collection count changed. Broad candidate29/72versus30/72still fails promotion.
135targeted postgame/goal/field/recovery tests and107capture-component tests pass;
these are not a full suite or native legendary qualification. No production
code changed. Audit-only path spelling comparison was normalized to unique
resolved paths with identical digests; no guard, executable or gameplay replay.
No publication or external agent use. Next recommendation: AstraHigh,Fastoff.
