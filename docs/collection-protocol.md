# Preregistered battle collection protocol

## Scope and current status

The public
[`red-battle-collection-v6.json`](../configs/red-battle-collection-v6.json)
registry freezes one prospective Pokémon Red teacher-collection campaign:

- 68 stable public battle-plan identities in exact qualified-route order;
- five `train`, two `validation`, and five `test` root-lineage slots;
- partition-local ordinals `1/5` through `5/5`, `1/2` through `2/2`, and `1/5`
  through `5/5`, in addition to global collection ordinals `1/12` through `12/12`; and
- one unique 68-offset timing schedule and one attempt for each slot.

The v1 campaign's uncounted rehearsal completed all 312 checkpoints, all 36 objectives, and Hall
of Fame with 68/68 schedule attestations. Its first one-shot training root then failed at Route 24:
a poisoned Wartortle entered trainer 3 at 17/54 HP and Ekans trapped it with Wrap. That failure is
preserved in the private immutable ledger; v1 is not eligible for model fitting because its five
training roots can no longer all complete. The teacher now visits the already-planned Center before
that trainer, and an uncounted replay of the exact exposed schedule reached the following trainer.

The v2 campaign later qualified its complete dry rehearsal, but its first immutable training root
failed at the Rocket thief as documented below. V2 is therefore retired and remains preserved as
historical evidence. The v3 campaign also qualified a complete 312/312, 36/36, 68/68 Hall-of-Fame
rehearsal. Its first immutable training root reached Route 24 trainer 2 at checkpoint 42 before
three consecutive accuracy-reduced Water Gun misses let poison and enemy attacks faint Wartortle
with the opponent at 4 HP. The one-shot v3 failure remains in its private ledger, so v3 is retired
and cannot be used for fitting.

V5 passed its complete uncounted 312-checkpoint, 36-objective, 68-battle Hall-of-Fame
qualification, including the targeted Diglett-to-Dugtrio lesson. Its first immutable training root
then failed at the S.S. Anne rival after accuracy loss and the earlier opponents consumed both
retained Potions. V5 is therefore retired with that failure preserved. The current v6 registry
promotes exposed seed `15001` to its uncounted dry run and assigns twelve fresh, disjoint counted
seeds. The teacher now learns BubbleBeam before boarding, ranks that stronger move against the
first three rival members, and saves Bite for Ivysaur. V6 must pass its complete qualification
before any counted slot opens.

The retired v4 registry began with twelve fresh counted seeds. Its uncounted dry
seed `13001` deliberately replays that exact exposed v3 schedule. The teacher now heals at the
Center immediately before the accuracy-lowering trainer, may spend one of the already-budgeted
Route 24 Potions at a live low-HP MAIN boundary, and returns to the Center after the bridge when
that recovery was needed. Either branch proves the same four-Potion handoff before the Nugget
Rocket. The first v4 rehearsal survived the exposed damage sequence but revealed that the local
bridge loop left the main-command cursor on ITEM after recovery and repeatedly reopened the bag.
Stable MAIN states now pass back through the semantic move selector, which normalizes FIGHT and
proves the chosen move's PP decrement. The next replay passed both repaired trainers, then field
poison fainted Wartortle during the return walk to the Center. Route 24 now invokes the existing
exact Antidote cure at the stable post-bridge boundary before any movement, preserving all four
Potions and one Antidote for downstream routes. That replay then reached the Rocket thief, where
Drowzee sleep returned to MAIN between suppressed turns and exposed a dialogue-only recovery
assumption. The shared battle runtime now normalizes MAIN to FIGHT and MOVE to the latched legal
slot on every sleeping turn while preserving the exact unchanged-PP proof. The complete v4
rehearsal then cleared Rocket, both Route 6 trainers, and every earlier repair before the S.S.
Anne rival fainted Wartortle with Ivysaur at only 3/57 HP. The route now buys and carries one
additional Potion through every bounded handoff, giving that adaptive rival controller two
recoveries without making either use mandatory. The complete v4 rehearsal is still required
before any v4 counted slot can begin. That repair cleared S.S. Anne and Surge, then exposed a
five-turn sleep value (`0x05`) at the Rock Tunnel field-recovery boundary. Gen I stores remaining
sleep turns in the low three status bits, so the field recovery now treats every value from one
through seven as sleep, consumes the already-budgeted Awakening, and accounts for it exactly.
The following replay crossed that field gate, but DUX was paralyzed after reducing the final
trainer's Bellsprout to 3/57 HP and then fainted inside repeated Wrap. The two final Grass
trainers now enable the existing status-protection role pivot: once status makes DUX unavailable,
the healthy story lead owns the matchup for the rest of that battle instead of immediately
switching back into the impaired specialist.
That replay cleared all nine Tunnel trainers and reached Lavender, but the resource contract
correctly rejected zero remaining Awakenings: DUX had been awakened immediately during an earlier
battle despite a healthy reserve, then needed the second item at a later field boundary. Status
recovery now prioritizes the healthy party pivot and spends an Awakening only when no safe reserve
exists, preserving the declared Pokémon Tower contingency.
The next replay preserved that item but won final Tunnel trainer 5 after pivoting before DUX had
executed its declared Peck lesson. The physical victory was rejected rather than mislabeled.
Final-tunnel role reassignment is now gated on an observed PP decrement from the required DUX
move; once that evidence exists, the adaptive type/status pivots resume normally.
If the aggregate Lavender contract still fails after its individual gates, the retained private
diagnostic now reports the complete public-safe trainer, inventory, party, and route ledger rather
than a generic rejection, allowing the next repair to target the exact invariant.
That ledger proved all eleven trainer lessons, seven wild escapes, party state, healing, Repels,
and route gates passed; only the Tower reserve failed after two legitimate Awakening uses, with
`$1,761` still available after every other restock. The route therefore carries a three-item
total reserve and preserves one after the observed two-use lineage.
The first three-reserve attempt paid for four Repels but failed their inventory settlement after
changing the original Awakening quantity selector. Splitting the added copy into a final same-Mart
top-up proved the Repels but reproduced the unsettled Awakening stack. Buying two at the original
Cerulean stop then proved the early route did not yet have the extra ₽200. The extra copy is now a
separate Cerulean purchase after the Nugget Rocket reward: the earned Nugget is sold for its exact
₽5,000 value, the funded top-up carries two forward, and Vermilion performs its already-qualified
single-Awakening, two-Parlyz-Heal, four-Repel sequence to reach the same three-item reserve.
The same funded Cerulean top-up now adds one Potion for the mandatory Gym trainer. Route 25
consumes its planned recovery from six to five; the Gym controller may spend the fifth item only
at a live low-HP MAIN boundary under confusion, or use it as post-battle field recovery when the
lineage wins without crossing that threshold. Either path restores the exact four-Potion Rocket
handoff instead of weakening the downstream reserve.

