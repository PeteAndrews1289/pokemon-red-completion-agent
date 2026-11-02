> Historical snapshot, archived October 26, 2026. Not current instructions.
> Follow [the current handoff](../../HANDOFF.md) and latest user direction.

# Watch the project

The local dashboard is a read-only spectator view. It separates live emulator
state, a pinned historical save, admitted learning evidence and engineering status.
An idle image is not live gameplay, and a coding session is not model training.

## Start the viewer

For the selected run, use the current checkout's focused Mac-local viewer:

```bash
python scripts/run_red_run_dashboard.py \
  --run-dir /absolute/path/to/private/run --port 8768 --live-port 8769 --no-browser
```

Open [the run viewer](http://127.0.0.1:8768/watch) on that Mac. It shows the real
screen when connected, registrations, badges, recorded party health, resources,
elapsed time, recent goals, model versus support attribution and the stop reason.
The selected folder is fixed; another run's feed is rejected. The viewer selects
**red-frozen-autonomous-run-20261016-capture-hazard-v1**, now paused by the user
for a same-save Windows transfer. Worker29400/supervisor29399/sleep29401 exited
October16 18:58:13UTC /14:58:13Eastern. Heartbeat is PAUSED; any remaining viewer
is a spectator showing retained data, not an active game.
[Pause session](../work-sessions/2026-10-16-windows-pause-handoff.md).

[Verified checkpoint](../evidence/red-windows-pause-2026-10-16.json): five badges,
58/124 registrations, Vermilion Pokémon Center, Master Ball intact. Controls are
released; state/context and protected pins verify.740closed choices include
430model-interface/310support and43ordinary setbacks. No new weights.
The native interrupt is the requested pause, not a newly diagnosed software failure.
Windows compatibility is unqualified; no automatic successor or resume is allowed.

The trade-escape predecessor stopped after Brock/14entries when an offered capture
corridor could not bind at arrival. The repair excludes live hazards from its
reachable region, matching downstream walking.868focused tests and copied
composition pass. Paras was earned on the diagnostic copy before a faint; the
survey remains failed, but existing strict recovery and later model choices verify.
No copied gains or new weights; completed124reference and every failure remain.
The prior six-badge/77entry PC-return failure is separately retained.

The Fuji-menu actual remains failed at four badges/38 entries with its exact
partial-training terminal and all costs. Diagnostic XP is never copied in.

The previous story-facing actual remains stopped at4badges/21entries with its
empty Fuji menu, exact state and costs. It is not resumed or erased by the repair.

The previous escape-loan actual remains failed at Brock/13 with full costs and
exact state. Its apparent PC error was a trainer-facing wild interruption. The
new candidate passed strict copy qualification; no failed save was resumed.

The prior route12-v1 actual stays stopped at4badges/36entries with the original
wild-escape/loan failure. The compact actual stays stopped at4badges/21entries
with its Route12 routing failure. Both retain exact state and all costs. No failed
run or completed124reference is resumed or merged into this fresh actor.
[Current work](../../HANDOFF.md).

The [partial-training repair](../work-sessions/2026-10-15-partial-training-recovery.md)
passes1244targeted tests and native composition. Candidate partial-training-package-v3
keeps the target unmet and costs intact, then permits a genuine new model choice.
Diagnostic emulators are stopped; copied XP never enters the fresh save.

The [Route3 correction](../work-sessions/2026-10-14-route3-battle-handoff.md) and
[Fly repair](../work-sessions/2026-10-14-fly-handoff.md) remain copy-qualified, but this
previous Route3-candidate actor reaches neither barrier. It remains failed with one
starter entry at poison-faint recovery; its exact state/costs are preserved.
Previous Fly actor stays separately failed at
Brock/7, dashboard actor at Surge/30. Copied continuation reaches8entries only in
its diagnostic copy; no frame or progress is imported into this actual actor.

Frames are in memory only, with no new screenshot archive. A disconnected or
stale frame is labeled as the last real frame. Party and resource statistics are
last recorded boundaries, not instant battle observations. Completed-segment
decision totals can lag a running segment; incomplete totals show a lower bound
or unknown. Gameplay does not update model parameters automatically.
An exception during continuation export can leave counters/party at the last
completed chunk and omit the outer error here. Use retained root/native receipts
for that tail; missing display text never implies success.

Future fresh or configured launches can opt into the existing frame observer by
declaring this presentation setting **before freezing** their new plan:

```json
"spectator": {"port": 8769, "maximum_fps": 4}
```

It is off by default and disabled during configured inspection. A busy feed port
disables presentation rather than terminating gameplay. Invalid settings fail
validation. Do not change an already frozen actor to add this setting. The
viewer itself never launches a game, opens a save or accepts controller commands;
both original endpoints bind to127.0.0.1 only. Phone access uses the separate
bridge described below, not a change to those endpoints.
The [gate qualification](../work-sessions/2026-10-14-early-route22-gate.md) verifies
real emulator frames on a diagnostic copy and pins the feed in the accepted new
candidate. It played the distinct fresh dashboard run unchanged until that blocker.
The [dashboard session](../work-sessions/2026-10-14-local-run-dashboard.md) records
verification and limitations; [HANDOFF.md](../../HANDOFF.md) owns the next work.

The older research/learning overview remains available separately:

```bash
python scripts/run_product_focus_dashboard.py --port 8768 --live-port 8769 --no-browser
```

Use a different viewer port if both are open. This starts neither gameplay nor a fit.
A separate configured runtime supplies the live port. See [setup](../getting-started.md).

## Phone viewing on the same Wi-Fi

The [phone viewer](../work-sessions/2026-10-15-phone-dashboard.md) is a separate
authenticated read-only bridge on port8767. Open the private link supplied in
chat from a phone on the same trusted Wi-Fi as the Mac. Keep the Mac awake.
The link is private: it grants viewing access, not gameplay controls. The bridge
uses LAN HTTP, not encrypted remote access; it does not work over cellular or
away from home. No router, firewall or public tunnel has been configured.

The current bridge25458 expires October17 at03:20:34Eastern. Its private ACCESS.json
is in the selected run's phone-viewer folder, outside the repository. The Mac LAN
page/status/frame and access boundaries are verified; the actual phone connection
still needs confirmation. Old phone links no longer select this run.
The selected game is running unchanged. For a future authorized running game, an
already-configured spectator can be shared without restarting it, using:

```bash
python scripts/share_red_run_dashboard.py \
  --host PRIVATE_MAC_IPV4 --port 8767 --upstream-port 8768 \
  --run-id EXACT_RUN_ID --access-file /private/viewer/ACCESS.json \
  --deadline-utc FUTURE_ISO_TIME_WITH_TIMEZONE
```

Use a new access file in a private directory and a deadline within24hours. The
bridge refuses another run identity, anonymous requests and all writes. It
cannot launch gameplay. Do not expose the original loopback viewer directly.

## Read the evidence correctly

The saved-state card can lag the newest private checkpoint when public evidence
does not contain every field it needs. Its own source/date is authoritative for
that card. Do not combine its money, species or badges with another save.

The pinned learning chart is a historical135-example fit, not current Model151
or evidence of live training. The active integration task has no new lesson-count
quota. [ACTIVE_PRODUCT_STATE.md](../../ACTIVE_PRODUCT_STATE.md) and
[HANDOFF.md](../../HANDOFF.md) describe current work.

The retained, unselected v3 run is stopped at Brock/10entries,96model choices/12support steps
and six safe setbacks. Read-only tracing identifies an optional late-rival
preparation preview invoked on a healthy one-badge Route22 state; it aborts menu
construction before selection. The subsequent gate repair qualifies on copies;
it does not modify or resume this retained v3 actor.
[Original retained failure](../evidence/red-frozen-v3-menu-blocker-2026-10-14.json).

The protected [completed continuation](../work-sessions/2026-10-14-league-and-collection-continuation.md)
has Champion/concurrent HOF and124entries, but is a different, assisted DEVELOPMENT
save. Its all-six return and legendary custody do not belong to v3. Older
[v1 startup failure](../work-sessions/2026-10-14-frozen-fresh-run.md),
[v2 capture-miss failure](../work-sessions/2026-10-14-fresh-exclusion-repair-and-retry.md)
and [guarded recovery qualification](../work-sessions/2026-10-14-capture-miss-recovery-and-retry.md)
remain distinct. The previous Fly-candidate actor is stopped/failed at Brock/7;
final fresh acceptance stays0/5 until whole-run proof, not pooled progress.

The dashboard's generic **Train the party** label covers develop_team. At the
older Surge/30entry terminal it means **obtain Fly**, not an XP dose. The selected binding and
[retained failure](../evidence/red-frozen-dashboard-blocker-2026-10-14.json) establish
the actual intent. Read the binding/receipt before diagnosing a training loop.

[Earlier completed-run data](../work-sessions/2026-10-10-same-save-run-completion.md)
and the [collected-data assessment](../work-sessions/2026-10-11-completed-red-data-assessment.md)
retain the historical evidence and estimates. Starting either viewer launches
neither gameplay nor a fit.

## Update engineering status

```bash
python scripts/update_product_focus_dashboard_status.py \
  --status working \
  --headline "Connecting the existing player" \
  --detail "Checking recovery; no gameplay running yet." \
  --current-step "Verify continuation" \
  --next-step "Model-selected progression"
```

Use the same status-file location as the viewer if overriding its default.
Status text is operational information, not experimental evidence.
Do not expose private paths in displayed text.

[Generated roadmap](../development-roadmap.md) · [Current audit](../work-sessions/2026-10-11-completed-red-data-assessment.md) ·
[Historical dashboard specification](dashboard-through-2026-09-10.md)
