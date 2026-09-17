# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 16, 2026.

## Static natural battle bank cannot supply the next fit

The [action-free audit](docs/evidence/red-natural-battle-supply-audit-2026-09-16.json)
authenticated all 81 source saves (54 train, 27 validation) and inspected
natural battle captures without input. The train capture bank has 18 starts on
14 upstream roots; no root has more than two starts, and four starts have only
one supported attack. Among the 14 multi-action starts, just two move sets
appear. The ordinary four-roots/four-examples-per-root fit gate is unavailable
from this bank. The old 20-example development evaluation gave the learned
ranker zero wins and two losses against the fixed heuristic; the recent
assisted pilot only tied it.

The richer source saves contain 16 supported party move sets, but most are
historically consumed. After excluding account claims and prior battle
materializations, only six untouched train roots remain (three with three
eligible party members, three with six), concentrated in advance-story and
recover-control contexts. Four untouched development roots remain. No root
was claimed or replayed, no controller input or outcome was produced, and no
model changed. The anti-drift no-learning alarm fired, so stop sampling this
static bank rather than lower the fit gate or clone assisted examples.

Next: implement a bounded model-directed multi-encounter *train* episode.
Retain each model choice and pre-choice state before input, actual terminal
outcomes, semantic diversity, hard cost limits and no teacher fallback. Only
isolated train-side branches may evaluate other attacks; reserve separate
upstream development episodes. Begin with ROM-free durability/partition tests;
at most one prospectively frozen train-only mechanical pilot if they pass.
Do not fit yet. See [decision](docs/roadmap-decisions.md).

Red remains 96/124, 74 specimens, 198 cash; Model137 and frozen battle
authority are unchanged, fresh acceptance 0/5. Gameplay stopped; no GitHub
push. Sol High, Fast off for this bounded implementation.
