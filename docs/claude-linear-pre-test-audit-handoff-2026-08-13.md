# Claude Handoff: Linear Ranker and Sealed-Test Repair Audit

## Authority and stop line

Audit the capacity repair and the ROM-free sealed-design finding. Do not open, materialize,
preflight or execute any private test capture. Do not inspect live test route costs or run the model
on a test policy input. If the implementation is wrong, preserve both development candidates and
repair under a new source identity.

## What changed after your audit

Your three findings were accepted.

1. The validation-selected MLP remains preserved but is superseded. It has no test or live
   authority.
2. A deterministic shared linear scorer was added. It fits five coefficients, has no intercept,
   and scores candidates independently so candidate permutation remains equivariant.
3. Model family, feature subset and L2 are selected only from 24 training examples using
   leave-one-out evaluation plus a one-standard-error simplicity rule. Validation is absent from
   the selector API.
4. A separate public-metadata audit proves the existing test design declares zero challenge
   hypotheses even though ten test frontiers could structurally support one. It explicitly does not
   claim those ten are measured baseline disagreements.
5. A replacement one-shot plan assigns new case identities, preregisters all ten eligible origins,
   binds the exact model/source/evidence digests and defines conservative scoring. It is prospective
   only and requires this audit plus owner authorization.
6. Test remains 0/12 opened, and the fit receipt marks sealed-test readiness false.

## Frozen results to reproduce

- Linear model ID: `pokemon.core.strategic-navigation.destination-ranker.linear.v1`.
- Enabled features: the relative ranks of route cost, route steps, map transitions, field actions
  and mode changes.
- Fitted parameter count: 5.
- Selected L2: 0.1; training epochs: 600.
- Training-only leave-one-out: selected feature set 16/24; best large set 17/24; one-standard-error
  threshold 0.6155528526674487.
- Development validation: 10/12 model, 4/12 cheapest route, paired wins/losses 6/0, exact two-sided
  p = 0.03125.
- Canonical model digest:
  `753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1`.
- Private model-file digest:
  `6ef826bc92fae3092e9ccaefaad4107a687a564f7d35818f844fadba68540cdd`.
- Sealed design: 12 public scenarios, 0 declared test challenges, 10 structurally eligible, 0
  private inputs accessed.
- Replacement plan digest:
  `ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b`;
  12 cases, 10 preregistered challenges and 0 private inputs accessed.

Private ROMs, checkpoints, episodes and the model stay outside the repository. Never place their
locations in a tracked or untracked file.

## Read first

1. `MISSION.md`
2. `AGENTS.md`
3. `AGENT_COORDINATION.md`
4. `src/pokemon_red_completion/strategic_navigation_model.py`
5. `src/pokemon_red_completion/strategic_navigation_test_design.py`
6. `scripts/fit_strategic_navigation_model.py`
7. `scripts/audit_strategic_navigation_sealed_design.py`
8. `tests/test_strategic_navigation_model.py`
9. `tests/test_strategic_navigation_test_design.py`
10. `docs/evidence/strategic-navigation-linear-development-2026-08-13.json`
11. `docs/evidence/strategic-sealed-test-design-audit-2026-08-13.json`
12. `docs/evidence/strategic-linear-and-sealed-design-mutation-audit-2026-08-13.json`
13. `configs/red-strategic-navigation-sealed-evaluation-v1.json`
14. `scripts/regenerate_strategic_navigation_sealed_evaluation_plan.py`
15. `tests/test_strategic_navigation_sealed_evaluation_plan.py`
16. `docs/evidence/strategic-sealed-evaluation-plan-freeze-2026-08-13.json`
17. `docs/evidence/strategic-navigation-linear-reproduction-audit-2026-08-13.json`

## Adversarial targets

1. Let validation or test enter linear fitting or selection. Every variant must fail.
2. Change leave-one-out to train-on-self evaluation, omit a fold, or duplicate a held-out row.
3. Change the one-standard-error subtraction, parameter-count priority or L2 tie break.
4. Give any disabled feature a nonzero serialized weight, accept an unknown/reordered feature, or
   accept Boolean metadata as an integer.
5. Add a shared candidate-position feature or break candidate permutation equivariance.
6. Corrupt model ID, feature schema, parameter count, weight, file digest or array shape.
7. Turn structural test eligibility into a claimed measured disagreement, or let the audit read a
   private path, route cost, episode or model prediction.
8. Change the test minimum below six, count non-test rows, or treat the existing zero declarations
   as admitted.
9. Check every public statement: 10/12 is development evidence, not cross-game transfer, live
   authority or an unbiased final estimate.
10. Mutate the frozen model/source/registry/evidence digests, case hashes, challenge count, failure
    scoring, tie scoring, omission policy and rerun policy. The plan tests should distinguish them.

## Decision after audit

If clean, recommend publishing the exact repair and plan, requiring green exact-commit CI, then
asking the owner to authorize the frozen one-shot protocol. Only after that authorization should
any private test input be accessed.
