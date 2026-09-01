# Red battle V2 seven-capture materialization freeze

Status: implemented locally; publication and green CI are required before invocation.

This gate converts the passed two-venue capacity census into one immutable private capture plan.
It does not create an encounter, choose a move, query a teacher, open an outcome, evaluate a model,
or claim a source root.

## Frozen denominator

The plan contains exactly seven independent catalog-authenticated train roots:

- five roots materialized in `pokemon_mansion_1f`;
- both independently available Lavender roots materialized at `route_11`; and
- zero replacement or contingency slots.

The freezer inventories the whole retained catalog bank. A caller cannot provide a selected root,
venue, lineage, partition, or party slot. Every assignment is rederived from the complete private
inventory whenever the plan is reopened.

## Prospective party selection

Every selected party member must be alive, have at least two moves with positive PP, and remain
within the battle experiment's maximum level gap for every measured encounter level in the venue,
including its rare ceiling. Selection then prefers species, party-slot, status, and level diversity,
followed by more usable moves and higher HP ratio. Source and slot identities break any remaining
tie deterministically.

These are input-quality facts only. Wild species, battle menus, prior scores, predictions, and
outcomes do not exist when the assignment is selected.

## Trust and recovery boundary

The private plan binds:

- the exact clean published source commit and source bundle;
- CPython/PyBoy runtime identity and the verified Red ROM;
- the historical catalog and registry provenance;
- every authenticated upstream source binding;
- the destination-directory digest and unique state/manifest filenames; and
- `retry_after_controller_input = false`.

All availability observations, deterministic selection, destination checks, and durable plan
publication happen under one shared claim-registry lease. The plan file is owner-only, exclusive,
filesystem-synced, and independently reopened before a path-free receipt is emitted. Any existing
planned output fails the freeze rather than becoming a silent resume or overwrite.

## Required next gate

After this implementation is published and CI is green, invoke the freezer once against the full
private bank. Inspect only its path-free receipt. A separate runner must then consume the exact
plan claim-first and may continue only never-started assignments after interruption. Capture
materialization still stops at the battle policy boundary with zero move choices and zero teacher
queries.

No outcome collection, model fitting, sealed Red evaluation, Crystal execution, authority
promotion, or full-game replay is authorized by this document.
