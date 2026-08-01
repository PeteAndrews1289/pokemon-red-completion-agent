# Preregistered battle collection protocol

## Scope and current status

The public
[`red-battle-collection-v1.json`](../configs/red-battle-collection-v1.json)
registry freezes one prospective Pokémon Red teacher-collection campaign:

- 68 stable public battle-plan identities in exact qualified-route order;
- five `train`, two `validation`, and five `test` root-lineage slots;
- partition-local ordinals `1/5` through `5/5`, `1/2` through `2/2`, and `1/5`
  through `5/5`, in addition to global collection ordinals `1/12` through `12/12`; and
- one unique 68-offset timing schedule and one attempt for each slot.

As of the commit that introduces this protocol, the schedule dry run and all twelve declared
slots are unexecuted. The registry is a prospective plan, not an outcome or held-out result. It
contains no trajectory, ROM, snapshot, private path, or completion evidence.

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
| Registry bytes | `6337` |
| Registry SHA-256 | `42e73f255228a4e66013c6db5814faa4def34adadd3a0b30943bff25dab3dc69` |
| Source bundle SHA-256 | `c90b226ed8ff4d7961b9f240071e14507b6efd633cd6a74ba127f71c0f793e69` |
| Behavior configuration SHA-256 | `6b1ead4078541ca953ed432e90c175710d4c4f7a2b096f14ed9ed5cb6c71b39d` |
| Objective graph SHA-256 | `453ba1dcecbb33df9e10a911ac93090ff9a5080b07e02a5594e34a015e5bd3b6` |
| Teacher execution SHA-256 | `bfc318be3b1407c25a1f6f2cfc12405c481f3767825b9803cd745664b31bbe56` |
| Dry-run schedule SHA-256 | `4c33d545f61735f331e645d1e1e70bbfba1bc083e004c7b4748025258af33a98` |
| Slot `01` assignment ID | `d457a0a7299b1f8bf37baa03a4aee6868194d9d96ef8b9101fcfac0a1fbd8579` |

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
68-ID instrumentation path, but the fixed seed `9101` and its distinct schedule. Its metadata is
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