Historically, the v3 registry had twelve fresh counted seeds. Its
uncounted dry seed `12001` deliberately replays the exact schedule that exposed the v2 failure;
none of its counted train, validation, or test seeds reuse a v1 or v2 assignment.
The first v3 rehearsal reached checkpoint 44 with Wartortle at 2/56 HP before the Nugget Rocket's
Ekans trapped and fainted it. The failed rehearsal remains private and uncounted. The already
budgeted Route 24 Potion is now consumed before that battle instead of after victory, preserving
the same four-Potion downstream handoff. The corrected source must repeat all 312 checkpoints and
attest all 68 battle offsets before any counted v3 slot can begin.
The next replay cleared both Rocket fights but reached the same exact-one-use assertion after the
first required Route 6 trainer. Route 6 recovery is now conditional under the identical live HP
gate, and unused Potions remain available to later objectives instead of being spent to normalize
an historical inventory count. The S.S. Anne rival may spend that bounded surplus repeatedly when
its live low-HP gate recurs, reusing one battle intent across recovery.
That correction carried the rehearsal through Surge and checkpoint 109 before Rock Tunnel B1F
trainer 5 status-locked DUX. The healthy Wartortle pivot then treated Bulbasaur as a generic
matchup and spent resisted BubbleBeam plus its two-heal allowance before fainting. Bulbasaur now
belongs to the reusable Grass-matchup set, so a replacement story lead ranks neutral Bite instead.
The failed rehearsal remains private and uncounted.
The next replay survived that matchup, then a still-paralyzed Wartortle lost its selected
BubbleBeam turn against B1F trainer 4 before the opponent self-destructed. Victory set the trainer
event without spending the required evidence PP. The route now cures supported status before the
self-destructing Hiker sequence and carries a second Parlyz Heal for the later Grass contingency,
preserving both executable teaching evidence and status robustness.
That replay then cleared Rock Tunnel, Rocket Hideout, and Pokémon Tower before consuming the
ten-Great-Ball reserve plus all surviving Poké Balls at the one-time Route 12 Snorlax. The teacher
now establishes a completion-oriented 25-throw combined reserve with a thirty-three-throw total
controller bound and sells the temporary remainder after capture. The static encounter no longer
depends on unbounded leftovers from earlier species searches.
An attempted thirty-ball reserve failed closed at the Mart because its ₽19,400 combined capture
and healing cost exceeded the live ₽16,897 balance. Twenty-five balls plus both Super Potions cost
₽16,400, retain the recovery contract, and require neither selling future-use TMs nor relying on
earlier Poké Ball leftovers.
The funded replay caught Snorlax in six throws and continued through Koga and the Celadon Gym
trainers before a wandering Center NPC occupied the first exit tile beyond the original eight
bounded waits. Movement now retains the same release-and-observe semantics with sixteen bounded
waits, covering a complete longer NPC cycle without teleporting or changing the route.
The exact replay showed the NPC can remain parked while the player waits directly above it even
through that longer window. The second Center exit now uses the legal open side corridor around
the occupied tile and rejoins the same doorway below it; no collision retry or NPC timing is
required for that handoff.
The first side-detour rehearsal reached checkpoint 223 but could not move left; the exact right-side
replay failed at the same coordinate, proving those apparent alternatives were structural walls.
Because the party is healed immediately before the hazard-free rooftop TM exchange, the exchange
now verifies that state and returns only to the Center entrance instead of performing a redundant
second nurse visit. The doorway is then one step away. This remains an uncounted source repair and
requires a new exact dry qualification.
That entrance-return lineage cleared Erika and formed the complete six-member party, then reached
Sabrina at checkpoint 261. A Hyper Potion wait exhausted its pre-action samples even though the
diagnostic reread already showed the main battle phase. The bounded recovery now accepts a main
menu reached by the final cancel pulse, while the independent exactly-once item-decrement contract
is unchanged. This late failure was also uncounted and requires another exact dry qualification.
The post-observation replay then showed the underlying Sabrina strategy could consume all seven
Hyper Potions while falling below the same threshold after every enemy reply. The Celadon purchase
now reserves three X Specials: one for the Silph rival and two independently verified setup uses
for Sabrina. This staged Special-defense lesson changes the battle state instead of extending an
unproductive healing loop, and the exact source again requires full dry qualification.
The staged replay defeated Sabrina and reached checkpoint 275 before a Mansion encounter Disabled
the lead's last preferred move with PP. Lead training now uses battle-active PP, excludes only a
currently disabled slot, and performs a bounded flee when no legal preferred attack remains. This
aligns the lead block with the existing balanced-team recovery semantics and requires another
uncounted exact-source qualification.
That replay completed the level-75 six-member curriculum and reached checkpoint 296 before the
Indigo shop lacked ₽611 for two Revives. The final economy now sells leftover Antidotes and buys
two Full Heals instead of three while preserving six Full Restores, eleven Hyper Potions, both
Revives, and every League setup item. This uncounted repair keeps the capture and balanced-team
contracts intact and again requires complete exact-source qualification.

