# Local Red run dashboard

Build a Mac-only spectator view using the existing dashboard transport and frame
observer. Preserve the stopped frozen run, completed reference and all run data.
The dashboard neither launches gameplay nor supplies controller inputs.

## Mission check

1. Capability: watch an actual run and understand its current goal, recorded party,
   progress, recent decisions and failure without digging through private logs.
2. Authority: the player retains all strategic and battle decisions. The browser
   has display controls only; observing cannot launch, resume, fit or steer it.
3. Reuse: existing loopback HTTP server, typed public snapshots, PNG observer,
   relay and durable native receipts. No new logging or hosting service.
4. Cheapest falsifier: a stale or unrelated feed appears live, private paths leak,
   HTTP writes are accepted, or enabling the viewer changes controller behavior.
5. Up to90minutes; reassess after15stalled minutes or two equivalent failures.
6. Stop for completion or a connection requiring broader authority. Do not start
   Red, alter the frozen package/plan, load a save, or fix the rival-preview bug.

## Delivered and verified

The [Mac-local spectator](http://127.0.0.1:8768/watch) is open, using the existing
server, typed snapshot, PNG observer and relay. It shows the selected run's party
and HP, registrations, badges, money, balls, elapsed time, latest goal, recent
choices, model/support attribution and failure. Fullscreen changes presentation
only. [Usage](../progress-dashboard.md) explains the fixed run selection.

Current v3 is still stopped at Brock/10entries:96model choices/12support steps,
six safe setbacks,131cash/seven balls and healthy14/14/16/14/14/14party. It has no
screen publisher, so the viewer truthfully shows no live frame. Future fresh and
configured launchers accept a pinned opt-in feed; default-off and inspect mode
attach no observer. Pixels are rate-limited, in memory only. A busy port does not
abort the player. No hosted service, phone connection or new archival log exists.

Readers inspect recent durable receipts, cache projections and read at most64KiB
of each large segment report for reconciled top-level counters. They do not load
entire journals or repeatedly parse every old context. Partial writes retain the
last observation; unknown/partial totals are not presented as an observed zero.
Party/resources remain explicitly last recorded boundaries. A stale/disconnected
frame is retained as the last real frame, and another run's feed is rejected.

[Path-free verification](../evidence/red-local-run-dashboard-2026-10-14.json):
395 targeted ROM-free tests, Ruff and typing of both new runtime modules pass.
Browser rendering shows the exact stopped checkpoint with no console errors.
Synthetic PNG transport and existing mocked adapter rendering are verified;
an actual private-ROM frame stream has not been launched or qualified here.
This is not full-suite/CI success or a new frozen candidate.

All7,874frozen package files,4,512environment files,24protected reference files
and five retained-run pins rehash unchanged. Completed124save and original v1/v2
failures remain separate. Gameplay worker/supervisor76970/76956 are absent;
the viewer alone is running. No private save load, input, registration, TRAIN,
fit, parameter update, rival repair, restart, deletion or publication occurred.

## Next work

The prior read-only diagnosis already found the cause: preparation requests a
late Route22 rival preview from a healthy one-badge state. The strict eight-badge
validator raises before menu selection. Do not re-diagnose the whole game.
Propose one scoped eligibility-gate repair and early/late/consumed/ambiguous
regressions, then a separate authorized native-menu copy qualification. Preserve
the frozen failure; declare the spectator before any later candidate freeze.
Use up to1hour, reassess15stalled minutes/two failures, and explain any expansion.
Reuse the current models and executors; no refit, battler redesign or copied gain.
