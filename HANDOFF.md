# Current development handoff

Read [MISSION.md](MISSION.md), [NORTH_STAR.md](NORTH_STAR.md), and
[ACTIVE_PRODUCT_STATE.md](ACTIVE_PRODUCT_STATE.md). Updated September 17, 2026.

## Focused Astra review complete: repair targets before fitting again

The [focused review](docs/reviews/red-trainer-astra-focused-review-2026-09-17.md)
and [measured evidence](docs/evidence/red-trainer-astra-focused-review-2026-09-17.json)
identify two localized target defects. Averaging per-timing softmax probabilities
can favor a worse average-return action (five individual head examples do so).
Control targets take the best child action separately at each hidden timing,
creating an unattainable strategy; no current corpus control winner reverses,
but its values and diagnostics are optimistic.

The eight five-on-five HP cases have 260 matched branches, all truncated at
two player turns. They do not demonstrate full-battle opening values. Switching
wins all eight short-horizon contrasts even when timing maxima are corrected.
The failed recipe and its 52-context fit stay retained as negative evidence.

The earlier 44-context attack model has full-52 TRAIN regret 0.04475 versus
0.11999 for the new fit, and even slightly lower current-objective training loss.
Both have the same architecture. A capacity limit is not established. Complete
control-plus-child action regret improves overall (0.16086 to 0.14105), but
worsens on the new eight HP cases (0.26967 to 0.30542). These are TRAIN diagnostics.

## Next bounded work

Sol High, Fast off: repair aggregation of raw returns before softmax, average
each actual action before control maxima, add mathematical regressions, and
report the actual composed action's regret. Version the target derivation and
preserve historical receipts. Reuse authenticated TRAIN records for one fit;
no new gameplay is needed for this first step.

Proposed gates: original-44 attack regret <=0.0554, full-52 attack regret
<=0.0648, and composed-action regret on the 44 control contexts <=0.1609.
See the review for definitions and the four-scenario, two-member-versus-one
terminal HP pilot that follows only after those gates pass. No standing Astra
review is required after these specific repairs; escalate a failed falsifier
or a material architectural decision.

## Preserved authority and boundaries

The earlier [mechanics remediation](docs/evidence/red-trainer-astra-remediation-2026-09-17.json)
remains in place. The 44-context model won five natural DEVELOPMENT battles,
but failed the predeclared correlated League comparison. Those battles remain
consumed, share unresolved historical ancestry, and cannot be replay-tuned or
used in fitting. A genuinely new-origin natural comparison remains necessary.

Older frozen control retains authority. Model137 stays 137 examples / 92
successes / 58 economy-qualified; Red stays 96/124; fresh acceptance stays 0/5.
This review made no gameplay actions or fits. Gameplay is stopped. No full
game, ROM hack, Crystal work or GitHub push occurred. Pete decides publication.