The now-retired v2 registry began as a prospective campaign with fresh counted seeds.
Its first uncounted dry run reached checkpoint 70 before a walking Cerulean NPC blocked the Route 6
healing-replay corridor. The failed private artifact is retained. A bounded yield-and-retry repair
then carried that exact rehearsal schedule through the next checkpoint. The registry below binds
the repaired source; it still requires a new complete dry run, and all twelve counted slots remain
unexecuted. The next replay cleared that collision, reached checkpoint 91, and then exhausted the
25-ball Forest capture reserve while attempting Pikachu. The repaired source raises that legal
reserve to 30 and expands the later bounded cleanup gate accordingly; its downstream economy is
part of the next required full rehearsal. The longer purchase cadence also shifted Route 11 and
reached the old 72-encounter Spearow cap; the repaired source gives that search a dedicated
96-encounter bound while retaining the exact species and level requirement. This remains a plan, not a held-out-result claim, and
contains no trajectory, ROM, snapshot, private path, or completion evidence.
That replay then cleared both capture curricula and reached the live Lt. Surge battle. Diglett
defeated the first opponent with 10/30 HP remaining, but the next opponent moved before its third
Dig and knocked it out. The teacher now performs one bounded Super Potion recovery only from a
proven low-HP MAIN battle gate, verifies both the HP increase and inventory decrement, and resumes
the Dig-only plan. The complete v2 rehearsal remains the next qualification gate.
The exact replay proved that recovery and the Dig-only victory through checkpoint 97. The
following Lavender entrance then rejected the correctly depleted potion slot because its legacy
handoff allowed only one remaining Super Potion. That boundary now accepts either zero or one and
still restores the observed quantity to the same fixed twelve-potion downstream reserve with an
exact money-and-inventory proof.
That replay reached checkpoint 102 and proved the handoff, then showed that blindly replacing the
consumed potion would exceed the exact early-game budget by ₽409. The intermediate repair retained
the planned tunnel allocation regardless of whether Surge consumed the carried reserve, recorded
the observed zero-or-one starting quantity explicitly, and proved the conservation equation
`starting + purchased - used = remaining`. Lavender still tops the result back to twelve after
selling TM28, so the downstream reserve is unchanged.
The next replay proved that the 30-ball capture curriculum also displaced ₽1,400 needed for four
Rock Tunnel Repels. Historical qualified recovery evidence used five Super Potions across this
chapter, and the live contract already requires at least five at Route 9. The purchase therefore
allocates ten Super Potions plus the observed starting remainder, preserving a two-times safety
margin and all four Repels; the later exact top-up still restores twelve.
That replay validated the complete economy repair through Rock Tunnel and continued to checkpoint
220. Koga's terminal mutual-KO recovery had completed the physical battle outside the adaptive
turn loop, but had not closed the collection schedule lifecycle; the next Erika battle therefore
failed closed as an apparent intent change. The externally settled trainer exit now closes the
matching already-applied schedule entry exactly once, alongside the existing observer lifecycle.
The following exact replay proved that repair, defeated Erika, and reached checkpoint 230 before a
moving fourth-floor department-store customer occupied the evolution-stone clerk route. A bounded
eastward yield maneuver now preserves and restores the exact approach coordinate until the customer
vacates the single blocked tile.
That replay proved the yield, entered Silph Co., and reached checkpoint 243 before the rival
knocked out Blastoise with 17 enemy HP remaining. The bounded rival controller now treats the live
active battler—not only the field lead—as its recovery subject, selects the healthiest living
reserve from the forced-switch menu, and resumes with that reserve's actual PP. This is a reusable
full-party lesson rather than another lead-only retry.
The first replay of that lesson proved the knockout branch but showed that Gen I presents bounded
faint dialogue before the forced party cursor accepts movement. The selector now interleaves a
periodic confirmation with cursor normalization, matching the already-qualified Koga mutual-KO
pattern while still proving the chosen living reserve and restored MAIN state.
The next replay reached the same turn with both Blastoise and the rival's final Pokémon at zero HP.
That terminal mutual-KO is now distinct from a mid-battle KO: the teacher selects a living reserve,
accepts the proven battle exit instead of requiring another MAIN menu, and closes the matching
Silph schedule and observer lifecycle exactly once.
That repair proved the rival victory at checkpoint 244, but post-battle text still owned input when
the elevator route began. Terminal recovery now clears bounded dialogue and requires two consecutive
field-readiness observations before any navigation, matching the normal adaptive runtime contract.
The next exact rehearsal proved that repair, completed the six-member balancing block with every
trainee in the upper seventies, defeated Blaine and Giovanni, crossed Victory Road, and reached
checkpoint 296/312. The expanded bounded capture curriculum legally consumed all thirty Poké
Balls, but Indigo cleanup still required at least one leftover before opening its sale path. The
cleanup contract now accepts the complete zero-through-thirty remainder range, skips the sale when
the stack is empty, and retains the exact downstream supply checks. The failed rehearsal remains
private and uncounted; this corrected exact source must repeat the full dry run before slot `01`.
That replay again reached checkpoint 296 and accepted the empty stack, then exposed that the old
positive-sale branch had also supplied an implicit menu transition: cancelling after a completed
sale returns to BUY/SELL, while skipping the sale leaves field control at the clerk. The zero path
now interacts with the clerk explicitly before selecting BUY; the positive path retains its
cancel-to-menu transition. The second failed rehearsal also remains private and uncounted.
The corrected v2 source then completed **312/312 checkpoints**, **36/36 objectives**, Hall of Fame,
and a **68/68** offline schedule audit, publishing the required dry-run qualification. Its first
immutable training slot reached checkpoint 62 before Drowzee defeated a 0/66-HP Wartortle with
24/50 HP remaining. That failed outcome is retained in the private v2 ledger and makes v2
ineligible for the required five complete training roots. The teacher now carries one additional
already-owned Potion out of the Cerulean reserve, spends it at the Rocket thief's live low-HP MAIN
gate only when needed, and ranks the stronger Mega Punch after the required one-use Bite lesson.
A v3 campaign with fresh counted seeds must qualify this repair; the v2 slot is never rerun.

