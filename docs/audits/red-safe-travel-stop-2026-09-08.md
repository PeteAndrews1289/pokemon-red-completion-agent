# Safe travel stopping and failure-state retention — September 8

## Result

The interruption-budget repair is implemented and qualified. Travel checks the
remaining budget before movement, retry waits, transition waits and readiness
waits. It does not wait for battle17 to begin after16interruptions have already
been handled. The limit was not raised, and no route or species exception was added.
An already acknowledged terminal may complete at the exact limit; an unsettled
transition is not silently certified as completed.

Source400f3d8117f540a78d371fffea893a349027569d.
[Path-free evidence](../evidence/red-safe-travel-stop-2026-09-08.json).

This is engineering qualification, **not a new live capture or training result**.
Model66 remains66examples/27successful/56distinct. The prior failed Route10
attempt remains consumed and was not replayed. Its exact lost terminal cannot be
recovered from screenshots or by relabeling its old starting checkpoint.

## Control and recovery boundaries

- Exhausted budget has its own typed reason, distinct from a handler that failed
  to clear an interruption. Original failure status and partial route remain.
- Readiness-wait failures retain already resolved interruption receipts and wait
  counts. A thrown exception must not discard those measurements.
- Opt-in private failure-state capture stores exact emulator bytes, held buttons
  and counters before component recovery or emulator close. It sends no input and
  does not normalize the failure. Both component failure and unsafe terminal
  boundary are wired into this path.
- These records say safe_checkpoint=false, admitted_continuation=false and
  training_target=false. They are not safe checkpoints, automatic recovery grants
  or invented outcome labels. Existing safe failed-goal checkpoints remain usable
  under their original authenticated completion and continuation rules.
- Retention is not crash-proof: abrupt power loss, emulator failure, an invalid
  save or unavailable disk can still prevent a write. This patch does not add
  automatic unsafe-state recovery or change hard action/frame budgets.

## Qualification

311focused and adjacent tests pass, plus39protocol tests. Cases cover limits
1,2,8,16; initial, movement, retry-wait and delayed-transition interruptions;
exact terminal completion; failed/unready handlers; durable binary serialization;
held-input preservation; mutation/size rejection; and write-before-close wiring.
Three changed source files pass type checks; repository lint passes.
This is not a full-suite or mutation-score claim.

The real historical PyBoy save restored exactly under its original observation
mode. The new diagnostic format round-tripped all167,677bytes unchanged, with
zero controller actions, advanced frames or model queries. This check verifies
serialization on a real emulator, not a new live travel success. It created no
admitted terminal checkpoint or training episode.

## Reorientation and next lesson

The useful-acquisition checklist remains2/3; only an actually useful played and
fitted result closes its final item. Phase3, the Red-first story/living collection,
unfamiliar Red hack and later Crystal sequence are unchanged. Stop further
infrastructure expansion now and define the next bounded learning origin.

The previous live endpoint was not saved. Any use of the older Route11 checkpoint
must be declared as a fresh training branch, with a finite curriculum/reset bound,
the same lineage and the old failure/cost record retained. It is not uninterrupted
continuation, a replacement for the consumed trial, or independent evidence.
Do not merely change the seed and resample the consumed assignment. If a supported
new curriculum cannot be specified without crossing those boundaries, obtain an
explicit scope decision before controller input.

No Flash or Claude work was needed: the localized repair was implemented and
reviewed directly. No fresh external quota measurement or speedup claim is made.

Next-session recommendation: Astra High, Fast off for bounded execution and result
review, reserving Extra High for a genuinely difficult failure. Consistent with
[official reasoning-effort guidance](https://developers.openai.com/api/docs/guides/reasoning#reasoning-effort);
no measured model cost/speed ratio is claimed.

Closeout:121focus/roadmap/dashboard tests also pass. Active-state, documentation,
public-artifact and whitespace checks pass; the regenerated infographic was
visually inspected. Overview8768shows the repair complete and next-origin decision
pending, not live gameplay. Implementation CI was still pending when reviewed;
no full-suite-green claim is made. No gameplay, fitting or external-agent process remains.
