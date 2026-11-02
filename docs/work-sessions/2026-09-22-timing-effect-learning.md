# Timing-aware effect learning — September22,2026

## Prospective mission check

1. Capability: distinguish decision-time HP from healing opportunity after opposing damage.
2. Learned authority: train one auxiliary probability predictor from measured native effects;
   no battle-choice authority is promoted in this packet. This unblocks the existing selector seam.
3. Transfer: reserve variant2/level40 on the fourth authenticated TRAIN root; fit variants0/1
   on three other TRAIN roots. Same source bank, not independent natural or cross-title transfer.
4. Cheapest falsifier: measured full-HP healing after faster opposing damage is absent on any
   fitting root, or the one fitted predictor fails the unused timing/condition configurations.
5. Time box:60–90minutes;84single-turn episodes,420000frames,one fixed logistic fit.
6. Stop: missing measured coverage, authentication failure, budget exhaustion, optimizer failure
   or reserved-test failure. Keep all attempts; no replacements, tuning or selector fit.

## Frozen design

Seed2026092207.72fitting turns and12reserved turns. Recover, Rest and Confuse Ray
each cross two conditions and both speed orders on every root. Fitting uses two recipe
variants; reserved uses a third. Healing contrasts full versus75%HP; confusion contrasts
clear versus occupied. Rest injured cases additionally start burned, as in the prior packet.
Choose a single ordinary, nonpriority, no-secondary-effect damaging enemy move with native
stats; prospective enemy selection uses speed/stat/type metadata only, never outcomes.
Enemy moves have35–60power and≥95%nominal accuracy; misses remain recorded. Select
the closest available native speed margin to±.15/±.60 for training variants and±.35
for the reserved variant, with magnitude .10–.80 and level within8of the actor.
Use the unchanged28observable features and existing logistic objective:zero initialization,
L2=.001,max500iterations,ftol1e-12. No old measured or failed qualification labels enter fitting.

Before fitting, require all12order/family/condition cells observed on every fitting root,
both measured labels per family/root, visible speed sign matching the constructed order,
and an observed full-HP healing success after opposing damage for Recover and Rest per root.
Unknown/suppressed outcomes remain retained, not negative labels. No post-outcome replacement.
Reserve cases are not played until the one fit is frozen. Require the same coverage on the
reserved root, aggregate Brier≤.125 and≤90%of training-prevalence baseline, with no family
or speed-order Brier regression against that baseline. Report classifications, not only averages.

No runtime masks, hidden timing/RNG features, weakened raw-concern gate, campaign input,
live promotion or old128battle-comparison access. Preserve cad523f4 and the12consumed
later-turn checks. All teacher memory interventions are isolated TRAIN setup only.

## Result: bounded timing test passed

Source freeze45810b93; private packet red-timing-effect-learning-20260922-v1.
All84turns completed in12.675seconds:111648frames,588event records, zero invalid
actions, unknown effects or execution suppressions.56effects applied and28had no effect.
All36fitting cells and12reserved cells had measured support. Full-HP Recover/Rest
after opposing damage was observed on every root. No replacement cases or retries.

One36iteration logistic fit used72labels, representing24distinct observable vectors
replicated across three roots. Reserved configurations supplied12different vectors;
zero feature-vector overlap. Weights froze before any reserved episode ran.

| Reserved group | Correct | Brier | Training-prevalence baseline |
| --- | ---: | ---: | ---: |
| All | 11/12 | 0.034718 | 0.222222 |
| Recover | 3/4 | 0.069142 | 0.194444 |
| Rest | 4/4 | 0.032980 | 0.194444 |
| Confusion | 4/4 | 0.002032 | 0.277778 |
| Actor first | 5/6 | 0.055255 | 0.277778 |
| Opponent first | 6/6 | 0.014181 | 0.166667 |

All predefined gates passed. The full-HP opponent-first cases predicted application
at93.75%for Recover and71.99%for Rest; both actually healed. The retained mistake is
actor-first full-HP Recover: predicted52.22%, actual no effect. Do not refit on it.
An explicitly post-hoc read-only comparison of old cad523f4 on these same12new cases
gave10/12correct,Brier0.160525. It did not influence selection or replace the frozen gate.

The independent read-only audit regenerated all recipes, reopened84capture manifests,
verified84event chains and episode/trace joins, reproduced every saved measured row
and metric, and checked fit-before-reserved execution. Story, primary, Model141,
K, old predictor and failed prior qualification hashes remain unchanged.
553targeted tests passed;13private-integration tests skipped. Ruff, registry and
documentation checks pass. This was one auxiliary fit, not a full battle learner fit.

## Boundaries and next step

Predictor8ac8c2d5 is eligible for a new bounded selector-integration experiment,
not live battle control. Three effect families, ordinary priority-zero enemies,
assisted first-turn states and reused TRAIN ancestry remain explicit limitations.
Successful application is not strategic value or probability of execution.
No new battle choices, selector fits, actor promotions or registrations occurred.

Next freeze this predictor; choose unused later-turn TRAIN cases prospectively,
excluding the12consumed prior checks. If it passes, use the existing one-fit selector
seam with182retained preferences/rewardv2 and a bounded native TRAIN screen under
unchanged readiness. No raw-concern exemptions or128old-comparison access.
Budget60–90minutes for that bounded packet, not Giovanni completion.

[Path-free evidence](../evidence/red-timing-effect-learning-2026-09-22.json) pins the
plan, training, coverage, predictor, inventory and results. All jobs/gameplay stopped;
no GitHub publication or external models. Next:Astra High,Fast off for integration
and honest qualification, not another auxiliary refit.