The latest v4 clean-power rehearsal passed the repaired Cerulean economy, Misty, the Rocket route,
the S.S. Anne, and the Diglett curriculum through checkpoint 91 before one level-6 Kakuna consumed
the six Poké Balls left by earlier captures. The generic source adapter had allowed a single
full-health encounter to spend the complete campaign remainder. It now caps one encounter at five
throws, verifies the exact decrement, and returns a failed bounded attempt to the area survey as a
fresh-encounter retry rather than false capture progress. This applies to every live wild-source
survey; the private failed artifact remains uncounted and the modified source must requalify the
complete 312-checkpoint/68-battle rehearsal.
That retry-capable replay returned to checkpoint 91 and then reached the Forest's older 64-leg
physical traversal bound. Because failed capture attempts now legally seek a fresh specimen, the
Forest permits 256 finite corridor legs while retaining its independent 1,000-encounter and
20,000-action ceilings. Collection changes remain accepted only after exactly one new retained
specimen appears.
The expanded traversal then reached the independent 20,000-action ceiling after the finite reserve
had already been consumed across several full-health encounters. The source adapter now applies
the portable capture policy instead of extending search again: it chooses a healthy low-level
Rattata, Caterpie, or Pidgey, performs one verified Tackle or Gust weakening action, proves the PP
decrement and target damage, and only then enters the five-throw budget. A knockout returns as a
fresh-source retry without collection progress, and an empty reserve fails immediately.
The first live weakening attempt arrived during wild-introduction dialogue rather than MAIN. The
adapter now preserves the encounter identity and party, invokes the existing bounded battle-menu
normalizer, and applies its strict helper-switch gate only after PARTY-selected MAIN is observed.
That normalized replay exposed that the shared navigator had no PARTY destination because earlier
callers used only FIGHT, ITEM, and RUN. PARTY now has an explicit bounded transition from each
main-command position before the adapter opens the helper list.
That route then proved repeated one-PP weakening hits before a failed Pikachu throw let the 1-HP
Rattata helper faint. After target damage is proven, the adapter now uses the same verified party
transition to restore the healthy story lead before any ball is thrown. The helper teaches the
weakening action but does not absorb the complete retry sequence.
A later faster Pikachu knocked out Rattata before Tackle executed. Forced-switch recovery now
selects the protected lead through a verified live party cursor. Target damage plus PP decrement
decide whether capture may continue; otherwise the restored lead flees and the survey retries a
fresh specimen without crediting a capture.
The first forced-switch attempt saw the stale move-menu cursor address immediately after fainting.
It now advances at least one bounded faint-dialogue transition before a live party cursor can be
accepted, while retaining the cursor-tile, party-range, species, and target-HP gates.
Because the first confirm left the full snapshot and cursor pointer unchanged, elapsed attempts are
no longer accepted as progress. The pre-faint cursor address is retained and party selection is
permitted only after a different valid live cursor address appears.
The exact branch remained unable to restore MAIN because Pikachu could outspeed and knock out the
low-level helper before it acted. Pikachu is now a Red-adapter direct-throw target behind the
durable lead. Passive Metapod and Kakuna still exercise weaken-then-throw; the threatening target
uses its high catch rate and the same five-throw limit without deliberately sacrificing a helper.

One invocation against the superseded registry
`24520b0f5cfb027cf1339261a179650cda6e7792058af148af8722333bfdf72b` stopped before
the episode header or emulator startup because the path-free serializer rejected a canonical
relative PyBoy inventory name. Its failed private artifact is retained, but it contains no
gameplay, schedule application, campaign seal, or declared-slot outcome. This revision permits
only validated location-free distribution inventory names at the exact structural runtime field;
absolute paths, traversal, spoofed keys, and every other path-bearing field remain invalid. The
registry below supersedes that preflight-only identity.

The exact source and configuration commit must be committed and pushed to GitHub before the
schedule dry run or any declared attempt begins. The command verifies that the clean local commit
is reachable from a remote-tracking branch. The registry loader resolves that commit once, reads
the registry and executable source from that exact object ID, and carries the same object ID
through metadata construction; a concurrent commit or checkout change fails before execution.
That pushed Git commit—not the co-committed digest
sidecar by itself—is the public preregistration anchor. Every dry-run header records the commit,
registry digest, and teacher-execution digest. Before slot `01`, the private campaign seal fixes
that exact source commit and registry digest for all twelve outcomes. If executable source,
behavior, objective graph, roster, assignment, or schedule changes before collection, regenerate
and publish the registry and sidecar first. Once a counted slot has started, such a change requires
a new registry version rather than replacement of the observed result.

## Canonical byte convention

Every content-addressed JSON document below uses the same canonical newline encoding. For a JSON
value `x`, define:

```text
C(x) = json.dumps(
    x,
    allow_nan=False,
    ensure_ascii=True,
    separators=(",", ":"),
    sort_keys=True,
).encode("ascii") + b"\n"

D(x) = lowercase_hex(SHA256(C(x)))
```

`C(x)` therefore has sorted object keys, compact separators, ASCII escaping, no non-finite
numbers, and exactly one trailing line feed. Array order remains significant. The registry itself
must equal `C(registry_object)` byte for byte. Generated values remain in the canonical registry
and sidecar; `scripts/regenerate_collection_registry.py --check` independently rebuilds the
prospective bytes and fails when they are stale.

## Frozen public identity

The prospective campaign published by this version has these independent golden values:

