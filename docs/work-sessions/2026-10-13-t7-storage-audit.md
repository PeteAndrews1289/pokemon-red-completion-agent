# T7 storage audit and lean logging proposal

The storage problem is substantially a recording and indexing problem, not the
size of the active learned model. The legacy goal journal contains 9,512,692
entries; 97.1% have action or trace identifiers. Spotlight indexes show another
71.15 GiB of allocated files across the three established volumes. The recommended sequence is
targeted indexing exclusions, a lossless archive pilot, then removal of redundant
report embedding and a compatible compact journal representation.

This is an audit and proposal, not cleanup or implementation approval. No existing
data was deleted, moved, compressed in place or changed. No indexing settings,
quotas, backups, player source, model parameters or game progress changed. The
documentation skill was used to keep the findings in one concise session record.

## All four volumes

There is one external physical T7 disk with four mounted APFS volumes. Capacity
figures below are rounded filesystem observations, not independently available
space on four physical disks.

| Volume | Used | Reported available | Main finding |
| --- | ---: | ---: | --- |
| T7 Developer | 277 GiB | 2.1 GiB | Legacy Pokémon journals and a 55.94 GiB Spotlight index; 300 GB quota. |
| T7 | 110 GiB | 313 GiB | Time Machine backup volume, two snapshots and a 4.69 GiB index; 454 GB quota. |
| Pokémon Runs | 138 GiB | 1.3 GiB | Recent run outputs, a 10.52 GiB index and 0.70 GiB of filesystem-event logs; 150 GB quota. |
| Pokémon Runs 2 | Less than 2 MiB | About 47 GiB | Newly created overflow, no gameplay outputs yet; 50 GB quota. |

The shared container reports about 135.2 GB, or 126 GiB, unallocated. Do not add
the available column to estimate physical free space. No further volume or quota
change is proposed.

Directory sizes are allocated-file totals. Hardlinks within one traversal are
counted once, but shared APFS clone extents are not independently resolved, and
snapshots or filesystem metadata are not included in ordinary folder totals.
These figures are not guaranteed unique physical bytes or reclaimable space.

Other measured Developer folders are MyFitPlate at 23.97 GiB, 93 older
PokemonRedCompletion version directories at 14.20 GiB, CodexSessionArchive at
5.43 GiB and PokemonRedAI at 3.51 GiB. The organized Pokemon Project tree is
1.16 GiB, including its retained worktree and recovery archives. Its active Code
and Experiments folders together occupy about 201 MiB. Documentation cleanup is
not the main space lever.

Build-related MyFitPlate directories occupy about 3.82 GiB, excluding the
separate SwiftPM checkouts and repositories. They are candidates for a separate
cache review, not a qualified deletion list: embedded logs and test evidence must
be distinguished from rebuildable products. Source, dependency checkouts, QA,
TestResults, release artifacts and chat history remain protected.

## Why the logs grow

### Individual files for each input

The existing [action recorder](../../src/pokemon_red_completion/red_player_lesson_runtime.py)
publishes an action record before each controller macro and a trace afterward.
The [sealed store](../../src/pokemon_red_completion/private_artifacts.py) puts each
record in a separate directory containing record.json and manifest.json. One
macro therefore normally creates four files and two directories, before other
diagnostics and snapshots.

In Developer/PokemonRedCompletion/goal-manager-v1, the complete immediate-entry
census finds 4,616,832 action identifiers, 4,616,827 trace identifiers and 274,420
diagnostic identifiers. Sampled action/trace payloads are around 71–84 bytes.
The five-count action/trace difference was not diagnosed; preserve incomplete
attempts exactly rather than filling missing records or inventing completion.
These counts are identifiers, not an exhaustive validation of every record.

The recent red-fresh-autonomous-run-20261011-v11 journal separately contains
375,341 action and 375,341 trace identifiers, plus 56,545 diagnostic identifiers.
The latest candidate continuation contains 22,138 of each and 5,423 diagnostics.
This layout multiplies filesystem allocation and metadata operations. Its share
of Spotlight growth was not measured independently.

### Repeated combined reports

In the latest candidate continuation, DRIVER-RESULT-001.json and segment
RESULT.json each contain the same complete episode as native/episode/result.json.
Their contents compare equal at the episode level. Together these three files
occupy 145.60 MiB of content; the native episode alone is 46.90 MiB. Driver metadata
still differs and must be retained, but it does not require another full episode.

The [native player](../../src/pokemon_red_completion/red_native_player.py) also
writes the entire diagnostic event list to diagnostic-events.json after publishing
the events individually. That combined file is 46.44 MiB in the same continuation.
These are redundant representations, not separate new training lessons.

The [frozen launcher](../../scripts/launch_frozen_red_player.py) stores complete
absolute read/write path lists. One ISOLATED-IO.json is 558.80 MiB. This is isolation
evidence, not fitting data; retain it losslessly, using compact path representation
or compression rather than deleting the access history.

### Large search indexes

Spotlight stores measure 55.94 GiB on Developer, 10.52 GiB on Runs and 4.69 GiB
on the backup volume. Developer and Runs report read-only indexes; their saved
configurations contain no folder exclusions. Overflow indexing is enabled and
also has no exclusions. Read-only index status is not proof of a privacy exclusion.

