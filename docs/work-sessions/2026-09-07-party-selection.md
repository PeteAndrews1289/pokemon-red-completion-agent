# Verified party-selection continuation

## Mission check

- Capability: select the intended party member and wait for real menu transitions before committing a swap.
- Learned authority: maintenance unblocking the already-selected evolution option; diagnostic gameplay is excluded from model fitting.
- Transfer test: ROM-free delayed transitions, multiple party orders and selected-member mismatches, followed by one retained-state Red qualification.
- Cheapest falsifier: one bounded intended swap and evolution continuation from the latest retained terminal, with exact roster/collection verification.
- Time box: four hours maximum; reassess after 90 minutes without useful execution.
- Stop condition: any wrong roster mutation, loss of a specimen, component error or global limit stops the attempt. Retain state; no reset/retry or full replay.

## Initial finding

The retained action trace reveals that the shared training `pulse` requested `WAIT(value=180)`
and `WAIT(value=120)`, but the native frame-safe executor uses `repeat` for wait duration. Every
such wait advanced only one frame. The party-menu helper could therefore read stale cursor/menu
state immediately after a transition. This is a concrete timing-contract mismatch; whether it
fully explains the wrong swap must be qualified rather than assumed. Inspect historical wait
consumers before changing the shared helper, and keep historical measurements unchanged.

After ROM-free qualification, allow one new component continuation from terminal
`db557b2758fed7ab86936f53d366e37ca0b9e046226a0826a082cd0c78578b8d` under at most128 four-battle
quanta,100000 actions,5000000 frames and10 minutes. It may use only the existing skill; no fitting
or silent replacement of the official player checkpoint. Preserve each returned quantum and
the exact final collection transformation or failure. Diagnose a failure before declaring any
additional successor; do not automatically rerun.

## Diagnosed continuation stop

The timing-corrected attempt successfully swapped the intended trainee, returned13 quanta
(52 battles), and gained6,812 XP to level36. It then exhausted all damaging PP, but the fallback
for species absent from the original roster counted70 status-move PP as usable attacks. It
stopped after eight safe escapes; terminal5465c3b232933dd2a24c2bbbee0b66e87736c41b177bf75984c3f3285ab57205
is retained and the attempt is closed.

Repair the fallback using actual damaging-move mechanics, not a new species allowlist. Preserve
the historical declared-roster branch. After PP regression tests, declare one successor from
that terminal under the same global bounds. This is new retained-state work, not a reset or
retry of the consumed attempt. Stop after its result and audit before more controller work.

## Closed result and reorientation

The successor completed Rapidash at level 40, retaining the boxed Ponyta at level 30 and all
17 specimens. Living species increased from 14 to 15; registered species from 19 to 20.
It returned 109 completed training battles in 29.807 seconds. Both attempts are closed;
read-only terminal restoration matched without controller input. No diagnostic entered fitting.

361 focused tests, 400-file type checking, lint and documentation checks passed. Model 35
and the useful-play checklist (2/5) are unchanged: private multi-quantum orchestration is not yet
a complete model-facing option. Next connect the existing bounded continuation to player choice,
then collect a fresh eligible lesson and fit. See the [audit](../audits/red-party-selection-evolution-2026-09-07.md).