| Field | Frozen value |
| --- | --- |
| Registry bytes | `6518` |
| Registry SHA-256 | `b6644123def08aec1637f7bf2edf44c3dc3d4a862d56df4402f2a235594eda78` |
| Source bundle SHA-256 | `62c92d15e7ced29653b4a50fb4352cffd2e6ca7473f7ffae521bd7074f542a4a` |
| Behavior configuration SHA-256 | `6b1ead4078541ca953ed432e90c175710d4c4f7a2b096f14ed9ed5cb6c71b39d` |
| Objective graph SHA-256 | `453ba1dcecbb33df9e10a911ac93090ff9a5080b07e02a5594e34a015e5bd3b6` |
| Teacher execution SHA-256 | `31cbc829256c4f6a258750996c00778b8796c4be4b9131d16ae97535620d5111` |
| Dry-run schedule SHA-256 | `44f7f521126553fbc94a7868b65bfe87237ef740dba8965ad401c9043b6c7e28` |
| Slot `01` assignment ID | `70c361a4d2ad62f723fd97874f975560ac5cd3d869ed6681509e03596fc1622d` |

The tests independently pin these values so an accidental registry, source, behavior, objective,
or assignment change fails before collection.

## Exact content-addressed identities

### Battle roster and schedules

The roster digest is:

```text
D({
  "battle_plan_ids": [the exact 68 IDs in qualified route order],
  "schema": "pokemon-red-battle-plan-roster-v1"
})
```

The array must equal the 68-entry `RED_BATTLE_PLAN_IDS` tuple exactly. A missing, duplicated,
substituted, or reordered ID is invalid even if the array length remains 68.

For each roster ID, `sha256-mod-v1` derives a frame offset from 0 through 255. The SHA-256 input is
the following exact byte concatenation:

```text
ASCII("pokemon-red-battle-start-offset-v1")
+ NUL
+ harness_seed as exactly 8 unsigned big-endian bytes
+ NUL
+ ASCII(battle_plan_id)
```

Interpret the first eight digest bytes as an unsigned big-endian integer and reduce modulo 256.
The expanded schedule digest is:

```text
D({
  "offsets": [
    {"battle_plan_id": ID_01, "frames": OFFSET_01},
    ...,
    {"battle_plan_id": ID_68, "frames": OFFSET_68}
  ],
  "schema": "pokemon-red-battle-start-offset-v1"
})
```

The registry commits the complete expanded-schedule digest, not merely its seed. Seeds and
schedule digests are unique across all twelve counted slots. The fixed dry-run seed and schedule
digest are also disjoint from all twelve.

### Executable source bundle

The source bundle is computed from one resolved Git commit. Its inventory contains
`pyproject.toml` and every regular committed blob below `src/pokemon_red_completion/`. Collection
configuration is deliberately outside this bundle to avoid self-reference. For each blob:

```text
{"bytes": exact_blob_length, "mode": "100644" | "100755",
 "path": ASCII_git_relative_path,
 "sha256": lowercase_hex(SHA256(exact_blob_bytes))}
```

Sort entries lexicographically by `path`, then compute:

```text
D({
  "files": [sorted file entries],
  "schema": "pokemon-red-executable-source-bundle-v2"
})
```

The registry loader resolves one `HEAD` commit and recomputes this digest from that commit's Git
blobs. Immediately before a scheduled run, the command also hashes the live working files,
including untracked source, rejects ignored executable content, and requires exact equality with
the committed bundle. Uncommitted or ignored working-tree content cannot satisfy the frozen
execution identity.

### Teacher behavior configuration

The behavior digest is:

```text
D(the exact "behavior_configuration" object)
```

That object uses schema `pokemon-red-teacher-behavior-v1` and fixes the emulator name and version,
disabled human input, disabled save-on-exit, the new-game/opening/play timing maps, the pinned
pret/pokered commit, and the battle-schedule application schema. Window visibility and playback
speed are presentation metadata, not part of the behavior digest; changing them does not change
the teacher policy.

The objective-graph digest uses the same encoding and an explicit domain schema:

```text
D({
  "objectives": [the exact topologically ordered public objective payloads],
  "schema": "pokemon-red-objective-graph-v1"
})
```

Each objective payload includes its identity, title, specialist, sorted prerequisites, and sorted
completion facts.

The teacher execution digest is:

```text
D({
  "actor": ACTOR,
  "adapter_id": ADAPTER_ID,
  "behavior_configuration_sha256": BEHAVIOR_DIGEST,
  "collection_id": COLLECTION_ID,
  "game_id": GAME_ID,
  "objective_graph_sha256": OBJECTIVE_GRAPH_DIGEST,
  "ontology_id": ONTOLOGY_ID,
  "policy_id": POLICY_ID,
  "schema": "pokemon-red-teacher-execution-v1",
  "source_bundle_sha256": SOURCE_BUNDLE_DIGEST
})
```

Every counted assignment binds this single execution identity.

### Registry sidecar

The registry digest is SHA-256 over the exact canonical registry bytes. The sidecar must itself
equal:

```text
C({
  "bytes": exact_registry_byte_length,
  "schema": "pokemon-red-collection-registry-digest-v1",
  "sha256": lowercase_hex(SHA256(exact_registry_bytes))
})
```

The loader resolves one commit, reads and validates the canonical sidecar first, reads the
registry from the same commit, authenticates its exact byte length and SHA-256 before parsing it,
then checks that the execution contract names the source bundle recomputed from that commit.
Because registry and sidecar are committed together, this is an authentication and corruption
check rather than an independent timestamp. The pushed commit is the public anchor, and the
write-once private campaign seal prevents a different registry or source commit from replacing it
after collection begins.

### Assignment, lineage, and episode identity

For a declared run, the assignment digest is:

```text
D({
  "collection_id": COLLECTION_ID,
  "harness_seed": UINT64_SEED,
  "partition": "train" | "validation" | "test",
  "registry_sha256": REGISTRY_DIGEST,
  "run_id": RUN_ID,
  "schedule_sha256": EXPANDED_SCHEDULE_DIGEST,
  "schema": "pokemon-red-collection-assignment-v1",
  "teacher_execution_sha256": TEACHER_EXECUTION_DIGEST
})
```

The private root-lineage ID is `red-root-<assignment digest>` and the private episode ID is
`red-teacher-<assignment digest>`. Metadata also records `attempt.counted=true`,
`attempt.attempts_per_slot=1`, the global slot ordinal and total, and the partition-local ordinal
and total. These fields are derived from the authenticated registry rather than accepted as
mutable command-line labels.

