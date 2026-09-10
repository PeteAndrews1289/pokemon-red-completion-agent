# Native player learning: session audit and reorientation

## Verdict

The player-to-learner loop now works on actual Red execution: **two sampled goal outcomes were
added to all 29 retained examples, producing a 31-example model**. The updated artifact reloads,
and its saved game state restores with fresh semantic and living-ledger agreement, without input.
See the [path-free result](../evidence/red-native-player-learning-result-2026-09-06.json) and
[prospective session record](../work-sessions/2026-09-06-resource-cost-learning.md).

This is a small nine-output goal-value model choosing among supported objectives. Deterministic
navigation, menus, battle/capture skills and safety still execute the mechanics. It is not an
end-to-end game-playing network, a completed Red player, or demonstrated Crystal transfer.

## What actually happened

| Launch | Gameplay | Training admission | Terminal |
| --- | --- | --- | --- |
| Original A | No controller input | None | Binding wrapper dropped the new quote |
| R1 A | Four successful goals; 656 actions / 40,368 frames | None: all choices recorded as nontraining | End-save encoding rejected by the path guard |
| R1 B | Four successful goals; 656 actions / 40,368 frames | Two sampled outcomes; two nontraining choices excluded | Complete archive and durable checkpoint |

Original B never launched. Each controller-started episode ran once; no failure was replayed or
relabelled. R1 A remains an attempt, not an outcome-selected exclusion. Its sampling contract
produced no eligible rows regardless of its successful gameplay. The amendment to supported-menu
sampling was declared before B, not applied to old observations as invented behavior labels.

B retained two needed specimens, one a new living species: living **13 → 14**, registered
**18 → 19**, required specimens **108 → 106**, no undeclared losses. It also spent **12,000**,
ending with **649 money and 19 capture items**. Useful progress and inefficient spending both
belong in the report. These resets share one training lineage, not independent roots.

## Learning evidence

- Prior checkpoint: `bbd36e556bd57a3afb212d0f2a4fd3360336bd17afaefe92a31a72c60a17d01a`.
- Updated checkpoint: `95f62eaafc55a053cf65e23a8dcbf99955360040b85ef56ad8eff3e925edb472`.
- Fit: selected-arm capped-importance-weighted multi-output ridge; **31 settled rows**, 14
  successes, 26 distinct selected feature rows. All prior rows survive unchanged; no unselected
  counterfactual targets, development fitting, teacher-choice labels or authority promotions.
- On the same retained 31 rows, prior-model weighted MSE **0.00514748 → 0.00479554** after fitting.
  This is training error, not held-out accuracy. The fitter's separate initialization error is
  not the old checkpoint's error and must not be used to inflate the claimed improvement.
- On the four recorded inputs, the updated greedy policy changes one of the two model-supported
  decisions: it ranks continued acquisition above the second supply trip. This is an **in-sample
  replay**, not an executed counterfactual or an independently verified gameplay improvement.
- The saved B checkpoint reopens and agrees with fresh emulator observations. The updated model
  loads at that endpoint; its next choice is a deterministic unsupported-menu bridge because only
  one learner-supported goal is available. This check executed **zero actions and zero frames**.

## Engineering findings and fixes

1. Binding wrappers reconstructed objects and lost optional price metadata. Dataclass replacement
   now preserves it, and the action-free preflight exercises the real execution wrapper.
2. The sampler required coverage of all available physical goals, including unsupported healing.
   V2 samples the exact supported learner menu after deterministic safety. Unsupported goals have
   no positive selection probability outside that menu; do not claim full physical-action support.
3. Ordinary Base64 save data tripped a legitimate path filter. Checkpoint V2 uses URL-safe encoding
   without relaxing that filter; old checkpoint addresses and V1 reads remain supported.
4. Unit success did not expose those integration seams. Added tests span actual player wrappers,
   durable native trajectory admission and real private-store binary checkpoint persistence.
   The two newly reproduced sampling/encoding regressions are both killed by targeted mutations.

Local qualification before B: 111 focused tests, clean lint/type checks, product-focus/docs and
public-artifact checks. The earlier full suite was 7,073 passed, one skipped, one expected failure;
that baseline is not a claim about subsequently edited files. The final session verification is
recorded below. No external agent review occurred this session.

Final verification: **7,085 passed, four skipped, one expected failure** in 1,955.84 seconds;
156 dashboard/focus checks also passed. Lint, type checking, generated-registry consistency,
documentation/product-focus checks and public-artifact checks passed. The dashboard was inspected
in the browser: 31 examples, correct training-error values, explicit historical gameplay, and no
live emulator falsely displayed. Publication uses one consolidated pull request; CI is a background
publication check, not a dependency for the already completed fit.

Post-suite observer repair: the final live check found that a transient evidence/checksum mismatch
during a multi-file update escaped the refresh handler and stopped the viewer. The observer now
keeps the last verified inputs, reports blocked refresh, and resumes when all inputs validate;
initial startup still requires valid evidence. An actual main-loop regression test and **157**
dashboard/focus checks pass. This isolated observer change and its registry identity were made
after the full suite; no second full-suite pass or additional model fit is claimed.

## Remaining risks, in priority order

1. **Useful behavior is not yet established.** The training update changes a recorded preference,
   but the fitted 31-example model has not executed a new prospective chain. Do that before another
   architecture redesign or larger data campaign.
2. **Quantity and incentives remain incomplete.** Price/reserve quotes provide real known costs,
   not learned money forecasts. Fixed ten-ball purchase offers can overfill reserves. The current
   utility may still reward easy maintenance over completion; judge actual choices and spending.
3. **Living-Pokédex progress is richer than the old targets.** A needed duplicate precursor reduced
   remaining specimen requirements, yet its old species-count-based completion target was zero.
   Preserve that label's historical meaning. A future version should explicitly represent verified
   requirement reduction and dependency unlocks, not rename old zeroes into invented positives.
4. **Coverage is tiny and correlated.** Both new rows are successes from one familiar lineage.
   Retained failures help, but this does not teach every quest, evolution, storage maneuver or
   legendary puzzle. Do not equate 31 fitted examples with broad game competence.
5. **Continuation is only read-only qualified.** There is a valid terminal save; the actual bounded
   continuation consumer still needs parent-lineage binding and a fresh observation check before
   input. Do not re-enroll the endpoint as a new independent catalog root.

## Next session: use the model, preserve its progress

1. Add only the thin continuation consumer for an authenticated completed checkpoint, retaining
   parent lineage, original train partition, fresh quotes and the existing controller limits.
2. Freeze one short, prospective **31-example model** continuation (at most four goals). Measure
   model versus safety choices, required specimens, money, items, actions and failure causes.
   Do not fit that diagnostic as if it had exploratory full support. Save its terminal state.
3. If it buys wastefully, qualify a reserve-deficit quantity offer before collecting more easy
   shopping examples. If it collects sensibly, prioritize missing evolution/storage interactions.
4. Reorient on those results. Design a versioned specimen-requirement target only when the current
   target demonstrably hides needed living-Dex progress. Keep old models/data readable and intact.

Time box: one bounded session, up to four hours; stop earlier at a verified continuation and
reorientation. No new teacher factory, consumed-trial retry, sealed Red, Crystal or full-game run.
The end product remains a model that completes games and assembles a living Pokédex, with version,
trade and event dependencies explicit. Red competence comes first; title-neutral interfaces keep
later transfer possible without pretending it has been demonstrated.
