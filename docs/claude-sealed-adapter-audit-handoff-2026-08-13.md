# External audit handoff: sealed catalog and cartridge adapter

## Audit boundary

Review the public implementation and non-test fixtures only. Do **not** locate, inventory, open,
hash, preflight, materialize or score any actual sealed-test capture. Do not create an owner
authorization receipt. The test remains 0/12, no actual case catalog exists, and no permission has
been granted to construct one from private capture bytes.

The exact prospective plan is schema v6, 12,914 bytes, SHA-256
`9df65487806d80b7d37e074c6f1ecf0ddf615e9853f7615e5681975e461ff440`. The execution source bundle
is `6dcf2e9237e5a5f1c52b87869cbb5eed5def8c8130520b6295ef0e0e48a422db`; deterministic teacher
execution is `7866f7627af0b56fa78553fb29c8d8d21bd33b278907bbf04dac546d9d27a0cd`.

## What was implemented

- `strategic_navigation_sealed_catalog.py` parses a canonical path-free twelve-row catalog and
  opens one exact capture only through a deterministic private layout after the executor's claim.
  The catalog contains digests and sizes, never paths, candidates, route costs, labels or outcomes.
- `strategic_navigation_sealed_adapter.py` converts available route bindings into an unlabeled,
  identity-free inference question, evaluates the exact frozen linear scorer and cheapest-route
  baseline, then executes the deterministic teacher only after the prediction commitment exists.
- `strategic_navigation_sealed_cartridge.py` authenticates the ROM, runtime, plan, catalog,
  scenario registry and source execution; loads the claimed capture in PyBoy; validates its source
  origin and exact objective frontier; relocates challenge cases to their declared origin with no
  label and zero objective delta; plans candidates there; and records the teacher trajectory from
  that declared origin.
- `emulator.py` can load verified state bytes directly, avoiding a path handoff at the private-input
  boundary.

Ten challenge cases deliberately have a different origin from the source scenario snapshot. The
first adapter draft incorrectly assumed those repositioned snapshots already existed. The repair is
now frozen as the fourth pre-access amendment: authenticate source origin and frontier, relocate
after claim, reject any objective delta, authenticate the declared origin, and only then plan model
candidates. Relocation emits no policy question or label.

## Adversarial targets

1. Mutate catalog canonicalization, exact row coverage, case order, case/scenario binding, ROM or
   runtime identity, execution configuration, source identity, state size/digest and envelope
   digest. Refusal must occur before any mismatched input can become a prediction.
2. Attack the opener with absolute paths, parent traversal, symlinks at every level, nonregular
   files, swapped envelope/state pairs, size races and post-open digest changes. Confirm no private
   path appears in public objects, receipts, exceptions or fixtures.
3. Move private access before durable claim, candidate planning before relocation, or source
   authentication after movement. Each mutation should be distinguishable without using the whole
   plan digest assertion as the sole oracle.
4. Remove the exact-frontier check before relocation or the zero-objective-delta check afterward.
   A changed frontier must close the emulator and candidate planning must remain uncalled.
5. Substitute the source scenario origin for the declared challenge origin in the recorded
   decision. Confirm the choice identity changes while the model-facing input remains free of map,
   objective and destination identity.
6. Forge the candidate-order nonce, weaken it to depend on only a case ID, or permute after scoring.
   It must be derived from the exact capture, scenario registry, source bundle, source commit and
   teacher execution, and model/baseline/teacher indices must all refer to the same order.
7. Inject a look-alike scorer, label-bearing example or preselected candidate. Production must
   require the exact linear model class and the inference object must have no teacher or outcome
   target.
8. Move teacher execution before the durable prediction record; allow unavailable candidates,
   model ties or baseline ties to disappear; or let `abort()` perform teacher work. Failures must be
   consumed under the frozen policy and a prepared session must close without acting.
9. Attack cleanup on every exception path, including relocation planning, route execution,
   frontier verification, declared-origin verification, candidate planning, prediction creation,
   commitment failure and teacher failure. Also verify that no save file or ROM-adjacent artifact is
   produced.
10. Check the catalog/bootstrap authority boundary. An authorization binds the catalog digest, but
    obtaining that digest requires read-only access to the private capture inventory. Recommend
    either a narrowly scoped inventory-only owner permission or a custodian-supplied canonical
    path-free manifest; do not silently treat evaluation authorization as retroactive permission.
11. Attack the readiness boundary. The owner receipt must bind both an external-audit receipt digest
    and an exact non-test adapter-qualification receipt digest, and runtime preflight must receive
    and recheck both before the start record exists. Try cloning loader-issued plans,
    authorizations, grants, catalogs, entries and inputs through `dataclasses.replace`; none should
    produce another accepted authority object. Also decide whether digest-bound owner attestation is
    sufficient or whether the next revision needs typed receipt parsers that authenticate verdict
    fields rather than only exact receipt bytes.

## Current evidence and stop line

The ROM-free qualification covers all 36 public non-test scenario shapes: 24 train and 12
validation, with candidate counts `{2: 17, 3: 16, 4: 2, 5: 1}`. Synthetic wiring proves relocation
precedes candidate planning and rejects objective drift. The current 124-test focused gate also
checks all-component symlink refusal, mandatory abort-before-start behavior, non-cloneable validated
objects and runtime receipt mismatch refusal. It does not prove that the exact adapter can relocate
every challenge on a live cartridge. That live qualification, the independent audit, publication
of the exact commit, green CI, a real path-free catalog and explicit owner authorization all remain
mandatory before case one.

Report findings even if they force another pre-access amendment. A clean review should say only
that the adapter is ready for the next gate, never that the model passed the sealed evaluation.
