# Closed journal lossless packing pilot

Follow-up: the later [approved retirement](2026-10-13-journal-retirement.md)
removes the exact cold-file list and both verification copies. Original-retention
and zero-recovery statements below describe the pilot at its close, not the
subsequent approved cleanup.

The pilot passes: all 29,453 files in one closed readiness TRAIN journal restore
with identical bytes, names, private modes and nanosecond modification times.
All 14,720 sealed records produce identical existing-reader bytes and summaries.
The full archive occupies 3.18 MiB, versus 118.05 MiB of original file allocation.
Every original stays in place; actual space recovered in this pilot is zero.

After approval of the exact cold-record group and restoration workflow, its
estimated net saving is about **109.7 MiB** including retained archive and pilot
receipts. This is a one-journal allocation estimate, not whole-drive savings or
a measured physical reclaim. Current gameplay and model identities are unchanged.

## Work order

The allowance is two hours from 17:28:40 UTC on October 13, 2026, ending at
19:28:40 UTC. Reassess at 17:58:40 UTC and after 15 stalled minutes or two equivalent
failures. A completed useful pilot may finish sooner.

1. Record the source census, hashes, private modes and current protected pins.
2. Pack exact file bytes and relative names into an authenticated compressed
   archive; preserve source locks and reject a changing or active journal.
3. Restore into a new private root. Compare every file and directory, then open
   the records and reconstruct TRAIN rows using the existing readers.
4. Test corrupted, truncated and unsafe archives, interruption retention,
   permissions and no-overwrite behavior on ROM-free fixtures.
5. Measure original, archive and restored allocation; list precisely which
   originals remain hot dependencies and which could be retired after approval.

## Mission check

- Reusable capability: retain training and failure evidence compactly so ongoing
  Red development does not exhaust the run volumes.
- Authority: storage mechanics only; model decisions and parameters do not change.
- Reuse check: exact restoration through the unchanged sealed store and TRAIN
  readers; a copied root is not an independent training or evaluation origin.
- Cheapest falsifier: any changed payload, manifest, mode, loss, partition,
  training row or existing-reader result fails the pilot.
- Time box: two hours, with a 30-minute reassessment.
- Stop condition: preservation failure, source writers, insufficient storage,
  missing dependencies, deadline or a proposed live archive-reader subsystem.

## Verified results

The archive contains 44,174 filesystem entries and 9,086,320 file-content bytes.
Its compressed content is 3,334,180 bytes and final allocated size 3,338,240 bytes.
Original files occupy 123,781,120 allocated bytes. About 97.3% of that file
allocation can be replaced by the archive before accounting for retained hot
metadata and external receipts. Directory/APFS metadata and shared clone extents
are not independently measured; no whole-archive migration is claimed.

The existing model codec loads identical parameters and all 161 retained-row
bindings. The existing native curriculum loader reconstructs all 12 local outcomes
identically; the original corpus's 10 admitted lessons remain admitted and its
two excluded outcomes remain outside that corpus. No fit or gameplay occurs.
Historical lesson sources outside this journal remain unchanged and were not
repacked or independently reconstructed here.

A second check forbids every proposed cold record ID while reading the restored
root. All 12 local lesson reconstructions and the current model/corpus binding
checks still pass, with zero cold lookups in 26 metadata-reader requests. Full
action/trace audits and future readers requiring those inputs must restore the
archive first. Existing live readers do not read compressed archives directly.

All 12,421 current package, environment and protected files matched their expected
hashes before and after. The original journal's complete census remained equal.
The archives live on a different APFS volume of the same physical external drive,
so they are not independent drive-failure protection.

**146 targeted ROM-free tests pass**, including the existing sealed store, native
curriculum and collection-teacher readers. Archive tests cover exact restoration,
private modes, modification times, failed/interrupted/invalid record preservation,
active collections and typed writers, source mutation, destination collisions,
truncation, tampering, links, path escape, inventory bounds and undeclared content.
This is not a full-suite or hosted-CI result.

The final safety pass found nonzero data hidden in buffered tar end padding was
not rejected. The utility now validates the complete buffered tail and gzip
footer; the new rejection test passes and a second complete native-journal restore
passes through the corrected utility. No source record or training reader changed.
The pilot's model-comparison check was also corrected to compare serialized
weights, hashes and row bindings rather than ambiguous NumPy array equality.

## Exact removal decision

No originals were removed. The private retirement inventory enumerates every
candidate's exact path, kind, bytes, hash, mode and modification time.

| Group | Records | Files | Decision |
| --- | ---: | ---: | --- |
| Native action records | 7,336 | 14,672 | Conditional archive retirement only. |
| Native trace records | 7,336 | 14,672 | Conditional archive retirement only. |
| Native player diagnostics | 8 | 16 | Conditional archive retirement only. |
| Models, corpora, plans, outcomes and attempts | 40 | 80 | Keep originals at their current paths. |
| Root sentinel and collection locks | Not records | 13 | Keep originals. |

The 14,680 cold directories contain 29,360 files with 120,258,560 allocated bytes,
no shared hardlinks and no matches against current/protected or original-package
file pins. About 4.95 MiB of archive and pilot receipts is retained, leaving the
109.7 MiB net estimate. These 40 kept directories include both models and corpora,
all 12 plans, all 12 outcomes and all 12 attempt records. Saves and external
training dependencies are outside the retirement group.

Two generated restored test trees are independently byte-verified duplicates and
are disposable after the pilot stops while the original and archive remain.
Each uses 118.05 MiB of file allocation. Removing them would reclaim pilot-created
copies, not count as old-run savings. They remain intact pending cleanup approval.

## Closeout and next work

All workers are stopped. The pilot finished within its two-hour allowance; the
30-minute reassessment retained the narrow work order and reused verified stages.
No data deletion, fit, emulator input, save change, publication, frozen-manifest
rewrite or live logging/reader backend was introduced. The player remains stopped
at 58/124 registrations and four badges, with zero learning/registration delta.

Before retiring any originals, approve the exact inventory, recheck its archive
and source fingerprints, and document restoration-before-read for full trace
audits or future training consumers. Use the existing offline utility and sealed
readers. Do not erase the whole journal or relabel restored copies as new origins.
Then measure the actual space gain rather than treating this estimate as observed.

Allow up to one hour for that narrowly scoped retirement and restore rehearsal,
reassessing after 20 minutes. Stop for a new dependency, integrity difference or
need for a live archive backend. Packing larger journals requires a separately
explained bounded-chunk approach; the current utility intentionally rejects more
than 100,000 filesystem entries. Do not launch a whole-drive migration or further
archive work merely to fill time. Return to the existing Silph work order when
Pete chooses gameplay again.

For the next storage step I recommend 6.1 Sol High, normal speed, with Fast off.
That is a task judgment, not a settings change; [official model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
lists the supported efforts. The exact receipts and removal inventory remain
private; this report follows the project's concise session-record format.