Propose excluding the private PokemonRedCompletion output folders on Developer,
Runs and Overflow from Spotlight, keeping Current/Code and public documentation
searchable. Use supported macOS settings, then measure the change; if an existing
index remains large, evaluate a supported rebuild while retaining the exclusions.
Do not manually erase .Spotlight-V100 or promise its entire size will be recovered.
[Apple documents folder exclusions and explains why Time Machine indexing must remain](https://support.apple.com/en-gb/guide/mac-help/mchl1bb43b84/26/mac/26).
The backup volume, its index and its two snapshots are outside this cleanup proposal.

## Lossless measurements

Compression tests ran entirely in memory. No archive was written and no original
was replaced. Every sampled file round-tripped byte-for-byte, including manifests.

| Sample | Existing size | Compressed size | Reduction |
| --- | ---: | ---: | ---: |
| 1,000 sealed record directories, 2,000 files | 8.125 MiB allocated; 0.785 MiB content | 222.8 KiB | 97.3% versus file allocation |
| Frozen launch isolation report | 558.80 MiB content | 59.97 MiB | 89.3% |
| Current terminal save | 167,677 bytes | 8,879 bytes | 94.7% |

The record sample is the first 1,000 directories in filesystem enumeration from
one closed continuation, not a random or whole-volume sample. Directory metadata,
future archive indexes and the compressed file's own allocation are excluded from
that reduction. This is a promising packing measurement, not an implemented
reader or a guarantee of equivalent whole-drive savings.

The save hash remains the retained actual 58-entry checkpoint. No emulator was
launched or save loaded. The active goal-model record is approximately 69 KiB.

## Apparent duplication that is already shared

The latest capture-switch-package-v1, v2 and v3 each expose the same 6,941
historical input files. All are hardlinked. Their 20,823 path references resolve
to 6,941 unique file inodes with a 1.034 GiB allocated-file total, not three
independent 1.034 GiB totals. Deleting package views would not reclaim three complete copies.
This metadata check did not rehash all input content.

Keep verified immutable input sharing within a volume. Hardlinks do not provide
cross-volume sharing; future Overflow packages must not blindly copy the entire
historical data tree or assume that the existing linking recipe works there.
Keep current pins and manifests unchanged.

## Proposed logging setup

1. **One authoritative copy, compact views.** Store complete decisions, candidate
   features and scores, outcomes, diagnostics and costs once. Driver and episode
   summaries reference the authoritative records with hashes instead of embedding
   their complete arrays. Full human-readable reports remain regenerable.
2. **Keep all action and trace evidence, pack closed chunks.** Extend the existing
   sealed-store interface with bounded, indexed, lossless chunks. Preserve original
   IDs, kinds, record and manifest bytes, order and hashes. Initially leave the live
   writer unchanged and qualify closed-chunk reading; do not build another logger.
3. **Preserve interruption durability.** Any later live compact writer must make
   the pre-input action durable before controller input and retain the separate
   post-input result. No delayed batch that hides an interrupted or failed macro.
4. **Compress and share identical artifacts.** Large path lists, closed snapshots
   and immutable repeated payloads may use lossless compression or hash references.
   Distinct run occurrences, partitions, original costs and identities remain
   distinct even when their bytes can be shared.
5. **Keep hot dependencies accessible.** Current continuation, protected saves,
   baseline/candidate models, all admitted TRAIN provenance and active frozen inputs
   remain directly readable until compatibility is proven. Archive closed historical
   runs losslessly; do not discard unique failures or relabel DEVELOPMENT as TRAIN.
6. **Measure growth with existing cost reports.** Add bytes and file counts per
   1,000 actions and per segment to the existing reporting surface. A storage
   warning should retain a safe checkpoint, not discard diagnostics or invent a
   gameplay success. Avoid another monitoring or data-collection framework.

The present sealed reader requires literal two-file record directories and checks
their permissions, bytes and hashes. Collection-lesson admission, challenge
consequences and sequence auditing request individual action/trace IDs. Frozen
packages also pin literal file inputs. Packing is therefore not a drop-in file
replacement: qualify compatible lookup and declared archive inputs, or verified
restoration, before retiring any originals. Never edit an old frozen manifest.

## Next session after approval

The outcome is bounded storage growth with unchanged player decisions and usable
training/failure evidence. Start with the indexing exclusion proposal, then one
closed-segment archive pilot through the existing sealed store, without deletion.
Reuse its hashes and readers plus the current lesson, consequence and recovery
checks. Include successful TRAIN, an ordinary loss and an interrupted attempt;
preserve invalid or censored evidence as invalid or censored.

Accept only exact payload/manifest restoration, equivalent reader results, unchanged
costs and partitions, rejection of tampering/truncation/path escape, and a measured
footprint reduction. No model fit or game replay is needed to test the storage
codec. Allow two hours for the compatibility pilot, reassessing after 30 minutes
if the existing reader cannot be adapted narrowly. Explain any broader storage
architecture before proceeding. Whole-archive migration is a separate measured
job, not part of this first pilot. No cleanup or source change is authorized here.

## Coverage and current player

All four volumes were checked for identity, capacity, quotas, snapshots, root
folders and indexing. Readable non-main Developer folders and system-log folders
were sized; protected backup/system paths denied some reads. Huge per-family
allocation walks were stopped after a partial pass, rather than spend hours
stating every tiny file. The legacy store and two example journals received
complete immediate-entry censuses. A full byte-hash duplicate census and exact
whole-archive reclaimable-space total are not claimed.

This audit changes no model or registration count. The actual player remains
stopped at 58/124 registrations and four badges; Silph and Sabrina remain unfinished.
The immediate recommendation is to approve a small lossless storage pilot and
targeted indexing exclusions, not erase historical runs. For implementation,
6.1 Sol High is my recommendation; Max is reasonable for the crash/recovery review.
Fast is optional and will not shorten the filesystem scan itself. These are task
judgments, not a setting change; [official model controls](https://learn.chatgpt.com/docs/models#gpt-61-sol)
describe the available options.
