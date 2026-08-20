# Claude Handoff: Sealed Primary-Endpoint Amendment

## Authority and stop line

Audit only the public plan, generator, tests and receipts listed below. Do not open, materialize,
preflight or execute a private test capture. Do not inspect a live test route cost, episode or model
prediction. The sealed counter remains **0/12 opened**.

## Why the plan changed

Your second audit approved the five-coefficient model selection and the conservative one-shot
scoring rules. It conditionally approved the evaluation design after finding that the original
primary paired test mixed ten preregistered challenge cases with two non-challenge cases. Those two
cases could add paired losses much more readily than paired wins, sharply reducing power without
testing the intended cheapest-route challenge.

That finding was accepted before any private access. The published plan digest
`ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b` is preserved in the new
plan's amendment chain as superseded.

## Amended endpoint

The twelve case identities and their source scenarios are unchanged.

- **Primary endpoint:** the ten cases whose public metadata preregisters
  `cost_baseline_challenge_hypothesis: true`.
- **Primary statistic:** two-sided exact McNemar test on paired model/baseline correctness.
- **Capability floor:** at least six measured teacher-versus-baseline disagreements inside that
  ten-case primary subset. Fewer is a published protocol failure.
- **Direction:** model paired wins must exceed paired losses and p must be below 0.05.
- **Mandatory descriptive endpoint:** model and route-cost-baseline accuracy across all twelve
  cases.
- **Safety endpoint:** the two non-challenge cases must contain zero cases where the baseline is
  correct and the model is wrong. A safety failure is reported and blocks live model authority, but
  it does not alter the primary test statistic.
- **Attempt rules:** every case is still published; omissions and reruns remain forbidden; an
  opened failure, interruption or incomplete episode is consumed and scores both actors incorrect.

Amended plan digest:
`230c90aa7120cd6badef8e933ccf014639889781fa1e32ecb4a486a6a2ef5537`.

Eighteen one-at-a-time endpoint mutations were killed with the canonical digest test excluded as
the probe oracle. The restored full gate is 2,821 passed, three integration tests deselected and one
expected failure.

The frozen model is unchanged:
`753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1`.

## Candidate-density decision

Six challenge cases have three or more candidates and four are binary. Their candidate lists are
the complete graph-legal quest frontiers committed by the source scenario registry; a third choice
cannot be appended to any current binary case without inventing an unavailable objective. Replacing
cases after observing that development accuracy was better on multiway choices would also change
objective coverage to favor a known development pattern. The benchmark composition therefore
remains unchanged. This is not a claim that binary performance is adequate; all candidate-count
results must be published.

## Read first

1. `MISSION.md`
2. `AGENTS.md`
3. `AGENT_COORDINATION.md`
4. `configs/red-strategic-navigation-sealed-evaluation-v1.json`
5. `configs/red-strategic-navigation-sealed-evaluation-v1.digest.json`
6. `scripts/regenerate_strategic_navigation_sealed_evaluation_plan.py`
7. `tests/test_strategic_navigation_sealed_evaluation_plan.py`
8. `docs/evidence/strategic-sealed-evaluation-plan-freeze-2026-08-13.json`
9. `docs/evidence/strategic-sealed-endpoint-amendment-mutation-audit-2026-08-13.json`
10. `docs/current-audit-2026-08-13.md`

## Adversarial targets

1. Reverse the primary filter or let either non-challenge case enter the primary paired test.
2. Drop any challenge case from the primary subset or lower its expected count from ten.
3. Let all-twelve accuracy replace the primary paired statistic.
4. Lower the six-disagreement capability floor, make the test one-sided, weaken p below 0.05, or
   remove the required model-better direction.
5. Let a safety failure alter the primary statistic, or let it pass without blocking live authority.
6. Remove mandatory all-case accuracy or omit either non-challenge result.
7. Mutate tie, failure, interruption, omission, rerun or one-attempt handling.
8. Remove the superseded digest, change any case/source/model/source-bundle digest, or claim that a
   structural challenge is a measured disagreement.
9. Access any private test input while auditing this public amendment.

## Decision after audit

If the amendment is clean, the public experimental design is approved. That approval is not owner
authorization and does not open the test. The next implementation gate is a separately audited,
fail-closed sealed executor and result scorer bound to this exact plan; only after those are green
and the owner explicitly authorizes the one-shot may a private test input be accessed.
