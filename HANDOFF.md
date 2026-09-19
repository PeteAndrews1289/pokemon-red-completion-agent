# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September19,2026.

## Supported battler v1 qualified; return to main-player work

[Current evidence](docs/evidence/red-battler-earned-switch-result-2026-09-19.json) ·
[Prospective plan](docs/evidence/red-battler-earned-switch-plan-2026-09-19.json) ·
[Prior learning/package](docs/evidence/red-battler-policy-learning-result-2026-09-19.json).

Frozen J remains SHA256
260b227a2fb3ba46a80be9c42e1f7e17977068e890f135407f8faafe2336fb09.
No new fit, examples or weight changes;318physical TRAIN contexts.
Prior15TRAIN checks, generated3v3 J9/24 versus H7/24 and natural attack evidence stand.
The preceding two-member Rocket trials did not exercise reserves; their failed
coverage gate remains historical, not retroactively passed.

## New earned-state switching and live handoff

Declared parents: boot2900-timing0-J and boot3100-timing0-J from
red-trainer-natural-team-20260919-v1. Same two origins, not new independent roots.
Existing short traversal reached a new Super Nerd encounter; normal party menus
put Zubat first. Setup was disclosed, not learned navigation or a teacher attack.
One initial load each, no battle reset, memory edit, healing cheat or replay.

J won2/2, defeated6opponents, made33decisions:27attacks,2voluntary switches,
4prompt declines. No faints, invalid actions, suppressed attacks or teacher queries.
Boot2900 switched on decision3 after two attacks; boot3100 switched immediately.
Decisions18/15; HP lost34/23; battle frames20262/16442; total frames26082/21206.
Mean actor inference1.098ms. Two typed predeclared ADVANCE_STORY objectives succeeded;
these are not learned high-level goal choices or a full-player promotion.

The live entry point is
pokemon_red_completion.red_trainer_practice_episode.run_live_red_trainer_practice_episode.
It borrows the player's running emulator, verifies capture bytes, refuses reset
and leaves the actual state intact on success or exception. Caller owns budgets,
durable endpoint capture and fresh verification. The standalone runner still works.
Both battle-final and final endpoints reopened read-only with matching observations,
enemy rosters, event chains and fresh completion ledgers;0actions/0frames.
First winner also passed the existing field-control continuation in the same emulator.

Private run: red-trainer-earned-switch-20260919-v1, source bfe9a440.
Private package: red-battler-live-v1-20260919/package.json, SHA256
d5e4a79c5b2baf19e91445ca1a9cbef4e858e104e2d8d4589b85119437e67fb4.
Each boot directory retains battle/final snapshots, logs, ledgers and typed outcomes.
Boot2900 ends HP10/10, Wartortle poisoned; boot3100 HP12/12, no status.
Preserve these real recovery needs; field-ready does not mean healed.

## Next: one main-player integration session, not more trainer refits

The existing main collection controllers were NOT automatically replaced.
Explicitly connect frozen J at one supported main-player trainer boundary, then
execute one bounded saved-state goal with resource/recovery and fresh-ledger checks.
Estimate45–60minutes if the existing boundary fits. Use the existing Model137
collection restart and its provenance; do not count these early-game test saves
as additional registrations in the96/124 collection save.
No new trainer factory, fit, generic review gate, full Red run or push.
Six-member reliability and natural forced-target choice remain unqualified.
Status/recovery/boost moves, Counter, self-destruct and all-party Struggle remain
excluded. This is a scoped v1 delivery, not universal battle knowledge.

1194focused tests passed;13optional integration skips. Mypy527source files passes.
Full suite not rerun; old unrelated dashboard/timing/fingerprint failures unclaimed.
No Flash/Claude. Gameplay stopped; no GitHub push.
Model137 unchanged:137examples/92successes/58economy-qualified; Red96/124,
74specimens/198cash; fresh acceptance0/5.
Next session: Astra High, Fast off per Pete; main-player integration judgment.
