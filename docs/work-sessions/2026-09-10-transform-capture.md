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
