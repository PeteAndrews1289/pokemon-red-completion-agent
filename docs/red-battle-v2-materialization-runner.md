# Red battle V2 materialization runner

Status: locally qualified on 2026-09-01; publication and exact-head CI are required before use.

This runner consumes the one private seven-capture plan frozen under plan SHA-256
`1eabadcf3d57646d4edf8a78c2d526f085c0ad0d190f48b9f1c3990d4cd80d1c`. It cannot select a
source root, venue, lineage, party slot, capture ID, or destination filename. Those choices are
already fixed by the plan: five Pokémon Mansion captures and both Route 11 captures.

## One-way recovery contract

Every assignment begins `pending`. Before the controller-capable materializer is called, the runner
changes that assignment to `started`, writes a new owner-only canonical journal, flushes the file,
atomically replaces the prior journal, and flushes the containing directory. That consumes the
assignment's only attempt.

The only legal transitions are:

```text
pending -> started -> succeeded
                   -> failed
```

A started, failed, or succeeded assignment can never return to pending. After interruption, the
runner may execute only entries that were never started. A started entry with two complete output
files may be reconciled to succeeded after independent reopen; it is never executed again. A
partial started output remains non-retryable and visible in the fixed denominator.

One owner-only file lock prevents concurrent runners. The runner also holds the existing shared
root-claim lease from the final availability check through the complete materializer call and
journal settlement, so an outcome campaign cannot consume the same upstream root in the middle of
capture creation.

## Authentication before input

Before any journal transition or emulator input, the runner requires:

- clean, published exact source and its complete executable-source bundle;
- the exact successful pull-request CI run and attempt for that source;
- the exact private plan digest and its canonical parse;
- the exact owner-private capture directory identity;
- the exact runtime and Red ROM identities;
- the historical context catalog and registry identities embedded in the plan; and
- a complete whole-bank scan whose independently reconstructed source bindings exactly equal all
  seven planned source bindings.

Pending outputs must not exist. Existing succeeded outputs are reopened on every invocation.

## Independent success check

The child materializer's receipt is necessary but not sufficient. The runner separately reopens the
state and manifest, then loads the retained state into a fresh emulator without advancing a frame.
It verifies:

- capture, root lineage, source state, source commit, partition, and manifest digests;
- the exact planned venue and wild-battle state;
- the exact active party slot, species, and level;
- the main battle menu and the recorded initial-observation digest; and
- a four-move decision surface with at least two supported choices.

Only then can `started` become `succeeded`. The public receipt contains counts and aggregate hashes,
not private paths or per-capture identities.

## Deliberate non-capabilities

This runner creates decision boundaries only. It cannot choose a move, query the teacher, open an
outcome, make a prediction, fit a model, open sealed Red evaluation, touch Crystal, grant gameplay
authority, or replay the game. Those remain separate later gates.

Local qualification passed 64 focused runner/freezer/materializer checks, 113 surrounding protocol
checks, clean public-artifact/document/regeneration checks, Ruff, mypy across 326 source files, and
the complete non-integration suite: 6,192 passed, one skipped, three deselected, one expected xfail,
and one benign SDL warning.
