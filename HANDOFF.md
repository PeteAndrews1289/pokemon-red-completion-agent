# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md) and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Trainer practice: PP boundary still unexplained

The [latest audit](docs/evidence/red-trainer-practice-pp-boundary-audit-2026-09-17.json)
examined the retained Ground-immunity TRAIN failure without replaying it. The
47-event chain records 11 completed decisions and a twelfth selection of move
slot 2 from PP `(13, 15, 0, 0)`. The runtime observed slot 1 at 15 rather
than the required 13, so it correctly refused a selected-turn outcome. The
preceding slot-2 choice did not execute and spent no PP while the actor lost
7 HP. The failed turn's in-flight after-state was not retained by the old log;
whether a move changed, the party index changed, or a cartridge effect restored
PP cannot be established. Do not label or replay this attempt.

Future runtime failures now retain active-party level, complete party PP and
opponent party position alongside the existing selected move, in-flight move
identities, active PP, HP/status, menu and action trace. A ROM-free test
reproduces the reported off-slot 13-to-15 transition and proves the strict
selected-turn guard still rejects it. All 256 battle-runtime and practice-log
tests passed; this is diagnostic readiness, not learned progress.

The [previous trainer evidence](docs/evidence/red-trainer-practice-telemetry-and-varied-train-2026-09-17.json)
still applies: authenticated assisted TRAIN states can control roster, moves,
levels, stats, HP and PP; a six-on-six logged baseline lost after 29 decisions;
one low-HP three-on-three state yielded six matched opening choices. All
assisted variants share one upstream TRAIN root. No switch-aware challenger
was fitted, no disjoint natural DEVELOPMENT comparison ran, and no battle
authority was promoted. Model137 remains 137 examples / 92 successes / 58
economy-qualified; Red remains 96/124 and fresh acceptance 0/5. Gameplay is
stopped. No full run, ROM hack, Crystal execution or GitHub push occurred.

Next bounded decision: use a prospectively distinct TRAIN scenario with the
enriched diagnostic, or other independent cartridge evidence, to establish
why PP changed before resuming varied outcomes. Keep the strict gate and
separate upstream lineages. Then fit a switch-aware challenger on valid TRAIN
outcomes and compare it against frozen/fixed controls on untouched natural
DEVELOPMENT battles. Sol High, Fast off; Astra High for a later promotion review.
