# Pokémon run retention audit

This is the pre-approval audit. The subsequently approved
[578-file retirement](2026-10-15-run-retirement.md) is complete and recovered
17.5087 GiB of observed net physical space; the original audit findings follow.

Pete chose identifying older run data for cleanup instead of adding another volume.
The recommended first batch is **578 exact files**, not entire run directories.
Their 19.04 GiB allocation compresses to 1.46 GiB in full in-memory byte/hash
round trips, projecting **about 17.6 GiB** of file-allocation savings after verified
archival retirement. No archive has been saved and no original has been deleted.

The private packet `red-run-retention-audit-20261015-v1` on T7 Developer contains
the readable report, exact paths, hashes and restoration/preflight metadata in
`DELETION-PROPOSAL.json`. Proposal SHA-256:
`f269bcb084011671ae1bf23c7756ee4473cc4484c785f9136e4e8f80652db46f`.
The [path-free evidence](../evidence/red-run-retention-audit-2026-10-15.json) records
the totals and limitations. [HANDOFF.md](../../HANDOFF.md) owns next work.

## First batch

| Target | Files | Existing allocation | Compressed payload |
| --- | ---: | ---: | ---: |
| Manifest-listed executions and snapshots in 93 legacy version trees | 560 | 13.82 GiB | 0.83 GiB |
| Isolation reports from stopped October 11–12 fresh runs | 18 | 5.22 GiB | 0.63 GiB |
| Total | 578 | 19.04 GiB | 1.46 GiB |

T7 Developer holds 565 files, with about13.30GiB projected saving; Pokémon Runs
holds13, with about4.28GiB. Runs2 and the backup volume have no first-batch files.
The578files have zero current pin matches. Full gzip decompression reconstructs
every byte/hash. Modes/mtime and original identities are in the candidate catalog;
ctime/inode are preflight fingerprints, not a promise to restore filesystem identity.

There are59hash-identical replay copies/1.38GiB within the560, not extra savings.
The broad616file compression survey is not a deletion list:38training/control
fixtures, audited targets, diagnostics and outcomes were excluded after review.
Keep legacy models, labels, corrections, metrics and all other non-whitelisted files.
Current pin absence alone is not a proof that historical readers never need a file.

## Larger archive opportunities

| Volume | Proposed later scope | Allocation basis |
| --- | --- | --- |
| Pokémon Runs | Action/trace classes in six old failed fresh journals |35.85GiB estimated from4,699,482 completely counted record names and sampled8KiB allocation. |
| Pokémon Runs2 | Silph/Sabrina, Giovanni and Koga/Fly story journals only |7.81GiB estimated from native meters/samples; full inventory still needed. |
| T7 Developer | Legacy goal-manager action/trace classes, never the whole mixed store |70.4GiB estimated from the prior complete October13name census; not a fresh payload/block census. |
| T7 | Time Machine backup contents |Not a cleanup target; no active output folder at the root. |

The six Runs targets are October12v5,v3,v2,v1 and October11v11,v10. Each is stopped
DEVELOPMENT,fit_allowed=false,0recorded fits/training and0current journal pin matches.
Their final saves, failure/outcome/cost/context and diagnostic records stay. The v3
journal contains a tail beyond the outer result; do not discard unexported failure
evidence. Existing100,000-entry archive limits prohibit an unplanned whole-store
packing invocation. Qualify a bounded plan before this separate retirement batch.

The93legacy roots total14.20GiB, but contain valuable models and labels. Whole-folder
deletion is not cleared. Current source families and the completed124reference/
all recent frozen attempts remain protected.12,701package/environment/protected
pins verify, including the unchanged161example goal-model record.

## Coverage and limits

All four volumes were checked for current identity/capacity/root role; the three
data volumes list no snapshots.90journal roots were inventoried, with complete
name censuses for six large candidates.93legacy trees were enumerated and560raw
files rehashed against their manifests.616complete plain-file gzip round trips
were measured, then narrowed to the final578file whitelist. Broad allocation walks
were stopped at the fifteen-minute reassessment; partial emitted folder sizes are
labeled partial, not extrapolated into a complete whole-drive total.

APFS clone sharing and metadata are not resolved unique physical savings. Measure
settled free space after authorized cleanup. The earlier Spotlight cleanup remains
effective; ongoing growth is mainly per-input records and verbose reports. No
backup, source, save, model, training payload or old run content was modified.
Only new audit artifacts and current documentation were written.

## Next execution contract

Outcome: recover space without losing model inputs, failed outcomes or future
raw-data restoration. Authority stays with the same local models; no teaching or
gameplay. Reuse normal gzip, current pins and existing readers. Cheapest falsifier
is a hot-pin match, changed source hash, failed exact restoration or unknown reader.
After explicit578file approval, save/verify durable archives and restoration catalog,
retire only exact listed originals and measure actual recovery. Allow up to2hours;
reassess15stalled minutes/two equivalent failures. Stop for wider scope or integrity
failure. No new volume, live writer/storage backend, replay, refit or publication.

The frozen-run goal remains blocked and its monitor paused. Completed/failed saves
and accepted candidate stay intact. Learning, authority, transfer and registration
deltas are0; actual recovered space is0. For the cleanup task, recommend6.1SolHigh,
normal speed/Fastoff; no setting change is claimed.