## Mandatory schedule dry run

Before global slot `01`, run the registry-declared schedule integration dry run:

```bash
pokemon-red-completion record \
  --private-root /absolute/private/trajectory-directory \
  --schedule-dry-run
```

It is a clean-power-on, full-route rehearsal using the same frozen execution contract and the same
68-ID instrumentation path, but the fixed seed `13001` and its distinct schedule. Its metadata is
`partition=unassigned` and `attempt.counted=false`, and explicitly binds the registry, source
commit, source bundle, behavior, objective graph, and teacher-execution digests. It must not enter
train, validation, or test data, and it must not enter any performance denominator. A normal
unplanned recording is not a substitute.

The dry run must finish successfully and attest all 68 offsets before slot `01` starts. A failed
dry run does not consume a declared slot, but collection must pause until the defect is corrected.
Any correction to a frozen input must be committed, pushed, and reflected in a regenerated
registry and sidecar before repeating the dry run.

After the complete episode and all 68 attestations pass their offline audit, the recorder publishes
a separate immutable dry-run qualification in private storage. It binds the registry, exact source
commit and execution digests, CPython/PyBoy runtime, ROM hashes, dry seed and schedule, episode ID,
manifest digest, and 68/68 audit receipt. Before any counted slot can create the campaign seal or
episode namespace, the command reopens that referenced episode and reruns the audit under the same
exclusive collection session. Absence, identity drift, replacement, or malformed evidence fails
closed. This qualification is not a campaign outcome and never enters an evaluation denominator.

## Runtime schedule attestations

At the first stable main battle menu, before the policy's first choice, the runtime claims the
next roster offset. A positive offset is executed as a normal `WAIT` through the frame-safe
executor; a zero-frame offset creates no fake execution. In both cases the semantic state is read
again before policy inference. Re-entry into the same physical battle never reapplies the offset.

Each application produces exactly one private `battle_start_offset_applied` event containing:

- `battle_ordinal`, `battle_plan_id`, `frames`, and `schedule_sha256`;
- `before_snapshot_sha256` and `after_snapshot_sha256`; and
- `execution_step_index`, which is `null` for zero frames and otherwise identifies the preceding
  `WAIT` execution.

The terminal event must contain a `battle_start_schedule` attestation with `complete=true`,
`expected_battles=68`, `finished_battles=68`, and the same schedule digest. Duplicate or unknown
IDs, intent changes, schedule mismatch, reordering, substitution, partial application, an extra
battle, or an unfinished schedule fails the attempt.

After the episode is atomically published, an offline audit rereads the durable artifact. It
requires the real trajectory header/event/execution schemas and content-addressed snapshot records;
synthetic rows that the production sink could not emit are invalid. For
every positive offset it requires the linked execution to be a successful, decision-free
`WAIT(repeat=frames)` with exactly the declared frame count and matching before/after snapshot
hashes. A zero offset must have no execution link. Because the runtime rejects policy-visible
drift during an offset, every attestation must have identical before/after policy snapshots. The
same audit authenticates the header's complete offset array and the sole terminal event. A
metadata-only claim therefore cannot pass.

## One-shot accounting and power-loss recovery

Before the first counted attempt, a private immutable campaign seal binds the collection,
registry, exact pushed source commit, source bundle, behavior, objective graph, teacher execution,
runtime, ROM, and complete twelve-slot roster identities. Runtime identity includes the CPython
implementation/version, exact interpreter-binary digest, PyBoy version, and a canonical digest
inventory of installed PyBoy files. Each assignment is then a single-attempt namespace. The outcome ledger
classifies every consumed slot as `complete`, `failed`, `interrupted`, or `invalid`, retains an
explicit reason code, and exposes a path-free receipt with all twelve slots and all pending and
terminal counts.

A process interruption or power loss does not create permission to rerun the same seed. On the
next reconciliation, a valid completed manifest left in a partial directory can be recovered as
complete; a finalized failure remains failed; and an unsealed orphan partial is classified
`interrupted` with the corresponding ledger rationale. Failures, invalid artifacts, and
interruptions consume their slot. Replacing any such outcome would permit outcome-dependent
cherry-picking, so a protocol restart requires a new registry version.

The deterministic partial episode directory is the start claim. Its directory metadata and the
private-root directory entry are synchronously persisted before emulator execution can begin. A
power loss therefore cannot turn an already-started counted attempt back into an absent slot.
Completion validation also recomputes the recorded runtime-document digest and requires the
top-level source, objective, behavior, assignment, and schedule identities instead of trusting
detached digest copies.

The public receipt's `ledger_sha256` is `D(core_receipt)`, where `core_receipt` is the complete
path-free ledger object before its `ledger_sha256` field is added.

The current state can be reconciled without starting a slot:

```bash
pokemon-red-completion collection status \
  --private-root /absolute/private/trajectory-directory
```

The ROM may be supplied with `--rom` or `POKEMON_RED_ROM`. Before a campaign exists, this command
reports twelve pending slots without creating a seal. Afterward it verifies the frozen campaign
identity and safely classifies any power-loss partial before returning the path-free ledger.

## Analysis and claim boundary

The current feature schema is `pokemon.core.battle.move-ranker.v2`. It retains goal and move-policy
context and adds the candidate-relative feature `constraint.matches_required_move`.
`exact_required` decisions are forced choices; `any_usable` decisions are free choices. Collection
and model receipts report the counts and accuracies separately, including unobserved-context
counts. Forced-choice accuracy measures compliance with a teacher-supplied constraint and cannot
stand in for autonomous move selection; free-choice accuracy is the more relevant generalization
measure. Overall accuracy remains descriptive.

`teacher_recovery_marker` currently records only `none` or `bounded_recovery`. It is descriptive
metadata, is not a model feature, and does not encode a typed recovery budget or envelope. It
cannot by itself establish recovery-policy coverage or qualify a recovery learner.

