# T7 verified cache cleanup

Pete authorized removal of verified old useless material after the
[storage audit](2026-10-13-t7-storage-audit.md). Twenty-three generated cache
directories containing 11,345 files were removed. T7 Developer available space
increased by 661,827,584 bytes, about 631 MiB or 0.62 GiB, to 2.75 GiB.
The shared container's observed free-space increase was 661,811,200 bytes.
Small concurrent metadata and receipt writes make these observed deltas, not
a claim about isolated physical allocation.

## Removed material

| Group | Exact scope | Directories |
| --- | --- | ---: |
| Old Swift compiler products and indexes | ModuleCache, Modules, index, MyFitPlateCore.build, MyFitPlateCorePackageTests.build, MyFitPlateCoreTests.build, SwiftSoup.build and SwiftSoupProfile.build under both retained MyFitPlate SwiftPM debug output roots; MyFitPlateShared.build under the first root only | 17 |
| Compiler and SDK caches | CompilationCache.noindex and SDKStatCaches.noindex in the Final23Merge-AppTests build-data folder and FoodDetailRelease derived-data folder | 4 |
| Pokémon development-tool caches | Current Code .pytest_cache and .ruff_cache | 2 |

The private exact-path and identity receipt is on Pokémon Runs 2 under
PokemonRedCompletion/storage-cleanup-20261013/RECEIPT.json. Every target was checked
against its original device, inode and timestamp, with no symlink traversal or
source, dependency, model, save, coverage or test-result subtree admitted.
No active Swift build process was observed. Removal used no force flag.

These generated caches were permanently removed, not moved to Trash. They can be
regenerated from the retained source; bit-identical historical builds are not promised.
The documentation skill kept one concise cleanup record and an exact private receipt.

## Preserved material and verification

SourcePackages, dependency checkouts and repositories, original test binaries,
codecov profiles, QA and TestResults remain. The earlier 3.82 GiB build-related
folder estimate was not a deletable-cache total: much of it contains dependencies
and results. Entire build-data parents were therefore not removed.

Before and after removal, all 12,421 declared runtime, environment, protected-save,
context and model inputs passed byte-hash checks, reading 1,310,541,271 bytes in
each pass. The frozen package manifest and current state/context/model identities
match the retained handoff. This is file-integrity verification, not an emulator
or full test-suite run. Source code, models and old run evidence were not changed.

Two pre-deletion guards refused conservative false positives: transported
nanosecond timestamps lost integer precision, and a QA-named compiler-index hash
shard resembled a test-results directory. The original raw timestamps and the
exact generated shard location passed the final checks before any removal.

## Spotlight remains unchanged

Pete asked what Spotlight files are rather than approving the requested reset.
No Spotlight store, exclusion, indexing setting, backup or snapshot was changed.
These are macOS-generated search catalogs, not Pokémon training examples or saves.
Resetting the catalogs is separate from deleting original files, and search can
be incomplete during rebuilding; see [Apple's explanation](https://support.apple.com/en-gb/102321).

The large legacy journal is not declared junk merely because it is old or not
read during inference. It contains provenance and original failures. Larger
data cleanup requires identifying genuinely redundant copies or verifying a
lossless archive and its readers before removing any originals.

## Player and next decision

All cleanup workers are stopped. Gameplay remains stopped at 58 registrations
and four badges, with zero learning or registration delta during cleanup.
Silph and Sabrina remain unfinished; no save was loaded or emulator launched.

Next, resolve whether Pete wants private run-folder indexing exclusions and a
reset of only the Developer/Runs search stores. Leave Time Machine alone. Then
use the existing sealed reader for the bounded lossless archive pilot proposed
in the audit. Do not start a mass purge, new logger, model fit, game replay or
GitHub publication under this cleanup authorization.
