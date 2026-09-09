# Shared registration foundation — September 9, 2026

## Mission check

- Capability: persistent cross-run Pokédex memory and registration-first capture/evolution demand.
- Learned authority: unchanged; maintenance unblocks `red-shared-registration-learning-v1`.
- Transfer test: overlapping synthetic Red/Blue observations and a known base serving a new branch.
- Cheapest falsifier: one evolved specimen retains all prior registrations; a duplicate adds no credit.
- Time box: one focused implementation session, then review before gameplay migration.
- Stop condition: fabricated local flags, stale inventory joins, lost registrations, rewritten old
  rewards, or an executor still using living-form safeguards under a new reward label.

## Delivered

`registration_memory.py` provides a private SQLite store, explicit observation-to-National-ID
mapping, idempotent transactional recording, frozen snapshots and readable JSON export. It keeps
global historical registrations separate from each run's latest flags and physical specimen counts.
Out-of-order imports do not replace newer local state. A restored earlier save does not erase
global historical credit. A registration record identifies an observation, not an inferred capture
method. Callers must authenticate actual checkpoint observations; digest syntax is not that proof.

`registered_collection.py` provides a separately versioned registration-only completion report,
checkpoint-bound semantic inventory bridge and new-registration projection. This does not assert
story completion or define the entire training reward. Frozen initial memory distinguishes
inherited achievements from new registrations.

The new capture-demand function models one physical specimen following one directed transformation
path, earning every missing registration along it. Separate branches can require additional
specimens. Explicit reserves protect story/trade dependencies; no automatic reserve is added just
to preserve every living form. Candidate demands are alternatives, not a combined shopping list.

The existing Red evolution inventory now has an explicit registered mode: globally credited targets
are skipped and a single unreserved precursor suffices. Its legacy default and the live executor's
two-copy requirement are intentionally unchanged until prospective runtime integration.

## Verification and self-review

237 targeted tests passed across new memory/demand/integration modules and existing Pokédex,
collection, planning, evolution and runtime tests. Four changed/new source modules passed targeted
typing. Lint passed. Capture demand was compared with independently enumerated specimen paths for
64 four-node DAGs at three initial stock quantities each. SQLite tests cover concurrent imports,
duplicate credit, conflicting identities, invalid mappings, stale inventory joins, corrupted
payload/index records, and an abrupt child-process exit during an uncommitted write.

These are engineering tests, not learning results or a test of actual power-loss hardware. Digests
detect the tested corruption, not arbitrary malicious replacement of a database and all evidence.
No ROM, saved game, production ledger import, controller action, fit, sealed evaluation or Crystal
execution occurred. Native114 and all historical reward/contract evidence remain unchanged.
No external-agent audit or external-model usage occurred this session.

## Next session — live integration, not more general architecture

1. Bind registered V1 and a frozen initial ledger identity to new checkpoint/runtime records.
2. Connect the existing acquisition menu to registered demand while retaining location, resource
   and executor qualifications. Expose real alternatives, not a hard-coded next Pokémon.
3. Migrate native evolution verification from mandatory source coexistence to exact expected
   specimen transformation and explicit story/HM/branch protection.
4. Version reward admission; assess compatibility of the 114 old-objective examples explicitly.
5. Import the authenticated current Red endpoint without advancing the game; then run one bounded
   collection lesson only after all consumers agree on the objective.

Do not replay a consumed trial or change its old reward. Do not start a full-game run. The memory
milestone is 1/3 of the new integration checklist; this is not a Phase 5 completion percentage.

[Path-free qualification](../evidence/shared-registration-foundation-2026-09-09.json)
