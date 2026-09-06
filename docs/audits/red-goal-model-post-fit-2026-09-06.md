# Red goal-model post-fit audit — September 6, 2026

## Verdict

**The real collection and single model update completed.** The result supports train-only
calibration of the living-Dex option-value scorer; it does not establish independent gameplay,
full-player authority, Pokédex completion or Crystal transfer. The next session should make this
specific artifact choose successive supported Red goals, not collect more qualification receipts.

## Verified evidence

Source `e9b381d0bafb114ce3a0ad08b4ed77d95926bb97`, merged PR 230, was qualified by exact-main
CI `34019391472` attempt 1. PR and main passed the full test check; the PR test result was
6,899 passed, four skipped and one expected failure. The actual process exited successfully.

The results/documentation follow-up passes all 100 product-focus tests, documentation links,
public-artifact checks, lint and the unchanged generated collection registry. No executable
gameplay source was changed by this post-fit documentation update.

| Measure | Verified result |
| --- | --- |
| Scheduled/terminal train lessons | 8/8 |
| Factual examples / setup censors | 6 / 2 |
| Scheduled roots / roots with factual rows | 4 / 3 |
| New actual kinds | Acquisition 2, party development 3, resupply 1 |
| New verified successes / failures | 5 / 1 |
| Controller actions / emulator frames | 20,312 / 1,127,136 |
| Actual model fits | 1 |
| Previous fit / saved corpus before run / updated fit | 18 / 23 / 29 examples |
| Successful examples in full corpus | 12 / 29 |
| Distinct selected-feature rows / represented kinds | 24 / 7 |
| Weighted MSE, prior then updated, on the same 29 train rows | 0.0069591 → 0.0050046 |
| Changed choices on training menus | 3 |
| Gameplay model predictions during collection | 0 |
| Development examples read / teacher queries / Crystal accesses | 0 / 0 / 0 |

The fit objective is `selected-arm-capped-ips-multioutcome-ridge-v1`: a small option-value model,
not an LLM. The collector used its disclosed 98:1 focus policy and deterministic execution.
The approximately 28% error reduction is **in-sample calibration**, not held-out accuracy.
The three training-menu disagreements are diagnostic predictions, not executed learned actions.

The separate read-only audit reloaded all 29 authenticated train rows, matched every one of the
23 pre-run fingerprints unchanged, and authenticated the new model, fit manifest, record and
dataset binding. It performed zero fits, predictions, controller actions or game frames.

Model SHA: `bbd36e556bd57a3afb212d0f2a4fd3360336bd17afaefe92a31a72c60a17d01a`.
Record SHA: `d831fdcf61f9eacfe8c23faaa0736feb1779f364edf8b6e7f89c3bee101ce010`.
Manifest SHA: `c6a5652b08a92c4c3b9f966a2a799c9edec3b4aef31ce4eff80882877d3bfa60`.

## Open findings

1. **Actionable setup diagnostics are incomplete.** Ordinals 5 (development) and 6 (storage)
   failed on the same physical root during `construction_route`, both labeled `unexpected_error`.
   Each retained 1,071 setup actions and 54,984 setup frames. Neither terminal retains the original
   exception, so the exact cause cannot be reconstructed from these records. Add private bounded
   diagnostic detail for future executions; do not retry or rewrite these consumed trials.
2. **Breadth remains limited.** The new three successful party-development rows are the first such
   successes in this learner corpus. Evolution, exploration, storage and access unlocking still
   have no successful examples here. That is missing learning evidence, not proof that every
   associated executor is broken. Repeated lessons from one root are clustered experience.
3. **The updated artifact has not played a new goal sequence.** It remains
   `non_authoritative_shadow_only`. No paired-development outcome was opened in this batch.
   Four reserved paired roots can provide descriptive engineering evidence, not a 5% superiority
   claim even if all four non-tied comparisons win. Do not demand an impossible statistical gate
   or promote full-player control from a training diagnostic.
4. **Overview presentation can mislead.** The work card reflects the completed batch, but the
   overview still contains hard-coded historical labels/counters. Its replacement should consume
   actual job, actor and result state. The cumulative cross-family scorecard is a separate older
   verified ledger, not this learner's 29-example corpus or an updated project-wide total.

## Preservation and next decision

All eight trials and the prior ten-trial campaign remain terminal. Preserve all negative examples,
setup censors, original plan, prior artifacts and account-wide claims. Four paired roots and one
reserve remain unexecuted; they are not replacements for bad train outcomes. The campaign and its
temporary live dashboard ended normally; no game or fit is currently running from this job.

Proceed with the [bounded-play plan](../work-sessions/2026-09-06-red-closed-loop-next.md): bind the
named scorer, make the short descriptive comparison, then chain supported goals with fresh state
and verified living-ledger progress. Keep deterministic safety/skills explicit, limit engineering
to this direct playing loop, and reassess after two–four hours. Crystal remains deferred while the
shared semantic boundary is preserved. No external reviewer or subagent audited this session.

Sources: [actual campaign/fit result](../evidence/red-retired-bank-train-and-fit-result-2026-09-06.json),
[read-only audit](../evidence/red-retired-bank-post-fit-audit-2026-09-06.json).
