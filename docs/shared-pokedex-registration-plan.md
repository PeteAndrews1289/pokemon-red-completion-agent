# Shared registered Pokédex — memory implemented, live integration pending

Pete's September9 decision supersedes the living-specimen and level100 completion
requirements. The ledger API and registered planning projections are implemented and tested.
Capture/evolution runtime bindings are also tested; gameplay remains paused until
observer, checkpoint and reward integration is complete.

## Completion contract

- Complete each run's story with a capable team; no universal level target.
- Earn verified caught/owned registration for missing species across the project.
- Post-story: catch a useful line, evolve through missing reachable forms, deposit
  when no longer useful, and move on. No spare base form merely for coexistence.
- Duplicate catches are allowed without a special penalty or repeated novelty
  credit. Time, balls and other actual costs remain recorded.
- Global credit persists after evolution, deposit or legitimate transfer. No
  automatic releases, save edits or invented trades are authorized by this change.
- Forms, gender variants and shinies require separate scope; species are the goal.

## Shared file: three separate views

Implemented: a private SQLite ledger API with readable JSON export. Transactional
recording and uniqueness checks handle overlapping concurrent imports. Production
placement remains T7; no live database has been created and no gameplay evidence
has been imported. The caller must authenticate checkpoint observations before
recording them; valid digest syntax alone does not prove gameplay.

1. **Global registration:** canonical species ID mapped by each title adapter,
   first verified credit and supporting evidence.
2. **Per-run registration:** title/version, cartridge fingerprint, run identity,
   checkpoint and actual in-game owned flags. Seeing a species is not credit.
3. **Physical stock:** current party/box specimens. Needed for battles, evolution,
   HM access and trades, but not the completion target.

Retain append-only observations with unique IDs, source/checkpoint digests and
verified registration. Record acquisition method only when proven; an owned flag
alone does not prove a capture. Reimporting an observation is idempotent. Merging
Red and Blue credits a species once without claiming Blue caught it or currently
owns it. Reference lookups and predictions cannot write verified credit.
Interrupted writes or corrupt evidence must not become successful entries.

The model receives useful semantic summaries and choices, not private file paths.
The observer verifies ledger updates; the policy chooses the next activity. This
external memory does not imply learned knowledge of every species location.

## Planning from the ledger

Intersect global gaps with current-cartridge availability and real prerequisites.
Distinguish reachable now, unlockable later, version/trade/event requirements,
unsupported mechanics and foreclosed choices. Plan irreversible choices before
consuming them; do not remove missed targets silently. Record cross-run assignments.

If Red registered a line, Blue skips repeating it solely for global credit. It may
still need the species for story utility, trades or a missing dependent species.
A new branch in a later game can make an already-credited base useful again.
Per-title full registration is optional, not the default requirement.

Training uses actual choices/outcomes. Evaluations freeze and declare their
initial ledger so prior runs do not leak credit into independent tests. Report
inherited credit, new global registrations and local registration separately.

## Minimal implementation sequence

1. Build ledger/import/export. Test seen-only rejection, evolution credit retention,
   duplicate imports, Red/Blue merges, concurrent/crashed writes, corrupt evidence
   rejection and canonical-ID mapping using ROM-free fixtures.
2. Version the registered-only completion contract and demand projection. Remove
   level100 and spare-base-for-coexistence requirements prospectively. Preserve
   physical prerequisites, story capability and specimen safety separately.
3. Connect capture/evolution candidates, rewards and reporting consistently. Old114
   examples keep their old reward semantics; audit compatibility before reuse,
   retraining or a new head. Do not relabel old rewards silently.
4. Action-free import of the authenticated Red endpoint, then a short new-objective
   run. Test preserved base registration after evolution, duplicate neutrality and
   skipping a globally credited chain when it has no current utility.
5. Broaden Red mechanics and remove operator sequencing. Test genuinely different
   game conditions before claiming fresh-game completion across seeds.
6. Add Blue with the same ledger; measure inherited versus new credit. Compatible
   hack and later generations follow.

No new campaign, consumed-trial replay, sealed/Crystal access or historical target
rewrite during migration. Ledger imports and documentation are not learned progress.

## Mission check

- Capability: cross-run registration memory and useful next-goal selection.
- Learned authority: unchanged today; maintenance unblocks red-shared-registration-learning-v1.
- Transfer test: overlapping Red/Blue credit and later-branch dependency fixtures.
- Cheapest falsifier: duplicate merge and evolution-credit tests, then one short
  changed-objective continuation after runtime consumers agree.
- Time box: one migration implementation session followed by review.
- Stop condition: invented local credit, lost historical registration, destructive
  inventory action, altered old rewards or an unversioned runtime objective.

## Foundation qualification

237 targeted tests passed. Registered demand and evolution inventory are opt-in;
the old live contracts remain unchanged. See the [implementation and next steps](work-sessions/2026-09-09-shared-registration-foundation.md).

## Runtime-binding qualification

340 targeted tests passed for shared-credit capture surveys, single-copy native
evolution and legacy compatibility. The old episode loop rejects registered mode
until checkpoint and reward migration is complete. [Session and remaining integration](work-sessions/2026-09-09-registered-runtime-binding.md).

## Current gameplay evidence, unchanged

Model114 has114 fitted examples under the old objective. The endpoint has38 local
registrations,34 living species and42 specimens. The global union is **not yet
audited/imported**. Do not call38 a verified cross-run total. BaselineV1, old
contracts and all gameplay/learning receipts remain preserved.
