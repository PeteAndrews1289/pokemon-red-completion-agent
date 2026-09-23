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

The saved panels use repository evidence references. A complete saved-state card can lag the newest
collection receipt when the newer public evidence omits one of the card's required resource fields;
the learning and active-state panels remain independently pinned to their own current evidence.
The dashboard must show that distinction rather than combining numbers from different checkpoints.
Private operational records and game assets are not part of the public checkout. See
[setup](getting-started.md).

The pinned training chart is the historical135-example measured fit; it must not be relabeled
as the current Model141 or live training. The handoff reports141fitted outcomes and the primary
109/124collection save separately from the seven-badge earned story lineage. Latest story
stage283 is stopped before Giovanni; its preparation earned XP, not new model weights.
Do not combine those saves or infer that starting this viewer starts the game. See the
[latest story evidence](evidence/red-giovanni-readiness-2026-09-22.json) and
[research record](research-retrospective.md) for metric and time-accounting boundaries.

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
