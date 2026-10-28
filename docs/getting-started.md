# Setup and verification

The repository contains source, tests and selected evidence summaries. Private
ROMs, saves, trajectories, training corpora and model artifacts are not a public
playable distribution. A documentation/review copy does not authorize gameplay.

## Existing Windows project

The private Windows MAIN installation uses an already qualified WSL2 environment
and its existing Python runtime. The local platform handoff identifies the exact
distribution, user, project paths and current closed state. Do not reinstall or
upgrade that pinned runtime merely to read code or review documents.

The authoritative source checkout and a normal-Windows review copy have different
roles. Edit the active checkout only under the source-writer claim. Review copies
are read-only snapshots; their directory is not a player-resume source.

## Fresh source-only checkout

For an independent public checkout, pyproject.toml requires Python 3.11 or later.
Create a separate environment rather than modifying the qualified private one:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,emulator]"
```

On native Windows, use the environment's Scripts activation command instead.
The emulator dependency is needed by some imports; installing it does not open
a ROM, qualify private assets or launch a game.

## Documentation and ROM-free checks

Run from the source checkout with the intended environment:

```bash
python scripts/check_public_artifacts.py
python scripts/check_product_focus.py
python scripts/check_docs.py
pytest -q tests/test_documentation_surface.py tests/test_product_focus.py
```

These checks need no ROM or saved game. For a behavior change, run proportionate
tests covering that behavior; do not start a full story replay as an installation
test. Focused results are not full-suite or hosted-CI success. Historical broader
failures remain part of the record until an appropriate later check resolves them.

## Private runtime and gameplay

The player uses local learned models and declared execution support. The latest
experimental model is not automatically the configured or adopted actor. Current
source, package, model, continuation and limits belong to
[HANDOFF.md](../HANDOFF.md) and its exact private plan.

All runs remain stopped for review. Do not replay old commands, revive an expired
lineage, treat an old unclaimed plan as current, or import a diagnostic terminal.
An eventual official evaluation needs its own authenticated fresh start, frozen
configuration, declared assistance and explicit authority under the
[completion contract](completion-contract.md).

[Architecture](architecture.md) · [Dashboard](progress-dashboard.md) ·
[Contributor instructions](../AGENTS.md) · [Operating contract](../NORTH_STAR.md)
