# Transform-aware capture continuation

## Mission check

1. Capability: distinguish persistent wild encounter identity from mutable battle
   appearance, while verifying the Pokémon actually received after capture.
2. Learned authority: maintenance unblocks fresh model6 destination/collection
   choices and outcome fitting; no learned combat or new authority claim.
3. Transfer test: ROM-free mid-switch and pre-transformed opponents, changed
   original identity, type immunity, HP/party/bag drift and non-Ditto capture.
4. Cheapest falsifier: legitimate Transform survives protected-state checks;
   an unrelated identity change still rejects before another controller action.
5. Time box: at most two hours; repair and a short fresh continuation, then review.
6. Stop: unverifiable attribution, unsafe boundary, lost specimens, consumed retry,
   or another mechanics failure. Preserve the state and actual costs.

Flash High owns an isolated observation/status implementation and regression draft.
Codex owns cartridge qualification, integration, actual received-stock verification,
live continuation, fitting and publication. No external agent controls the game.

Initial qualification rejects the prior suggestion to use `wCurOpponent` for
random wild identity: random encounter initialization writes `wEnemyMonSpecies2`.
The latter remains stable through Transform but is overwritten by successful
transformed capture. Therefore it is a live-encounter identity, never a substitute
for actual post-capture party/box and Pokédex evidence.

Read-only inspection authenticated the retained failed-state SHA and ROM before
restoring without controller access: wild battle1, original internal species76,
display129, transformed flag set, live types24/24, current-opponent0. Frame delta
and controller inputs were both0. This directly falsifies the current-opponent
proposal and supports the separate encounter/form adapter.

## Integration and qualification

Flash High completed one384.59-second draft, preserved in isolated local commit
`de37e45f`. Its first12-test run had10 passes and2 fixture-constant failures.
Codex corrected those constants and old reader fixtures, removed a redundant
type-option alias, validated explicit live types, used the public species catalog,
and required exactly two type bytes. The runtime now rechecks escape moves on
every setup turn, including Transform in reply to a status move rather than a
switch. Successful status reports retain original/displayed identity separately.

Five in-memory mutation probes targeted the original-identity address and guard,
HP preservation, live-type immunity, and repeated-turn escape checks. One immunity
probe initially survived: the test's Ground species already implied Ground typing,
so it did not distinguish live typing from catalog fallback. Codex replaced that
case with a transformed Porygon using Conversion; all five probes then failed a
test. No tracked source or private game state was mutated by this harness.

The real failed snapshot was authenticated and restored read-only again with the
new adapter: original76/display129, transformed true, Psychic24/24; no input or
frames. Independent outer-verifier tests retain actual Ditto and reject credit for
a different received species. Non-Ditto transformed captures remain explicit
unsupported-attribution failures rather than invented original-species credit.

