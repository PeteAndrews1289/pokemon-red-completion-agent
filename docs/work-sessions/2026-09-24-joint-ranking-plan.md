# Joint ranking correction — prospective plan

User authorizes continuous implementation, one fit, and conditional comparison.
No conversational stage boundary is required. No promotion or campaign inputs.

## Mission check

- Capability: retained outcome-trained reserve selection after attrition.
- Learned authority: same neural switch/control heads; no action overrides.
- Transfer test: original untouched 24 teams × three timings × three actors.
- Cheapest falsifier: synthetic conflicting lessons, large wrong/tiny old margins,
  actual corrected decisions, and bounded honest local obstruction.
- Time box: implementation/tests reassessment within90minutes; one fit capped
  at600direction attempts and1800seconds per head; comparison capped3600seconds.
- Stop: failed method tests, unresolved measurement/architecture decision, failed
  frozen fit, censored comparison or original comparison failure. No blind refit.

## Method fixed before private fitting

Opt-in `joint_ranking_v1`; defaults unchanged. Cycle through incorrect fresh
examples deterministically, giving each at most40accepted directions per visit.
Select its highest-scoring measured-best alternative versus current choice.
Jointly solve a linear program for useful ranking progress within parameter
trust bounds and all distinct retained worse-choice margin constraints. These
are conservative local guards, NOT the numeric mean budgets or a global
infeasibility proof. Old wrong choices remain free to improve. New worse-choice
guards prevent forgetting already learned fresh decisions.

First maximize useful margin progress. Then minimize L1 displacement retaining
90%of that progress, capped at the correction's required margin plus0.1.
Guard floors retain half the current margin up to0.05. Use HiGHS with explicit
finite residual, iteration and time checks. Each parameter trust radius0.05;
up to8trust-region halvings per attempt, solving the joint problem anew.
Accept only exact nonlinear original numeric budgets, nonincreasing fresh
selected regret and strict improvement of the focused margin. Keep every
accepted parameter checkpoint plus solver residuals, binding constraints,
target choice/score changes, rejection reasons and actual costs.

If a focus cannot advance, try the other lessons without restarting weights.
Stop after a full sweep without accepted progress or all fresh choices optimal.
Select best feasible fresh actual regret, then expected regret, then earliest.
No requirement for100%wins or perfect training choices. No target IDs, species
or slots in the optimizer. Replay supplies constraints, not a competing shared
gradient; every original group/offset/multiplicity remains independently checked.

One declared schedule:600attempts/head, radius0.05. Fit switch, rebuild all
control proposals, then fit control. Same9late targets,36prior contexts,
18groups/35checks,591unchanged status choices; frozen damage/status features.
Original new-switch nonincrease and full-control10%improvement gates unchanged.
Independently audit saved checkpoints and final model before any comparison.
No new labels, opened-evaluation replay, parameter sweep or architecture change.

If passed, execute original216battle packet against deployed and parent models.
Retain losses, costs, invalid choices and risk; independently verify events and
terminals. Original win/cost/risk rules govern qualification. Campaign461 and
deployed actor remain protected, irrespective of result. No GitHub publication.

Solver reference: [SciPy HiGHS documentation](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html).
