# Assistance policy

The project does not treat assistance as contamination. It treats undisclosed assistance as an
invalid claim.

| Class | Route knowledge | Read-only RAM/maps | Teacher fallback | Live foundation model | Claim |
| --- | --- | --- | --- | --- | --- |
| Deterministic teacher | Yes | Yes | Not applicable | No | Scripted expert baseline |
| Hybrid learner | Yes | Yes | Disclosed | Optional, disclosed | Autonomous hybrid completion |
| Learned skill stack | Yes | Yes | No | No by default | Trained specialists completed |
| Distilled macro-policy | Goal identifier only | Declared structured state and pixels | No | No | Local learned controller completed |
| Pixels-only ablation | No route at inference | No | No | No | Research comparison only |

Training snapshots, demonstrations, and corrections are permitted for every learned class. They are
disabled during official evaluation.

The objective graph and deterministic action executor may remain present in a learned-stack run.
They provide temporal abstraction and controller safety; they do not choose a specialist's learned
battle or recovery action.

A completed human run is not required to build the deterministic teacher chapter-by-chapter. A
full clean teacher completion is this project's promotion gate before training or evaluating
full-game composition. Completion claims are governed by their own clean-run evidence. The
[Teaching and Data Plan](teaching-plan.md) defines the reference and demonstration boundary.