Sources: [wild encounter initialization](https://github.com/pret/pokered/blob/master/engine/battle/wild_encounters.asm),
[RAM layout](https://github.com/pret/pokered/blob/master/ram/wram.asm),
[Transform](https://github.com/pret/pokered/blob/master/engine/battle/move_effects/transform.asm),
and [actual capture reload](https://github.com/pret/pokered/blob/master/engine/items/item_effects.asm).

The fresh continuation retains model6 and the final recovery checkpoint, with
at most four steps and1,200 seconds between-step budget. Neither consumed failure
is replayed. An initial preparation call stopped at the dirty-worktree check
before opening the gameplay path; actual execution requires this tested source
to be committed and published first. Live results will be recorded below.

## Fresh learning and measured preparation bottleneck

The published Transform repair drove one new model-selected Route15 attempt:
Venonat was captured and retained, registered credit rose39 to40, and physical
stock rose43 to44. The verified episode used415 actions and32,160 frames. Its one
eligible destination-choice outcome advanced the registered corpus6 to7 and
fitted model7. This is bounded development learning, not independent evaluation
or learned battle control. No live Ditto capture was demonstrated in this run.

The four-step runner was interrupted during preparation of step2 after repeated
Center path planning. No step2 proposal, choice, episode or controller input was
committed. Step1, its checkpoint and model7 remain durable; the other three steps
are unclaimed. The interrupted runner did not publish its normal final summary.

A90.03-second read-only profile at the retained checkpoint timed out in source
enumeration, with zero predictions or controller inputs. It recorded43 route
plans (53.62 cumulative seconds), including three Center-offer enumerations
(39.66 cumulative seconds). These are nested timings, not additive totals.
Flash's82.30-second static review suggested caching decoded routing worlds;
Codex did not adopt it: mutable nested data complicates safe caching and the
measured hot path was repeated recovery routing, not primarily ROM decoding.

### Bounded maintenance follow-through

- Capability: practical enumeration of missing-registration destinations.
- Learned authority: unchanged; unblock the next model7 destination choice.
- Transfer test: both default native recovery and capture-only menus, preserving
  guarded transport and escort qualification.
- Cheapest falsifier: disabling Center offers must not disable those guards;
  source-only enumeration must request no unused recovery offers.
- Time box: remaining session time, followed by a90-second read-only comparison.
- Stop: any changed capture qualification, failed regression, or unsafe input.

The router now separates recovery offers from guarded capture operation.
Regional enumeration opts out only of discarded RESTORE_TEAM offers; native
enumeration keeps its default. Escort qualification and fresh execution checks
still reject a fainted or unqualified party. No route cache or cross-state
memoization is introduced. Timing improvement remains unverified until measured.

## Comparison and closeout

The follow-up profile on published source `97542ada` also reached90.03 seconds
during source enumeration. It reached five router enumerations rather than three,
but neither profile completed the operation: this is not a measured end-to-end
speedup. Remaining work includes route searches for Fly connections (two calls,
21.63 cumulative seconds) and repeated authenticated checkpoint reads. Recovery
still exists in the native menu; only capture-only menus omit unused offers.

Validation:559 focused tests passed, full source typing passed (463 files), and
whole-repository lint, registry and documentation checks passed before publishing
the performance repair. This is not a full-suite test claim. GitHub CI for the
preceding Transform publication completed successfully.

Latest retained continuation: episode `red-registered-transform-20260910-a-01-causal`,
checkpoint SHA `38e4610b2bb857a620a98831cda08f9a43262b22e8434ddbe55754639ba8486f`,
registered model SHA `ffaa3135163828d57679f595d85f82c57bb6a7c8f77214353932081709947049`.
Use a new declaration from this endpoint; do not rerun the consumed launcher.
Its source/fit records authenticate the exact state and seven-row corpus.
Retained state SHA: `865bb2cf4e4f72ae26497999e943d3f7da4d25de6cf96089c81e8a5b22eb4711`;
registration observation sequence10. The refreshed saved-state dashboard projection
authenticates the episode manifest and shows Route15,40 registrations,36 current
species,44 specimens,14 capture items and15,503 money. This is saved evidence, not
a live game feed. Historical saved-state receipts remain unchanged.

Flash contributed an isolated mechanics draft and a read-only performance review.
Codex integrated, tested, corrected and measured; Claude was not used. The most
recent refreshed Flash quota showed61.86% five-hour and87.05% weekly remaining.
Those are account snapshots, not a measured cost for these calls.

Next session: a bounded route-search optimization, an unprofiled preparation-time
measurement, then fresh model7 gameplay. Keep this maintenance tied to that actual
learning attempt; do not expand into a routing rewrite or repeat cartridge audits.
The gameplay loop is stopped at this closeout; the status dashboard remains available.
Final combined regression run:676 focused tests passed, including reporting and
focus counters. The infographic was regenerated and visually checked; its
three-line scope text was moved inside the existing card boundary. The North Star
remains unchanged because no product requirement or authority gate changed.
