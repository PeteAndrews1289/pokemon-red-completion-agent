# Focused Astra review brief — Red battle learner

The implementation and negative-result packet are ready for a **design review**, not a model-promotion review. Review [the measured HP-pair pilot](../evidence/red-trainer-full-team-hp-pilot-2026-09-17.json) together with [the previous remediation](../evidence/red-trainer-astra-remediation-2026-09-17.json). Do not run gameplay, refit, reopen consumed DEVELOPMENT, or broaden this into a full-project audit.

## Decision evidence

- Eight prospective five-on-five TRAIN scenarios were measured from four clean-power origins. Each origin supplied a healthy/8-HP pair with only lead HP changed. The earlier 44 TRAIN contexts were authenticated and reused, not replayed.
- Switching was the best measured control choice in **all eight** new cases. The intended HP-dependent attack-versus-switch reversal never occurred. One attack-choice and one switch-target reversal appeared, but neither changes that control conclusion.
- The 300-epoch fit had move regret 0.1654 versus 0.1470 for always choosing the first move. A 2400-epoch refit on exactly the same records reduced move regret to 0.1200; no new gameplay occurred.
- On the *same original 44 TRAIN cases*, move regret rose from 0.0354 with the earlier 44-context model to 0.1392 with the 52-context refit. This is training interference, not held-out evidence.
- The previous frozen challenger already failed the predeclared correlated League comparison; five natural DEVELOPMENT battles and their shared historical origin are consumed. No new-origin natural evaluation was performed here. The older frozen control retains authority.

## Questions for Astra

1. What is the smallest prospective TRAIN recipe that yields actual attack-versus-switch reversals from one observable factor, while keeping the two alternatives viable? Examine the opponent/party balance before recommending more examples or larger models.
2. Does the three-head factorization need an explicit joint action-value or ranking objective to avoid attack-head interference, or is the failure better explained by the unbalanced 52-context curriculum and optimizer? Identify one discriminating ROM-free or bounded TRAIN test.
3. Which exact gate should precede a new-origin natural evaluation: reversal coverage, common-44 retention, and what thresholds? Avoid claiming generalization from TRAIN regret.
4. Is there any unresolved correctness or leakage issue in the five-on-five intervention/admission that would invalidate the negative result? Name a reproducible defect if so.

Requested output: a prioritized, bounded next action and a clear go/no-go condition. Current answer is **no-go on the 52-context fit and no promotion**. Keep the Red-first, legitimate Pokédex roadmap unchanged; do not start a full run on this result.
