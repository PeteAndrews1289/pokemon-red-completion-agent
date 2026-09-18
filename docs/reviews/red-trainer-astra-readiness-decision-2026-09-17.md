# Astra readiness decision — September 17, 2026

Reviewed source `886cd343d893ca9d4ea8c5467ee1a31de8254068`.
**Keep the framework; freeze the older attack head and combine it with the
corrected control/switch heads. Stop refitting attacks on these same 52 cases.**
The system already collects outcomes and fits real models. The resulting battle
policy is not yet qualified for final-player authority.

[Measurements](../evidence/red-trainer-astra-readiness-decision-2026-09-17.json).
This review reconstructed retained TRAIN evidence, evaluated existing components
in memory, inspected source and ran 34 focused tests. No fit, composite model
artifact, gameplay or DEVELOPMENT evaluation was created.

## Measured successor to the retention failures

| Existing gate; lower regret is better | Ceiling | Read-only composition |
| --- | ---: | ---: |
| Attack regret on original 44-context corpus | 0.0554 | 0.035384769 |
| Attack regret on all 52 contexts | 0.0648 | 0.044750856 |
| Actual control-plus-child regret on 44 control contexts | 0.1609 | 0.112597023 |

All three pass without changing thresholds. The full corpus contains 40 attack
examples and 28 distinct attack input matrices, not 52 distinct attack lessons.
The composition uses the older 44-context attack head and corrected cold-fit
control/switch heads. The older full policy's composed regret was 0.160857928.
These are TRAIN engineering diagnostics, not held-out performance.

Package one composite artifact with authenticated per-head model/receipt hashes
and lineage. Verify schemas, legal-candidate compatibility, serialization and
actual policy loading. Assert unchanged attack weights and reproduce these gates.
Reuse corrected control/switch weights rather than rerunning their unchanged fit.
Both failed attack fits remain failures. Freezing preserves case 43 without a
case-identity exception; it does not establish generalization. Retire the current
same-corpus attack-refit recipe, not future attack learning. A return-sensitive
objective is a later bounded option if new TRAIN decisions show it is needed.

## Reproduced source defect — fix before the next fit

`build_refit_plan` in `scripts/refit_red_trainer_practice_outcomes.py` copies
`**previous` and overwrites warm-start fields only when new arguments are supplied.
A new plan with warm-start arguments omitted therefore silently retains a prior
warm model, receipt and 100-update schedule. I reproduced this without file writes.
Existing tests do not cover warm-to-cold plan construction. Clear inherited mode
fields before applying explicit options, or reject ambiguous inheritance; test
warm-to-cold and replacement-model transitions. This did not cause the previous
measured failure, whose continuation was explicitly requested.

## Remaining learning and qualification work

1. **Terminal HP curriculum:** the eight latest HP scenarios all favored switching;
   all 260 matched branches truncated at two player turns. Keep the already
   proposed four-scenario pilot: two different matchups, healthy/critical lead
   pairs, two own members versus one foe, five timings and a common four-turn
   horizon. Measure rather than prescribe labels. Require terminal outcomes in
   every compared branch and an attack/switch preference reversal in both pairs,
   with mean-return margins above 0.10 in both directions. Retain failed recipes.
2. **Learning and unseen variation:** freeze attacks and train switching components
   as needed on the pilot. Require the actual selected action within 0.02 of best
   in all four TRAIN cases, retaining the three original corpus gates. Reserve
   a small distinct-species/level/HP variation set before fitting; freeze its
   parameters, metrics and resource cap before predictions. Do not fit its
   failures. Replaying the four trained cases alone does not check overfitting.
3. **Natural qualification:** inventory genuinely new-origin natural sources
   outside TRAIN and the consumed historical cohort. This review verified none.
   Freeze a small challenger/control comparison, battle count, budgets and pass
   thresholds prospectively. Use meaningful, non-overleveled choices; require
   wins without teacher substitution, illegal choices or unhandled boundaries,
   and compare faints, HP/PP, actions and useful switching. Historical League
   results remain correlated, failed/consumed and unavailable for tuning. If
   new sources require a broader progression campaign, report its cost and seek
   direction rather than silently rebuilding a teacher factory.

## How far away

- **Training infrastructure:** operational for the declared damaging-move and
  switching segment. Training has already begun; we are qualifying what it learns.
- **Next useful experiment:** one small implementation block for authenticated
  composition, the inherited-settings fix and terminal-pilot support. Plan one
  focused session, capped at two hours, ending in a measured pilot or specific
  failed prerequisite rather than another general review.
- **Qualified narrow battle segment:** three work blocks remain: package the
  candidate; demonstrate terminal HP-dependent learning plus unseen variation;
  pass independent natural comparison. Budget roughly 2–4 focused sessions only
  if suitable natural sources exist and gates pass. Source availability and
  learning success are unresolved; this is not a completion deadline.
- **Complete battle mastery:** not this segment. Non-damaging/status moves,
  recovery/boost choices, Counter, self-destruct and all-party attack depletion/
  Struggle remain outside the actor's supported surface. Repeated voluntary
  switching is still masked until an attack. All 151 configurable species does
  not mean all battle mechanics learned. Expand and test those explicitly later.
- **Final Red player:** sustained battle/story integration, navigation/goal
  composition, legitimate resources and remaining collection work still apply.
  Development registration is 96/124 (28 missing); fresh acceptance is 0/5.
  Neither is a whole-project completion percentage or remaining-time estimate.

Do not add another automatic Astra review between a passing package and its
bounded pilot. Escalate a failed predeclared gate or material design change.
No new learner authority or transfer result occurred; gameplay stays stopped.
Recommended next implementation setting: Sol High, Fast off.
