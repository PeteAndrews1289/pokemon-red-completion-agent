# Current development handoff

Updated September 10, 2026. Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and [ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Older outcomes remain in dated reports and Git.

## Goal

A learned player that completes stories and accumulates one shared registered Pokédex across games. Red first; global credit, local owned flags and physical stock remain separate. No level-100 or simultaneous-living-form requirement. Deterministic mechanics are disclosed; fresh-game autonomy and transfer are unproven.

## Latest verified save: AM01

Dig-to-Center recovery succeeded under an actual sampled native choice: 46 actions/3732 frames. An earlier exploration failure retained 244 actions/13380 frames. Both choices fitted 63 to 65 examples. 64 registrations and 54 specimens preserved; all party HP/status restored. Gameplay stopped at Fuchsia Center.

- AL01 sampled explore from two options despite a higher model value for recovery. It failed without semantic progress; its failure was fitted (63→64 examples), not discarded.
- AM01 continued the actual AL save/model64 with the next seed. It sampled restore_team and completed Seafoam B3F→Fuchsia City→Center. Successful recovery fitted the next example (64→65).
- Parasect healed from 36 to 73 HP and Blastoise from 221 to 244 HP; all six members have full HP and no status. Bag, 593 money and 54 specimens are unchanged. Zero balls remain.
- Both batches together: 290 actions/17,112 frames; 393.433 seconds including preparation. No new registration. One success out of two related development choices is not an independent success rate.
- Exact terminal: Fuchsia Center/map 154, row 3, column 3; input-ready, battle 0. No pending trainer. Gameplay stopped.

Exact identities:

- Episode: `red-registered-dig-recovery-20260910-am-01-causal`
- Checkpoint: `13c4c37c079c1d8c33200885bf1ec21db7f058af73ed5e685b1fc877ed08057d`
- Manifest: `88c08d469beb76b362941f17d7118833e16250f4cbf579241dd92f222e9a3f00`
- State: `eb40f517d52d5041b023f12fca9acb4ce1a4f5513817d1f8fb5a53910f84a030`
- Model65: `fad0b1bce9887862fb1214a6b95d1d43cc96457f8029f50715f189c72a03238b`
- Corpus: `9f9a3a86a9315d8f702468468aff32c492b9e0de7a2f0e92a6322858471b7997`
- Played source: `8125e9b48b402c41de4258478baa3291f05b0bc0`

[Session report](docs/work-sessions/2026-09-10-dig-recovery.md) · [Learning evidence](docs/evidence/red-dig-recovery-learning-2026-09-10.json) · [Saved collection](docs/evidence/red-dig-recovery-saved-2026-09-10.json).

## Prospective income work

Read-only AM inventory reconfirmed Blastoise73/full HP, 593 money, zero balls, no Pay Day holder and no TM16 in the bag. TM16 availability elsewhere is unknown. New economy observations/features retain net cash and per-item bag changes without altering model65 or historical serialization. They are not yet wired to fitting or live earning. No gameplay, fit or registration this session. [Funding session](docs/work-sessions/2026-09-10-renewable-funding.md).

## Mechanics and checks

Explicit ordered Dig recovery leaves historical profiles unchanged. Only allowed terrain, a living first Dig holder and a known healing anchor qualify. Execution rechecks stale state, bounds escape inputs, verifies the cartridge-derived landing and unchanged party/resources, then freshly binds ordinary Center recovery. No Seafoam walkthrough was added.

252 focused/regression tests passed before two extra boundary tests; the final Dig group has 25 tests. Another 149-test closeout group passed. Ruff and configured mypy (472 files) passed. This is not a full-suite claim. Actual area trace and exact save qualify the escape/heal; no nested Dig summary was persisted and none is invented.

## Next bounded session

Continue AM01/model65. Connect prospective economy facts to explicit earning choices, then qualify one bounded League-income attempt with measured costs. Exclude forced support from fits and preserve old rows. Pay Day is a fallback pending TM/holder setup. Budget 1-2 sessions for this boundary, not Red completion; no full replay, sealed Red or Crystal.

Private helper `inspect_an_funding_20260910.arguments()` reconstructs exact AM ancestry without launching gameplay. AN was read-only and created no episode. Its first inspection raised the explicit empty-menu exception; the normalized follow-up confirmed zero native goals and zero regional candidates. Never rerun AL/AM or restore AJ to regain resources.

The current resource-recovery checklist is 2/3, not a phase or Red percentage. Funding/collection is still open. The previous travel-capture checklist remains 3/3: Shellder was caught en route to B3F before the later failed Seel capture; preserve that partial-gain failure.

## Ownership and publication

Codex owns integration. A native read-only reviewer identified the learning-signal gap and verified accounting boundaries; accepted fixes include legacy API preservation and malformed-evidence checks. Claude/Flash were not used and external quotas were not queried. Flash's older stone draft remains isolated at `895b4d6b`, not integrated or live-qualified. External reviews are optional bounded help, not a standing gate.

PR243 contains the supply/escape integration; preserve played `8125e9b4`. PR242 previously merged as `0d58f492`. Batch closeout publication after local checks; ordinary development gameplay does not wait on hosted CI.
