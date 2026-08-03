# Preregistered battle collection protocol

## Scope and current status

The public
[`red-battle-collection-v4.json`](../configs/red-battle-collection-v4.json)
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

The current v4 registry has twelve fresh, previously unexecuted counted seeds. Its uncounted dry
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
now buys a completion-oriented twenty-five-Great-Ball reserve with a thirty-three-throw total bound and sells
the remainder after capture. The static encounter no longer depends on leftovers from earlier
species searches.
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
| Registry SHA-256 | `ffa40fa35addfa549b746f47d4899a5c82ea3d4b1ddb17bd93caa15b61085c8e` |
| Source bundle SHA-256 | `5c593db23e67e59270e94d12ae3664c1444fe0cbc52483d6042727d171093f40` |
| Behavior configuration SHA-256 | `6b1ead4078541ca953ed432e90c175710d4c4f7a2b096f14ed9ed5cb6c71b39d` |
| Objective graph SHA-256 | `453ba1dcecbb33df9e10a911ac93090ff9a5080b07e02a5594e34a015e5bd3b6` |
| Teacher execution SHA-256 | `ba01be0ae945294bde21c5b7c9371179ea584979839cc0d216b38c3eb7d6cd73` |
| Dry-run schedule SHA-256 | `b8ad2a192c4b41598fd55fa4c07839960932ce298175a276642db1436c1cb95f` |
| Slot `01` assignment ID | `878a412fe1e9e5986742c498524c6d7044129332d82145f8cde7de66fc4befec` |

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
