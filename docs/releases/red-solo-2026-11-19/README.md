# November 19 solo player repair

Four same-seed campaigns and their solo follow-up reached the same cartridge state when the last Pokémon fainted from poison during a walk to heal. Red could carry out its normal blackout sequence. The runner stopped before handing control back to the game. [Incident and replay results](../../work-sessions/solo-field-blackout-2026-11-19.md)

The source patch shows the exact changes to the two functions responsible for that handoff. It checks the failed healing route, the held cartridge state and the recovery action the game offers. Red deducts the money and restores the party. The model chooses the next goal. [Read the source change](field-blackout.patch)

Applying this patch to the two recorded parent files reproduced both repaired source files byte for byte. The fingerprint records the before and after SHA-256 values, the patch digest and both full build identifiers. It identifies the private emulator build used for the replays. The public download covers this repair. [Build and file fingerprints](repair-fingerprint.json)

Two native copies exercised the transition. The first reproduced the failure from before the faint. The second started at the stopped state. The live save subsequently paid ₽633 and the model chose to advance the story. The run records one external continuation at this point. [Interview handoff](../../ai-systems-specialist-interview-handoff.md) · [Four completed campaigns](../../work-sessions/four-run-splits-2026-11-19.md)
