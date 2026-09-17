# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Astra review complete: repair feedback before larger training

The [review](docs/reviews/red-trainer-astra-review-2026-09-17.md) and
[measured evidence](docs/evidence/red-trainer-astra-review-2026-09-17.json)
review local commit `5127cef4`. Keep the emulator factory, provenance, branch
logs, actor/executor separation and small three-head model. No wholesale
architecture replacement is justified by the current data.

Four fresh TRAIN source chains and all 140 timing trials / 500 branches passed
existing admission on reconstruction. However, the 28 scenarios contain only
four unique attack-input matrices, five control matrices and seven switch
matrices. The attack model's 14/16 training winner hits equal always choosing
the first candidate; some identical inputs have conflicting winner labels.

Repair before a larger training campaign:

1. Preserve damage across living opponent switches. The current return scorer
   loses 52/83 damage on the first Fuchsia control attack and slightly reverses
   control/challenger reward ordering. Original wins, HP and action counts are
   valid. This switching pattern was absent from the 500 TRAIN branches.
2. Match training and live history inputs: 57 history-related weight rows are
   untouched random initialization, yet live history affects scores. Also fix
   history identity for different opponents sharing species and level.
3. Reconcile generation and model move support: Counter passes the scenario
   support rule but stops feature projection. Explicitly declare attack/switch
   scope; status, recovery and all-party Struggle remain unsupported.
4. Build distinct paired TRAIN decisions and uncertainty-aware repeated targets.
   Count unique inputs and compare simple controls before expanding the fit.
5. Freeze one challenger for a prospective natural cohort with useful choices.
   Easy battles require no regression; harder declared slices require benefit.

The two consumed natural DEVELOPMENT comparisons remain negative evidence,
not material for tuning or replay. Celadon used the 16-context challenger;
Fuchsia used the 28-context challenger. Both won less efficiently than controls,
neither voluntarily switched, and the captures share historical ancestry.
The current 28-context model SHA-256 remains
`686361c0b4ca1852e1d2576819096db5f7886d617b9e00846c7970b69d8f0f38`.

Review verification: 38 focused existing tests passed; code defects above were
reproduced from retained evidence, not fixed during this review. No new model,
gameplay, authority promotion, cross-title transfer or GitHub push occurred.
Model137 remains 137 examples / 92 successes / 58 economy-qualified outcomes;
Red stays 96/124 and fresh acceptance 0/5. Pete decides publication.

Next: Sol High, Fast off, for scoring/history/support repairs with focused
regressions (estimated one to two implementation sessions), then a small
distinct-curriculum pilot. Do not make another general review a standing gate.
