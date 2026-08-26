# Red living-Dex exhaustive inventory V3

Status: ROM-free implementation under qualification. No V3 protected read is authorized by this
document. The generated [active product state](../ACTIVE_PRODUCT_STATE.md) remains authoritative.

## Why this exists

The sole V2 census authenticated 81 private Red inputs and then stopped at `state_observation` on
the twelfth considered context. One earlier root was consumed, and ten readable contexts each had
fewer than three mapped options. Because V2 terminated on the first context-local exception, it
never projected a scenario or evaluated the unchanged 8-train plus 4-development gate.

V3 answers one narrower question: **can the complete authenticated bank be counted safely enough
to decide whether it contains the honest multi-option curriculum?** It does not collect an
outcome, train a model, grant gameplay authority, evaluate Red, run Crystal, or replay the game.

## Context-local versus global

| Context-local anonymous exclusion | Global fail-closed terminal |
| --- | --- |
| Unsupported partition | Argument, source, or private-input authentication |
| Consumed physical root | Runtime or materializer-namespace authentication |
| Existing materializer claim | Any controller-authority attempt, action, or frame |
| State restore failure | Any draw, claim, outcome, prediction, teacher query, or fit |
| State observation failure | Whole-bank accounting mismatch |
| Binding enumeration failure | Protected-input integrity failure |
| Historical replay failure | Private-plan encoding or publication failure |
| Fewer than three mapped options | Unexpected process-level interruption |
| Empty party observation | Private identity/path disclosure |
| Scenario projection failure | Any later ambiguity outside the finite vocabulary |

A local exclusion is not an ignored error. It is a preregistered terminal for exactly one
authenticated context, contributes one aggregate count, exposes no context identity or ordering
clue, and permits the next context to be inspected. A global terminal stops the entire V3 identity
without retry.

## Isolation and authority

Each eligible, unclaimed context gets a fresh emulator instance. A failed state restore therefore
cannot contaminate the next context. The runner measures frames, pressed buttons, counted actions,
and controller-authority attempts before accepting either a projected menu or a local exclusion.
Any nonzero protected effect overrides the local category and becomes the global
`zero_effect_authentication` terminal.

The source contains no behavior commitment, option selection, model scorer, teacher, claim writer,
controller press, emulator tick, after-state observer, or gameplay replay. It restores already
authenticated snapshots only to read current state and enumerate existing semantic bindings.

## Exact accounting

Every authenticated context must reconcile once through this pipeline:

```text
authenticated
  = unsupported + consumed + namespace-authenticated
namespace-authenticated
  = existing-claim + restore-attempted
restore-attempted
  = restore-failed + restored
restored
  = observation-attempted
observation-attempted
  = observation-failed + observed
observed
  = enumeration-attempted
enumeration-attempted
  = enumeration-failed + enumerated
enumerated
  = replay-attempted
replay-attempted
  = replay-failed + replay-authenticated
replay-authenticated
  = fewer-than-three + empty-party + projection-attempted
projection-attempted
  = projection-failed + complete-menu
zero-effect-checks
  = restore-attempted
```

That invariant is checked before coverage and therefore before private-plan encoding or
publication. The receipt validator independently reconstructs it. A changed count, missing
exclusion, false zero, extra identity-bearing field, private path, or free-form reason is rejected.

## The gate remains unchanged

Only complete menus with at least three mapped choices enter coverage. A V3 plan can freeze only
with:

- eight train scenarios;
- at least four genuine offered train option kinds;
- at least three train transformation families; and
- four development scenarios disjoint from train by both family and location.

If the exhaustive bank cannot meet that gate, the honest result is to design purpose-built Red
living-Pokédex captures. V3 may not turn binary menus into training data, lower the counts, reuse a
consumed root, or substitute a sealed/benchmark context.

## Qualification and next boundary

Focused ROM-free tests cover every local exclusion, continued iteration, fresh-context isolation,
finite global stops, fatal-stop non-downgrade, base interruption, hidden frame effects, complete
pipeline reconciliation, coverage, privacy, canonical receipts, plan publication, and idempotent
private records. All source-bound registries must be regenerated and the full repository must pass
before publication.

After exact-source and exact-main CI, the project must publish a path-free qualification and
reorient again. Only that later boundary may decide whether one new V3 inventory identity receives
one protected action-free census. V1 and V2 remain permanently retired.
