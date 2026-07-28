# Contributing

This project is completion-first: a change must make the system more correct, more observable, or
more likely to finish the game under the declared evaluation contract.

Before opening a change:

1. Keep ROMs, saves, snapshots, recordings, datasets, checkpoints, credentials, and private paths
   outside the repository.
2. Preserve the separation between actor decisions and read-only verification.
3. Give every new quest objective a machine-checkable completion condition.
4. Give every specialist bounded outcomes: `success`, `retry`, `replan`, or `fatal`.
5. Add ROM-free tests and run:

   ```bash
   python scripts/check_public_artifacts.py
   python scripts/check_docs.py
   ruff check .
   pytest -m "not integration"
   ```

Private runtime changes should also pass:

```bash
POKEMON_RED_ROM="/absolute/path/to/Pokemon Red.gb" pytest -m integration
```

Training assistance is allowed, but it must be labeled. Evaluation changes may not silently add
teacher actions, save-state restoration, online code modification, or human controller input.
