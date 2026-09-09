# Phase4 closeout — bounded hierarchical Red story completion

## Verdict

**Phase4 is complete under its unchanged declared authority.** The current saved
state verifies both Champion defeat and Hall-of-Fame entry. This is model-directed
play composed from authenticated development checkpoints, not a fresh-game
autonomous run or a learned battle policy. [Public receipt](../evidence/red-phase4-closeout-2026-09-09.json).

The stable exit remains: “Model-directed completion with concurrent Champion and
Hall-of-Fame evidence under declared authority.” No independent win-rate gate,
new full replay or extra boss cohort has been inserted or silently removed.

## What actually ran

Executable source `03e14672b635bc9473f06d56efbc779c7fe3b6fe`, bundle
`f957e9cfa0537e373a6192c5b95962bb4aa202967a2585bf022ee6d36ceadb0c`.
The new plan used native83, seed2026090982, three decisions, one available
qualified battle Full Restore and the combined owned HP/PP recovery profile.
It started at the successful, model-selected Lance checkpoint. No failed save
was resumed; no controller-input trial was retried.

| Step | Authority | Outcome | Actions | Frames |
| --- | --- | --- | ---: | ---: |
| Restore HP | Sampled model choice against available story | Jolteon healed with one Full Restore | 54 | 4,488 |
| Restore PP | Sampled model choice against available story | Blastoise restored with one Elixir | 44 | 3,828 |
| Advance story | Explicit forced singleton | Champion defeated; Hall of Fame reached | 554 | 31,662 |

Total:652 actions/39,978 frames,2 genuine choices,1 forced step,3 owned items
(one field Full Restore,one Elixir,one battle Full Restore),0 faints,0 specimen
losses. All30 specimens remain;33 species are registered and28 unique species
are living. Jolteon participated: its Thunder PP fell from4 to3. Battle choices,
move selection, item targets and profile sequencing were not learned.

The earlier native82 Lance victory contributed one genuine story-vs-healing
choice,270 actions/25,813 frames,zero medicine or faints. The two successful
final legs together cost922 actions/65,791 frames; that is **not** the total
development cost and does not erase earlier failed attempts.

## Evidence and audit

- Episode:`red-model-combined-20260909-champion-01-causal`.
- Manifest:`86a9476a28cac1cdbadf801344e06903529f040670ea2d7f1455720b2acc12e0`.
- Checkpoint:`3cae71742bbc25577b9b45c3bae2521a3dca2579d9b5c57606531be09ac08c88`.
- State:`310ca55af66a5310c46b5ab8e2a364421117eed5fd5234892ec496f35e99996a`.
- Fresh read:map118,Champion and Hall-of-Fame facts concurrently present.
- Exact checkpoint/episode/state joins and all71 carried checkpoint bindings
  authenticated; zero-input/zero-frame save round trip verified.
- Specimen ledger hash unchanged at every final-episode step.
- Fresh saved-state supply read:30,418 currency,0 capture items; no input or
  frame advance. The dashboard now points to this Hall-of-Fame observation.
- Runtime teacher queries/fallbacks:0/0. Action-free preflight compared a teacher
  diagnostically; deterministic skills and operator-selected profiles remain.
- Strict admission reproduced the two sampled decisions and excluded the forced
  Champion step. No retroactive story target was invented.
- Internal independent read-only review agreed with the earned scope. No
  external Claude/Antigravity session or usage measurement was performed here.

The raw bounded-player result says `completion_satisfied=false` and
`stop_reason=decision_limit`. Those fields refer to the larger living-Dex
predicate and three-decision cap, not the story verifier. **92 required specimens
remain under the current declared collection contract.** The fields are retained
unchanged; living-Dex completion is not claimed.

## Training, not just demonstration

Native83 played the successful final episode. After admission, native85 was fit
once from the complete prior inventory plus its2 real recovery outcomes:84
comparative choices and1 historical guided outcome,43 successes,69 distinct
selected feature rows. All83 prior rows remain. Forced Champion remains excluded.

The updated artifact is
`bbb7a8528ddb88e054e5ebe8cff9a2a6bc0fcf1d2084bc7ed3f4a46df203b85c`.
It has **not** played. In-sample weighted error changed from
0.01160766048712076 to0.011611490387643562:slightly worse, not an improvement.
No authority promotion or generalization claim follows from this fit.

## What solved the last blockage

The PP-only profile had hidden the existing HP skill. A small explicit
composition restored both capabilities: HP first, PP only when HP has no legal
target or resource. No execution-error fallback, bag refill, boss-specific
target override or lowered safety guard was added. The last-Full-Restore reserve
is conditional: emergencies below halfHP/status may still consume it.

The previous Champion attempt is permanently retained:331 actions,25,998frames,
3 items,first3 opponents beaten,stop at Gyarados,0 faints,30 specimens. Its whole
trace remains quarantined and unfitted. Earlier failures are linked in the
public closeout receipt. This successor is correlated development, not a clean
counterfactual proving healing alone caused the win.

406 focused ROM-free tests, source type checks,Ruff,registry,docs,product-focus
and public-artifact checks passed before execution. Hosted CI is reported
separately; a local targeted pass is not a full-suite claim.

Closeout also passed171 focused dashboard,roadmap and product-state tests;
the actual dashboard reports85 samples and the verified Hall-of-Fame snapshot.
Hosted CI34363885441 for the preceding executable source passed. The victorious
source's CI34366478006 was still running at publication; it is not claimed green.

## Reorientation and next session

Story integration is now an earned intermediate result, not the final product.
Stop boss-controller work unless a new collection lesson demonstrates a specific
blocker. The next session is [Phase5 collection reorientation](../work-sessions/2026-09-09-phase5-collection-plan.md):
restore a usable post-game boundary without resets, audit the living collection
and legitimate supply, expose genuinely different attainable acquisition goals,
then let the model choose and retain the outcomes.

Do not claim the whole model is finished, all151 Pokémon available in Red,
fresh-game autonomy, learned combat, independent reliability or Crystal transfer.
The Red-era living collection, compatible unfamiliar Red hack, and Crystal remain
ahead in the unchanged long-term sequence.
