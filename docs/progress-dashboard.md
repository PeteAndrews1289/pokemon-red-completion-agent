# Watch the project

The local dashboard is a read-only spectator view. It separates:

- **Live gameplay:** current game frames and observed state, when an emulator is connected.
- **Last verified save:** recorded collection, location and resources, explicitly not live.
- **Learning evidence:** admitted training examples and model records.
- **Development status:** what the coding session is doing; this is not gameplay or learning.

An idle emulator or saved screenshot must not be described as training in progress.

## Start the viewer

From a configured checkout:

```bash
python scripts/run_product_focus_dashboard.py --port 8768 --live-port 8769 --no-browser
```

Open http://127.0.0.1:8768/ on that machine. Starting the viewer does not launch gameplay or fit a model. The live port must be supplied by a separate configured runtime.

The saved panels use repository evidence references. Private operational records and game assets are not part of the public checkout. See [setup](getting-started.md).

## Update engineering status

```bash
python scripts/update_product_focus_dashboard_status.py \
  --status working \
  --headline "Preparing the next collection lesson" \
  --detail "Checking saved state; no gameplay running yet." \
  --current-step "Verify continuation" \
  --next-step "Fresh model-selected goal"
```

Use the same status-file location as the viewer if overriding its default. This operational status is not experimental evidence. Do not expose private paths in display text.

[Infographic roadmap](development-roadmap.md) · [Active state](../ACTIVE_PRODUCT_STATE.md) · [Historical dashboard specifications](history/dashboard-through-2026-09-10.md)