Exact episode, manifest, assignment, schedule, or root-lineage reuse across partitions is hard
leakage and fails the audit. Repeated policy-visible semantic snapshot hashes can occur naturally
under distinct hidden timing/RNG schedules, so their overlap is report-only. Reports must disclose
the visible-overlap count and performance on novel visible states separately; visible semantic
overlap alone is not grounds to discard or replace a preregistered attempt.

Disjoint preregistered lineages are necessary but not sufficient for promotion. Model selection
uses train and validation only; the five test slots remain unopened until the feature schema,
model, thresholds, and analysis rules are frozen. Promotion additionally requires a
registry-authenticated corpus audit and learned battle rollouts with teacher fallback disabled.
The implemented `learn battle fit` command enforces that boundary: it requires all seven learning
outcomes, rejects any consumed test slot before loading a dataset, and publishes only a private
candidate plus aggregate validation evidence. It has not executed while the campaign is pending.

The current uncounted qualification replay also validates conservation across curriculum stages.
After the revised early capture policy passed its former Viridian Forest bottleneck, it retained
15 unused Poké Balls but lacked the cash required by the fixed Rock Tunnel supply contract. The
teacher now sells 14 at the Vermilion Mart, retains one legal capture/capacity token, proves the
corresponding inventory and money deltas, and then proves the full supply-purchase ledger. The later
Snorlax capture remains isolated behind its own Great Ball budget, so this conversion cannot
silently spend a future capture reserve.

That exact replay proved the sale and purchase ledger at checkpoint 103 and reached Rock Tunnel
trainer 5 at checkpoint 109. DUX escaped after becoming paralyzed, but the replacement Wartortle
was also paralyzed and fainted after lost turns. The live battle adapter now distinguishes sleep
from paralysis, spends only the surplus second Parlyz Heal at a verified main-menu gate, proves
the cure and item decrement, and retains one cure for the later tunnel evidence battle. This was
an uncounted failure; the source must repeat the full dry qualification.

The next replay passed that battle and every chapter through checkpoint 271 before exposing a
15-slot Cinnabar bag against the qualified 16–19-slot capacity curriculum. Retaining exactly one
early Poké Ball preserves the later full-bag reward lesson without introducing a new Cinnabar
purchase: it is legal backup for Snorlax, survives the Great Ball cleanup, and is sold by the
existing Indigo normalization. The observed 14-ball sale still funds all required Repels.

Retaining that token shifted later battle timing and exposed Rocket Hideout Giovanni's historical
helper-sacrifice recovery path at checkpoint 136. The teacher now invokes the same reusable
recovery primitive in preservation mode: a living helper absorbs only the item-turn reply, the
lead's exact Super Potion use is proved, the lead is restored immediately, and one attack must
follow before another recovery. This aligns the rehearsal with the balanced-party objective and
keeps the original finite item reserve; the failed replay remains uncounted.

That repair passed Giovanni and Pokémon Tower before the Snorlax restock exposed a ₽100 shortfall.
The earlier Lavender top-up had been adding one Parlyz Heal regardless of whether Rock Tunnel
consumed any. It now restores a fixed two-cure reserve instead: zero consumed means zero repurchased,
one consumed means one repurchased, and the exact cash and inventory ledger is still mandatory.
This saves ₽200 on the observed no-cure schedule while preserving both cures, the capacity token,
and the full later capture/recovery budget. The replay remains uncounted.

The replay still fell ₽403 short of its second Snorlax Super Potion because it bought the older
25-Great-Ball reserve in addition to the retained capacity ball. The purchase now binds the same
25 legal throws as before—24 Great Balls plus that one Poké Ball—saving ₽600 while remaining seven
throws above the historical 18-throw exhaustion. Both recovery items remain mandatory and the
controller's independent thirty-three-throw ceiling is unchanged.

The funded replay caught Snorlax in three throws and reached the Silph rival at checkpoint 243,
where Venusaur fainted the lead after the two-item recovery budget was exhausted. The teacher now
keeps the healing and party-depth bounds separate: it still spends at most two Hyper Potions, then
uses the existing verified forced-switch path for at most four living reserves without reopening
recovery. This is balanced-party continuity, not a larger healing or retry allowance. The failed
replay remains uncounted.

The corrected v4 source subsequently passed all 312 checkpoints, 36 objectives, and the 68-battle
dry-run audit. Its first one-shot training slot then failed at Route 24 trainer 1 after Wartortle
entered the final bridge fight without another Center recovery. That outcome is retained in the
v4 ledger and is never rerun. Because v4 can no longer provide five complete training roots, the
teacher now reuses its verified bounded Center backtrack before the final bridge trainer and must
publish and qualify a fresh registry before collection restarts.

V5 then froze disjoint seeds and its new uncounted schedule reached the Cerulean rival with
Pidgeotto at 6 HP when Wartortle exhausted its protected Potion allowance and fainted. The living
Zubat helper was already part of the qualified party and accuracy-reset curriculum, but had no
post-KO continuation. The teacher now preserves the exact Route 24 Potion reserve, performs at
most one observed forced switch to that helper, and chooses a legal move from the active battler's
live move/PP evidence. The failed qualification is uncounted; v5 must be regenerated and replayed.

That replay proved the helper switch and one legal Zubat attack, but the helper also fainted. The
underlying defect was an unproductive recovery loop: every enemy reply could leave Wartortle below
the same threshold and immediately trigger another Potion without an intervening attack. Rival
recovery now latches one mandatory legal attack after every exact Potion use. No item, healing,
switch, or retry bound is increased; the helper path remains only a final contingency.

With that latch, v5 cleared the rival, all five Route 24 trainers, Misty, and reached the Rocket
thief at checkpoint 62. Drowzee's Sing counter decreased normally but the former single 48-pulse
allowance expired with one sleep turn remaining. The runtime now derives a finite total allowance
from the observed Gen I three-bit sleep counter, giving each represented turn the same transition
budget. Complete PP-vector preservation, monotonic countdown, live-HP, and menu-state checks remain
mandatory, so the change accommodates legitimate multi-turn sleep rather than weakening progress
evidence. This qualification attempt is also uncounted.

