# Two-worker testing works; the newer battler still loses Misty

[Prospective plan](2026-09-27-two-worker-diagnostic-plan.md) ·
[Audited evidence](../evidence/red-two-worker-diagnostics-2026-09-27.json).

## Delivered

The bounded scheduler supports one or two fresh worker processes with exclusive
job directories, pinned inputs, a frozen Python runtime copy, per-worker logs and
observed process exits. It stops pending dispatch after failure and drains active
bounded workers. Watchdog expiry requests interrupt cleanup before escalation;
forced termination never implies a valid saved endpoint.

Existing emulator behavior already uses in-memory cartridge data and disables
battery/RTC saves. No campaign save, original fixture or model is written.
Workers use the existing retained-session exporter and battle telemetry.
The fresh worker reuses existing deterministic opening/rival logic, not a new route.
No source edits occurred while native workers ran; tests additionally prove the
runtime copy remains unchanged when its source checkout is edited.

Reusable implementation:emulation_batch.py and run_red_development_worker.py.
The latter deliberately exposes only this bounded battle/opening protocol,not
an unrestricted campaign launcher. Future packets need their own declared bounds.

## Measured results

| Test | Result | Actions | Frames | Batch elapsed |
| --- | --- | ---: | ---: | ---: |
| Risk/cost battler,current/prepared x offsets0/4/8 | 0/6wins,6native losses,0execution errors | 1398 | 118008 | 8.63s |
| Two independent power-ons through first native rival | 2/2teacher passes | 630 | 71746 | 3.80s |

Both batches reached exactly two overlapping worker processes. All eight actual
exits were observed;none timed out. These durations include process startup.
There is no matched serial native timing experiment and no claim of2x speedup.
Most session time is implementation/audit,not emulator execution.

An independent audit replayed all111battle decisions,authenticated event chains,
checked native endpoints and630fresh action receipts,and verified source protection.
Decision latency averaged2.83ms,max6.36ms. Audit advanced zero emulator frames.

The two fresh starts end with Squirtle6 and3175cash after rival victory. They load
no state,edit no game memory and query no model. They are DEVELOPMENT smoke tests,
not TRAIN supply,autonomous play or progress toward final fresh-Red acceptance.
Their retained states are not silently substituted into the actual player.

## What the negative result tells us

The existing newer actor1b8c8361 wins0/3with current17/7/5/7 and0/3with
prepared17/17/17/7. No fit,admission or deployment occurred.
All six defeat Staryu but lose to Starmie. Last-turn active Starmie HP:
current59/59/56;prepared45/49/59. Stored roster HP is not a damage summary because
the active enemy's stored party entry can lag its live battle HP.

There are11voluntary switches,126HP lost during those actions and4arrival faints.
That is fewer switches per battle than the prior screen,but not a winning policy
or a controlled attribution of improvement. Example:prepared/offset0 switches
Wartortle29/47HP to Kakuna7,which faints on entry. Wartortle subsequently chooses
Water Gun for2damage per successful hit against Starmie. Do not infer an unplayed
Tackle counterfactual or conclude every realistic preparation fails.

The controller executed what the model chose. Additional concurrency,more reserve
levels or a strategic sequence learner is not a demonstrated solution to this gap.
The original12battles and these6remain separate,consumed diagnostic packets.
All battle fixtures share TRAIN ancestry;timing siblings are correlated.

## Decision and next bounded work

Keep the two-worker infrastructure. Do not deploy this battler or begin a broad refit.
Next30–45minutes:inspect attack-ranking/switch-cost scores at retained bad boundaries,
then specify one attack-versus-switch outcome lesson using the existing
red_trainer_practice_counterfactual.py collector. Predeclare branches,horizon,caps,
and an untouched evaluation source before consuming more native trials or fitting.
The key falsifier is whether a practical legal alternative improves the measured
outcome;offline recommendation changes alone are insufficient.

This session stops at the declared eight attempts. Expanding another subsystem
requires explaining the evidence and scope first. Learned preparation/member choice
remains pending;sequence learning remains deferred. Original Misty/Bill unfinished.

## Verification and provenance

150targeted tests pass;703source files pass the repository type-check gate.
Lint,documentation links,active focus and generated roadmap checks pass.
Post-run review added a ROM-free-tested deadline recheck after slow input hashing;
no native packet was replayed. This is not a full-suite or full-game qualification claim.
Plan SHA:e6764f1ad27689571db936ad976b966b1065527b8df35365a01744783340e7d5.
Private audit SHA:92da44de49c6b69dc4de318ee362fd9baf182d6f5d8be0183fa29cdbbb629266.
Runtime manifest SHA:8a51b710bde29e381c92a8852f228c89ebe58c3d485ad12a8f24293517ebe5a5.
Source parent:c11bb703 plus the pinned new worker implementation.
No admitted learning rows,fits,promotions,registrations or campaign progress.
All gameplay stopped;no publication.
