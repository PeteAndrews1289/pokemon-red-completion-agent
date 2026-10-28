> Historical snapshot, archived October 26, 2026. Not current instructions.
> Follow [the current handoff](../../HANDOFF.md) and latest user direction.

# Setup and verification

The public repository contains source, tests and selected evidence summaries. It does not distribute the private ROM, saves, recorded trajectories, datasets or fitted model artifacts. A private local frozen player package now passes isolated startup; full fresh autonomous Red remains unproven. This public checkout alone is not a complete playable distribution.

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

The [dashboard guide](../progress-dashboard.md) explains how to open the local viewer without launching a game.

Private gameplay requires lawfully obtained compatible game assets, a configured private artifact store and an authenticated starting state/model. Read [the handoff](../../HANDOFF.md) before continuing an existing run. Historical launch commands in archived documents are not current instructions and must not be replayed.

Do not download or commit ROMs, saves, models, datasets or credentials. Do not run sealed evaluations or a full-game teacher replay merely to test installation.

## Private frozen-player launch

The current package reuses151 and the existing scoped actors. Its isolated wrapper
binds source/data/model/plan hashes and a verified installed Python environment;
that environment is not shipped with the public repository. The exact private
launch command and unclaimed clean-start plan are identified in [HANDOFF.md](../../HANDOFF.md).
Use that frozen command,not a mutable historical helper or an old saved checkpoint.
The short startup smoke proves a learned handoff/live renewal,not full completion.
Review disclosed mechanical support and prospective limits before claiming a run.

## Opt-in learned trainer

This section records the earlier minimal integration,not the current full-player default.

The authenticated private plan for `scripts/run_red_autonomous_collection.py` may include
`trainer_battler` with `path`, the qualified frozen J `sha256`, and the actual development
`root_lineage_id`. The model stays private. Omit this binding to preserve existing controllers.

This setting covers ordinary trainer-funding battles with one to three own party members,
not wild captures or Elite Four fights. Decisions, timings, failures and final states are
retained under the run's private `trainer-battles` directory. Player budgets and strict
funding preservation checks remain active; a faint can fail the goal before battle completion.

The first live integration failed that no-faints check. Read the
[checkpoint report](../work-sessions/2026-09-19-player-battler-integration.md) before use.
Do not rerun its consumed one-shot probe or mistake the setting for full-player qualification.

[Architecture](../architecture.md) · [Contributor instructions](../../AGENTS.md)
