# Astra focused review — September 17, 2026

Reviewed `e8148510`. **Repair two target-construction defects before the next fit.** Keep the small, separately trained heads and the existing battle factory. The failed pilot supports no promotion, but does not justify a larger model or a rewrite of the battle system.

[Measured evidence](../evidence/red-trainer-astra-focused-review-2026-09-17.json). This review reconstructed the 52 TRAIN contexts and their 260 timing records from authenticated branch evidence, evaluated existing weights, and ran 22 focused tests. No gameplay or fitting occurred. Tests pass but do not test the mathematical contradictions below. Existing DEVELOPMENT results were not reopened.

## R1 — High: soft targets can reward the worse average action

`_soft_return_target` in `src/pokemon_red_completion/red_trainer_practice_fit.py:313` computes a softmax separately for each timing and averages the probabilities. The measured regret instead uses average returns. These operations do not preserve the same ranking. `_combine_identical_inputs` then averages already-transformed probabilities across repeated inputs, retaining the mismatch.

Five individual head examples disagree by more than the existing 0.02 return tolerance: attack contexts 19 and 28, and switch contexts 47–49 (zero-based corpus indices). At context 47, the four switches have average returns **−0.7468, −0.4084, −0.8685, −0.2379**, but target probabilities **0.3539, 0.3007, 0.0279, 0.3175**. The optimizer is encouraged to prefer the first switch even though the fourth is better by **0.5089** average return. This is a target-objective contradiction, not evidence that the model cannot learn.

Repair: aggregate raw measured returns per observable candidate across the declared timings and equivalent inputs, with explicit weighting, before applying a softmax to the means. Preserve spread and timing counts separately. A common positive temperature can soften uncertainty while preserving the expected-return ordering. If risk sensitivity is desired, define a risk-sensitive utility explicitly and evaluate the same utility; averaging per-timing winner probabilities is not a substitute. Version the target derivation and retain earlier models/receipts unchanged.

## R2 — High: control targets assume access to hidden timing outcomes

`_observed_returns` at lines 296–307 chooses the best attack and best reserve **separately inside each timing**. It therefore values a switch strategy that can change its reserve after learning the hidden RNG outcome. A real actor must choose one reserve from the observation.

A ROM-free reproduction uses an attack worth 1 at all five timings and two switches with returns `[2,2,-2,-2,-2]` and `[-2,-2,2,2,2]`. Their achievable mean values are 1, −0.4 and 0.4: attack is best. Current code assigns switch value 2 at every timing and gives switching **0.999955** target probability.

The actual corpus has **zero** control winner reversals greater than 0.02 caused by changing mean-of-maxima to max-of-means. Thus this defect does not explain away the eight all-switch HP labels. It does inflate their value: at context 44, best achievable mean switch return is −0.2467, while mean timing-wise best switch return is −0.0069. This defect matters before adding more varied switch alternatives.

Repair: average each actual action first, then compare the best mean attack with the best mean switch. Use the same computation for labels and diagnostics. Also report the return of the action selected by the complete control-plus-child policy; a correct group decision can still choose a bad reserve. This requires no shared or joint neural network.

## R3 — Medium: the five-on-five curriculum still has a two-turn horizon

`scripts/run_red_trainer_practice_baseline.py:340` and `:403` hard-code a two-player-turn matched horizon. All **260/260** new branches stopped at that budget; none reached battle victory or defeat. The surrounding standalone baseline can run longer, but those longer runs are not the matched labels used by this fit.

The measured negative result remains valid for this short horizon: all eight configurations favor switching even after fixing the timing-wise maximum. It does not establish the best full-battle opening or the benefit of preserving a healthy lead for later opponents. Adding four reserves also changes the party-HP normalization and the number of possible switches while leaving the lookahead at two turns.

Next recipe: use two player members against one opponent. Configure the active member to move after the opponent, survive its hit at healthy HP and then finish the foe; critical HP should fall below that incoming hit. Provide a durable reserve that survives switching in and can win with an extra turn. Keep everything but lead HP identical within each pair. Verify the actual outcomes rather than assuming these labels. Use two distinct matchups and five declared timings per case, with a common four-player-turn horizon and retained failures. This gives four scenarios, not another broad five-on-five batch.

## R4 — Medium: the fit result does not establish a capacity bottleneck

The three heads have separate parameters and independent training calls. Each fit starts from seeded random weights, so the 44-to-52 comparison is not a sequential fine-tuning experiment. The observed loss of prior attack skill is real; its cause remains unresolved among target weighting, optimization and representation.

On all 40 attack examples in the 52-context corpus, the earlier model has regret **0.04475**, versus **0.11999** for the newer fit. On the 28 unique attack inputs under the current soft targets, the earlier model also has lower cross-entropy: **0.818024 versus 0.819638**. Existing weights within the same architecture already achieve a better result. A fixed epoch count did not establish convergence.

The complete control-plus-child choice has a mixed result: mean regret across 44 control contexts improves **0.16086 → 0.14105**, while the eight new HP cases worsen **0.26967 → 0.30542**. The near-zero reported control-head regret omits errors in the chosen reserve. Neither one favorable head nor the attack regression alone describes the whole policy.

After R1/R2, compare the two retained models against the corrected objective, then run one declared fit that logs initial/final loss, gradient magnitude, common-44 regret, new-case regret and composed-action regret. Keep the 16-unit architecture initially. If necessary, a single prospectively bounded continuation from compatible old weights distinguishes insufficient optimization from a cold-start failure; do not infer a need for more capacity from another arbitrary epoch cap.

## Concrete gates and work order

1. **One implementation session, initially ROM-free:** fix R1/R2, add their mathematical regression cases, and verify that target argmax agrees with the declared mean-return objective for every combined observable input within 0.02. Add composed-action diagnostics. Re-derive TRAIN targets from retained branches and fit once. This requires no new cartridge data.
2. **Retention gate:** on the original 44 cases, attack regret must be at most **0.0554** (the old 0.0354 plus the existing 0.02 tolerance); on all 52 contexts, attack regret must be at most **0.0648** (old 0.0448 plus 0.02). On the same 44 control contexts, composed-action regret must be at most **0.1609**, the old model's measured value. These are proposed engineering gates for the next experiment, not statistical generalization claims.
3. **Bounded four-scenario pilot:** each of two HP pairs must have opposite measured switch/stay winners, with an average-return margin above **0.10** in both directions. Require terminal outcomes within the common horizon for all compared branches; retain truncations as failures of this recipe. The learner must select the intended group and a child action within **0.02** of the best measured action in all four cases, while retaining the original attack gate. Preserve all cases; do not filter unfavorable pairs out of the corpus.
4. **Then evaluate natural play:** freeze the challenger and a new-origin natural cohort prospectively, with the older frozen control and declared win/faint/HP/action metrics. Meeting the TRAIN gates is permission to test generalization, not proof of it. Full Red play still depends on the separate project gates.

No additional standing Astra review is required after these specific repairs and tests. Escalate only a failed falsifier or a material architectural decision. Gameplay is stopped; learning, registration and authority counters are unchanged. Recommended implementation setting: **Sol High, Fast off**, because the immediate work is two localized target fixes and measured diagnostics.