The sleep-scaled replay then cleared that failure and progressed through the S.S. Anne and the
capture/trade setup before all thirty Poké Balls were exhausted in the Forest collection lesson
after checkpoint 91. The semantic policy requested weakening to a health threshold, but the Red
adapter performed only one low-level attack before throwing; passive Metapod and Kakuna could
therefore consume five-ball attempts while still near full health. The adapter now replans after
every verified damage action. Passive cocoon targets use a 50% threshold under an eight-attack
maximum, Caterpie retains the lighter 85% lesson, and dangerous Pikachu remains a direct throw
behind the healthy lead. Exact PP loss, target damage, encounter identity, and all finite throw
bounds remain mandatory. This qualification attempt is uncounted as well.

The first deeper-weakening replay reached a passive Kakuna but then exposed MOVE again after a
completed hit. The one-action verifier had treated every non-MAIN phase as dialogue, so confirming
that stale move selection issued additional attacks and correctly violated the exact-one-PP-loss
contract. MOVE now receives CANCEL back to MAIN; only UNKNOWN dialogue receives bounded
confirmation. A subsequent attack can be selected only by the outer policy after it replans from
the newly observed HP ratio. This qualification attempt is private and uncounted.

The cancel-aware replay then observed an ordinary Tackle miss against Kakuna: exactly one PP was
spent, target HP remained 22/22, and stable MAIN returned. The verifier had no terminal miss state,
so it waited for damage until its finite settling bound expired. PP loss plus stable MAIN now proves
that the one selected turn completed; unchanged target HP classifies it as a miss. The adapter
restores the protected lead, flees, and asks the area policy for a fresh encounter without claiming
damage or capture progress. Regression cases separate hit, miss, and pending MOVE states. This
qualification attempt is also private and uncounted.

The miss-aware replay completed every Forest root, defeated Surge, and reached checkpoint 102, but
only five of the original thirty Poké Balls survived. Selling the four-ball surplus plus the Nugget
left ₽591 after protected healing and status supplies, so the four-Repel purchase failed closed.
The route does not reduce those downstream reserves. Pikachu is now a high-risk weaken-and-throw
target instead of a direct throw: only a low-level helper above 75% HP may participate, with the
verified forced-switch/flee contingency protecting the party. Ordinary targets use a 65% threshold
and passive Metapod/Kakuna use 30%, under the same exact PP/damage evidence and eight-attack bound.
This qualification attempt is private and uncounted.

That replay funded the complete Tunnel reserve, cleared Rock Tunnel, Rocket Hideout, and Pokémon
Tower, then reached checkpoint 172. The Snorlax restock bought 24 Great Balls, but the chained
product transition remained on Great Ball and bought a 25th instead of opening the two-Super-Potion
purchase. Even without that extra ball, the live ledger was ₽779 short. The route now sells unused
TM34 Bide for its exact ₽1,000 proceeds and reopens BUY from a verified field boundary between
product stacks. At Cinnabar, one Great Ball replaces Bide's unique capacity slot and is sold after
Blaine, preserving the full-bag delayed-TM38 lesson. The ledger accounts for the replacement's
₽1,300 net difference; the 24-Great-Ball plus retained-Poké-Ball capture depth and both recovery
items are unchanged. This qualification attempt is private and uncounted.

The Bide-funded replay then bought the intended reserve, caught Snorlax in five throws, completed
Safari, Koga, and Erika, and reached Saffron at checkpoint 239. Exact follow-up diagnostics proved
the bag had only fourteen occupied slots and the Helix Fossil was absent: capacity was already
safe, but the cleanup incorrectly required a fixed three-item checklist. The cleanup now proves
the actual sixteen-slot requirement first, performs no PC transaction when already safe, and
otherwise deposits only enough available obsolete route items to reach the bound. Unsupported
over-capacity states still fail closed. This qualification remains private and uncounted.

The next replay passed that boundary, liberated Silph, completed the Fighting Dojo, defeated
Sabrina, and reached the Mansion development block. It was stopped safely after 1,250 of the old
equal-level battles when the active curriculum changed; no declared slot opened. The next v5
candidate instead requires the exact six-species final-form roster, zero faints, and a level-75
Blastoise workhorse. Already-final non-workhorses are not forced to match its level. The reusable
planner can request recruitment, evolution, restoration, workhorse switching, or workhorse
training, while the older equal-level policy remains available for separate experiments. Its first
replay correctly rejected level-20 Diglett after Blastoise reached 75; the Red adapter now executes
a bounded, zero-faint, targeted Mansion lesson until Dugtrio is observed, without grinding the four
already-final non-workhorses.

That revised v5 qualification completed the entire game. The first counted v5 training root later
failed at the S.S. Anne rival with Ivysaur at 23/57 HP after Wartortle fainted. Decision snapshots
showed that Pidgeotto had reduced accuracy twice, Kadabra consumed the retained healing reserve,
and Mega Punch's lower accuracy prolonged the final matchup while Leech Seed restored Ivysaur.
Teaching the already-owned TM11 before boarding now replaces Mega Punch with BubbleBeam: the
teacher uses BubbleBeam against Pidgeotto and Raticate, Bite against Kadabra and Ivysaur, and keeps
Water Gun as a legal fallback. This changes no purchase budget or retry allowance. V5 remains
immutable; the repair belongs exclusively to v6.

The first v6 dry rehearsal learned BubbleBeam and reached the dock, but the dock checkpoint rejected
the otherwise-valid state because its inherited Cascade invariant still required the consumable
TM11 item to remain in the bag. The invariant now accepts either the unspent TM or observed
BubbleBeam in the lead's live moveset. This preserves proof of the lesson instead of confusing item
consumption with lost progress; the failed rehearsal was uncounted and v6 requires a fresh complete
qualification on the corrected exact source.
