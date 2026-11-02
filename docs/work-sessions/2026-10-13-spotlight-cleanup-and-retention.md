# Spotlight cleanup and older Pokémon file retention

Resetting the two approved Spotlight indexes recovered a measured **53.92 GB
(50.22 GiB)** across T7 Developer and Pokémon Runs at 17:19:43 UTC on October 13,
2026. Private output folders are excluded, and indexing is enabled again. The
smaller search catalogs are rebuilding; their subsequent growth can reduce the
net recovery. No Pokémon source, save, model, training record, run result or
backup was deleted.

## Index exclusions and reset

Search Privacy now excludes the private PokemonRedCompletion folder on Developer,
Runs and Runs 2, plus all 93 older PokemonRedCompletion version output folders on
Developer. Those 96 folder exclusions were verified against the stored settings.
Neither volume retains a whole-volume exclusion. Current/Code and public
documentation remain eligible for indexing; completed search coverage has not
yet been established.

Each approved volume was temporarily added to Search Privacy and then removed,
retaining its folder exclusions. The cleared index roots measured 12 KiB on
Developer and 8 KiB on Runs before rebuilding. Indexing was explicitly re-enabled
on those two volumes; all four volumes subsequently reported indexing enabled.
This follows [Apple's documented reset procedure](https://support.apple.com/en-gb/102321)
and [folder exclusion controls](https://support.apple.com/en-gb/guide/mac-help/mchl1bb43b84/mac).
The backup volume and its index were not reset. No permissions, volume quotas,
partitions, encryption or backup settings changed.

## Measured space recovery

| Volume | Available before | Available after | Net recovered |
| --- | ---: | ---: | ---: |
| T7 Developer | 2.75 GiB | 45.57 GiB | 42.83 GiB |
| Pokémon Runs | 1.29 GiB | 8.68 GiB | 7.39 GiB |

The target volumes' used-space reduction was 53,919,326,208 bytes. Shared APFS
container free space rose by 53,919,322,112 bytes; a 4 KiB settings write on Runs 2
accounts for the small difference. Do not add independent volume headroom to
estimate physical capacity. The backup volume's used-space reading was unchanged.

The earlier 66.46 GiB index figure was an allocated-file total, not a guaranteed
net recovery measurement. This record reports the actual filesystem change and
does not attribute the entire difference to a particular APFS mechanism. The
[earlier cache cleanup](2026-10-13-t7-safe-cache-cleanup.md) separately recovered
631 MiB and is not included in these reset totals.

## What older Pokémon material can be deleted

Only **1,712,128 allocated bytes, or 1.63 MiB**, were newly qualified as disposable:
the old step2 Python bytecode cache. It contains 55 .pyc files, all 55 corresponding
source files still exist, and none of the cache files is a current package,
environment or protected-plan pin. This cache was identified, not deleted.

| Older material | Measured allocation | Retention decision |
| --- | ---: | --- |
| 93 version output folders | 14.20 GiB | Do not erase wholesale; they contain historical experiments and model records. |
| PokemonRedAI | 3.51 GiB | Retain pending dependency and content review; includes datasets and older tools. |
| Archived worktrees | 0.70 GiB | Retain verified recovery archives; redundant working copies were already removed. |
| Recovery folder | About 0.26 GiB | Retain source and Git recovery material. |
| CodexSessionArchive | 5.43 GiB | Retain unique chat and project history. |

The shallow inventory of the 93 version folders found no immediate src, scripts,
tests, Git or environment directories. Their 638 immediate entries include 216
failed partials, 23 model-named records, 21 teacher records, 43 outcomes, 41
diagnostics, 49 dry-run records, 24 seals and 221 other entries. These are
name-based classifications, not validation of their training eligibility. They
are primarily old outputs, not 93 duplicate code checkouts.

Failed or superseded does not mean byte-for-byte redundant. Original losses and
interrupted attempts still have diagnostic value, and some historical evidence
is used by training-provenance readers. The worktree recovery records show that
87 redundant clean working copies were already retired in September; their
remaining compressed archives preserve the non-cache content and recovery refs.

The largest remaining opportunity is lossless packing, not an unqualified purge.
The [storage audit](2026-10-13-t7-storage-audit.md) demonstrated 97.3% reduction in
one 2,000-file journal sample versus allocated file bytes, and 89.3% compression
of one large isolation report. Those are sample results, not a whole-drive
recovery estimate. Current readers require individual sealed directories and
frozen packages pin literal paths. No multi-GiB old-run deletion group has yet
been qualified under the requirement to leave training data and saves untouched.

## Protection and next decision

Before and after the reset, all 12,421 current package, environment and protected
files matched their recorded hashes, covering 1,310,541,271 bytes per pass. The
backup's Spotlight configuration hash and both Time Machine snapshot identities
were unchanged. Exact paths, exclusions and capacity readings are retained in
the private storage-cleanup receipt, not public source.

The player remains stopped at 58/124 registrations and four badges. This storage
work adds zero registrations and zero parameter-learning updates. Documentation
and product-focus checks apply to this record; this is not gameplay qualification.

The next useful storage session is a two-hour lossless archive pilot, with a
30-minute reassessment. Reuse the sealed store and existing readers on one closed
segment. Preserve and restore exact record and manifest bytes, original costs,
partitions, interrupted attempts and hashes; test truncation and tampering.
Accept only equivalent reader results and a measured footprint reduction. Do
not delete originals, fit models, replay the game or rewrite frozen manifests.
Explain any broader reader or storage architecture before expanding the work.
The pilot requires the user's next work decision; it did not run in this cleanup.

My implementation recommendation is 6.1 Sol High, with Fast off for this
filesystem-heavy work. That is a task judgment, not a settings change;
[official model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
lists its supported reasoning efforts.
