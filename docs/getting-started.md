# Setup and verification

The public repository contains source, tests and selected evidence summaries. It does not distribute the private ROM, saves, recorded trajectories, datasets or fitted model artifacts. It is an active development system, not a packaged autonomous game player.

## ROM-free checks

Use Python3.11 or later in a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,emulator]"
python scripts/check_public_artifacts.py
python scripts/check_docs.py
python scripts/check_product_focus.py
pytest -q tests/test_documentation_surface.py tests/test_product_focus.py
```

The emulator package is installed here because some tests import it; these checks do not need or open a game ROM. On Windows, activate the environment using the corresponding Scripts activation command.

For the larger ROM-free suite:

```bash
pytest -n 2 --dist loadfile --max-worker-restart 0 -m "not integration"
```

The full suite is substantially more expensive than targeted checks. A targeted pass is not a full-suite pass.

## Dashboard and gameplay

The [dashboard guide](progress-dashboard.md) explains how to open the local viewer without launching a game.

Private gameplay requires lawfully obtained compatible game assets, a configured private artifact store and an authenticated starting state/model. Read [the handoff](../HANDOFF.md) before continuing an existing run. Historical launch commands in archived documents are not current instructions and must not be replayed.

Do not download or commit ROMs, saves, models, datasets or credentials. Do not run sealed evaluations or a full-game teacher replay merely to test installation.

[Architecture](architecture.md) · [Contributor instructions](../AGENTS.md)
