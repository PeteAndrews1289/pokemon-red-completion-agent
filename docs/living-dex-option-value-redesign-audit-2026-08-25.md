# Living-Pokédex option-value redesign adjudication — 2026-08-25

Audited baseline: clean published `main` at
`dee52ff2ad6b6561fcecd447db891715b0664b2a`.

Review roles followed [the three-agent workflow](three-agent-workflow.md): Claude performed the
causal/statistical audit, Antigravity 3.7 Flash High challenged architecture and transfer, and Codex
adjudicated. Both external reviewers were read-only. No ROM, private context, teacher, model fit,
prediction, controller input, root claim, sealed Red case, or Crystal case was opened.

## Verdict

**Redesign before collection. Do not freeze or execute the proposed V4 curriculum.**

The previous four-feature binary head cannot support a valid living-Pokédex learning claim:

1. `DependencyTrainExample` makes failure of the selected arm a preference for the never-executed
   alternative. The settlement observer is honest; fabrication occurs at the fit and comparison
   boundary.
2. The candidate difference vector has only two reachable shapes and cannot express travel,
   capture/evolution effort, resources, storage, safety, irreversibility, uncertainty, or downstream
   value.
3. The freezer controls assigned-action balance while the fitter requires an exact reward and
   preferred-action balance. Outcomes cannot be prospectively balanced; selecting eight of twelve
   rows after seeing results would leak outcomes.
4. V4 had no implementation capable of 12+8 reserve semantics, observed-arm fitting, multiway menus,
   or Crystal adaptation.
5. Applying one-shot source/CI/root ceremony to routine development contradicted the repeatable
   development contract and left the current living-Dex learner at zero causal train examples.

## Codex decisions

- **Accepted:** retire V4 before freeze; replace counterfactual preference labels; enrich the shared
  representation; use repeatable development scenarios; preserve symbolic invariant masks; add a
  matching Crystal adapter only after a within-Red outcome gate.
- **Modified:** support genuine variable-size menus rather than manufacturing a third option; retain
  the historical binary ranker for evidence reproducibility but remove it from the active path.
- **Rejected:** fixed sample counts proposed without pilot variance; “agreement with optimal choices”
  as the transfer criterion; deleting historical evidence-bearing code immediately.
- **Deferred:** the narrow cross-registry root-claim atomicity repair belongs in the replacement
  collector. No further old-V4 collector work is justified.

## Replacement

The ROM-free shared contract in
[`living_dex_option_value.py`](../src/pokemon_red_completion/living_dex_option_value.py) now supports
variable menus, hard masks, title-neutral normalized features, full behavior distributions, censored
outcomes, capped inverse-propensity weighting, arbitrary observed outcome mixtures, separate benefit
and cost heads, and model records with zero unselected-action targets.

The immediate next gate is a repeatable Red adapter and calibration scenario lab. It is not a sealed
campaign and does not claim authority or transfer.

## Post-implementation review and adjudication

Claude Opus returned **GO-WITH-FIXES** with no P0 finding. Its only P1 was valid: every original
fixture used a uniform behavior distribution, so deleting the reciprocal propensity or its cap
would have left the suite green. Codex accepted the finding and added non-uniform selected-arm
cases that distinguish the weighted fit and evaluation from unweighted arithmetic, directly test a
cap-saturating arm, and allowlist every policy projection key. Claude's P2 cautions about in-sample
MSE, informative censoring, cap bias, and context/menu sampling bias are now explicit in the shared
contract and required calibration report.

Antigravity Gemini 3.7 Flash Medium returned **GO** with no P0. It correctly noted that eight pilot
examples cannot identify 25 parameters per outcome head, that the original feature standardization
was unweighted while the ridge objective was propensity-weighted, that fixed row ordering could
become a tie policy, and that the first fixture exercised only four of eight portable option kinds.
Codex accepted the weighted-standardization repair and added a discriminating regression; added an
eight-kind non-degenerate menu test; documented replayable neutral ordering; and retained the
eight-example minimum only as an underdetermined integration/variance pilot. A larger or more
complex estimator remains deferred until repeatable Red variance exists.

The final ROM-free boundary has **18 focused tests**. It still creates zero gameplay outcome,
learner authority, or transfer evidence. Both reviewers agree that the next engineering gate is the
repeatable Red adapter and bounded scenario collector, not another one-shot freeze.
