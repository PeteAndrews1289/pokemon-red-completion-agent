# Adjacent-map income: verified support, not learned story completion

The player reached an ordinary trainer on Route 25 from its real Route 24 save
and earned **525 currency**, without rewinding or selling protected stock.
The final retained balance is **619**, with **30 specimens / 28 living species /
33 registered species**, zero balls, and all four protected Full Restores.
The public [evidence](../evidence/red-regional-income-qualification-2026-09-08.json)
contains both attempts and exact endpoint hashes.

## What worked, and what failed

The new opt-in planner reserves trainer bodies and undefeated sight lanes by map.
Its search is limited to the current map and immediate ordinary connections.
It permits walking and connection transitions, not doors, ledges, Surf, Cut or
guessed return warps. Persistent events qualify remote quotes; real engine objects
must revalidate the target on arrival. Legacy saved menus remain local-only.

The first attempt reached the intended adjacent square but failed to start battle:
the game had armed the correct trainer while a dialogue page remained visible.
The previous intro loop treated every pending latch as wait-only. It exhausted its
unchanged pulse budget and saved checkpoint1c1b89ad/state73e15d0c after **141 actions /
13,836 frames**. No payout or learned row was claimed.

Zero-input reload established the pending identity209/2, visible dialogue, unchanged
party HP and specimen counts. The repair confirms visible dialogue only after
binding the pending identity, while keeping dialogue-free pending transitions
wait-only. It does not re-interact, increase limits, or resume an unrelated trainer.
Tests distinguish fresh pending dialogue, retained pending dialogue, ordinary
wait-only transitions, and wrong identities.

A separately identified continuation of that exact state finished the same battle
in **78 actions / 7,513 frames**. Trainer event1367 is now set and money rose94 to619.
Checkpoint21445916/state34949deb is ready overworld at Route25(x8,y5), with no pending
battle or dialogue. Electrode HP fell89 to71; the other five HP values were unchanged.
Both terminal reloads used zero controller actions or emulator frames. All30 specimens
were preserved, and594 recorded party-HP observations contained no faint.

Total cost including failure: **219 actions / 21,349 frames**. This demonstrates a
finite adjacent-map income skill, not sustainable income everywhere in Red.

## Learning and phase boundaries

The zero-ball safety policy selected resupply in both episodes. Model76 remains at
**76 fitted outcomes**,34 successful and66 distinct selected feature rows. There
were **zero new model fits or eligible rows**. Trainer ranking and battle control
remain deterministic. Keep these two support episodes, the prior earned-followup
singleton capture, and all preceding failure costs in the next genuine fit's lineage.
Never fit support alone or describe it as learned trainer selection.

The prior resource-integration checklist remains closed3/3 in roadmap history.
The new bounded **income-to-story checklist is1/3**; this is not a Phase4 percentage.
Phase4 still needs honest story-entry readiness, genuine model-directed story
outcomes across bounded varied conditions, and eventually the unchanged full-run
gate plus concurrent Champion-event/Hall-of-Fame evidence. No sealed evaluation,
full replay, Crystal run or transfer claim occurred.

The retained semantic state identifies **defeat_lorelei** as the next legal story
objective. Its eight badges and prior Victory Road progress are inherited from
the teacher-origin lineage, not newly learned achievements. The old Lorelei chapter
requires an exact lobby coordinate, first-party moves and stock quantities. Its
availability check does not expose every execution assumption. It must not simply
be switched on for the current party/inventory. The next session should qualify
current-state access and a truthful preparation contract, then one bounded story
choice—not repeat heal/capture cycles or rebuild the fixed teacher.

## Validation and agent loop

**276 focused tests and111 roadmap/product/dashboard tests pass**, plus full lint, type checking, artifact and documentation
checks. The registry was regenerated before executable publication. Sourcec5687c1c
introduced adjacent-map funding; source46e43319 repaired pending dialogue. Both are
published on PR236. At review, the older documentation run34246748329 had passed;
the new source runs34249064006 and34249920442 were still running. No hosted full-suite
pass for the new source is claimed, no workflow was disabled, and no manual reruns
were requested. Development did not wait on CI.

The first dashboard refresh correctly rejected a support episode placed in the
last-fit episode field. The published projection now retains the actual fitting
episode and lists the latest zero-label support separately. A new test loads the
real public reference through the dashboard's native training boundary. The local
dashboard was checked again and displays the verified income result, not a refresh
failure. No claim guard was relaxed.

Flash High's first headless attempt was blocked by command permissions and supplied
no audit. A tool-free review of source excerpts then identified useful map-qualified
reservation and live-rebinding concerns. Its suggestion to allow only `walk` steps
was rejected because legitimate map connections have their own transition kind.
Codex implemented, tested, executed and audited the work. This was useful bounded
review, not independent game verification or a demonstrated speed comparison.

After use, Gemini allowance was **91.36% five-hour / 93.68% weekly remaining**, resetting
September8 at17:59:32UTC and September11 at23:22:45UTC. Claude was not called; its
subscription usage was not queried. The Antigravity third-party pool is not a proxy
for that subscription. No external agent or emulator is left running.

Next recommendation: **Astra High, Fast off** for the state/readiness integration;
reserve a higher effort for a specific design dispute. OpenAI Docs was used to check
the supported [Astra reasoning settings](https://developers.openai.com/api/docs/models/gpt-6-astra),
not to infer a measured account-usage multiplier.
