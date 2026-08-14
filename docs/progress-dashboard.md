# Pokémon Learning Observatory

The dashboard is the human view of a run. It combines the live emulator screen with the evidence
needed to understand what the agent is doing and how far the experiment has progressed.

## What it shows

- the rendered game frame, run state, current stage, progress, actions, frames and emulation speed;
- the model's current goal choice, confidence, teacher-query count and fallback count;
- registered, living and level-cap collection totals, capture supplies and free storage;
- party levels, health and status plus the currently available goal pressures;
- the 18 zero-shot, 27 adaptation and 27 sealed-test counters; and
- recent identity-safe evidence events.

The initial Crystal preview intentionally shows zero model and experiment progress. It authenticates
the 1.1 cartridge and proves the display path without opening a context, asking the teacher, making
a prediction, sending controller input or saving cartridge state.

## Start the authenticated preview

From the repository folder, activate the project environment, provide the path to a private,
lawfully obtained international Crystal 1.1 cartridge, and start the preview:

```sh
source .venv/bin/activate
export POKEMON_CRYSTAL_ROM="/Users/user/path/to/private-crystal-1.1.gbc"
python scripts/run_crystal_dashboard.py
```

The browser opens automatically. Stop the preview with `Ctrl-C`. Use `--no-browser` when another
browser window already has the displayed local address, or `--duration-seconds 60` for a bounded
one-minute preview.

## Safety boundary

The dashboard binds only to this computer at `127.0.0.1`. Its server supports view-only GET
requests and has no controller, teacher, prediction or save endpoint. Runtime code publishes a
validated, identity-safe snapshot to the display; the display never feeds data or instructions
back into the agent. Private paths, raw memory addresses and binding identities are excluded from
the status document.

The same observer boundary is intended for live qualification, demonstration collection, model
fitting, zero-shot evaluation and later causal runs. A counter advances only when the corresponding
authenticated workflow publishes real progress.
