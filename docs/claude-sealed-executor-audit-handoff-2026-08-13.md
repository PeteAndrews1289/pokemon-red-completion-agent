# Claude Handoff: Sealed Executor and Final-Only Scorer

## Authority and stop line

Audit only the public plan, source, tests and receipts listed below. Do not open, materialize,
preflight or execute a private test capture. Do not inspect a live test route cost, private episode,
policy input or model prediction. Do not create an owner authorization receipt. The sealed counter
is **0/12 opened**.

This handoff covers the ROM-free protocol core. It intentionally does not claim that the
cartridge-facing case runner or exact private case catalog exists. A clean core audit authorizes
building and qualifying that adapter on non-test fixtures; it does not authorize the sealed run.

## What changed after your approved endpoint audit

Your five executor/scorer requirements are now explicit schema-v3 plan clauses and executable
invariants:

1. no primary statistic is computed until all twelve cases—not merely the ten primary cases—have
   been consumed;
2. a halt after any durable case claim is a published protocol failure;
3. all twelve identities, candidate counts and their execution order are fixed in the plan;
4. source, model, teacher, catalog and owner-authorization failures refuse before case one; and
5. a crash consumes the open case and a restart continues only at the next case.

There is an additional anti-leak boundary. Each case runner has two stages:

1. `prepare(case)` opens the already-claimed input and returns the frozen model prediction,
   cheapest-route prediction and a policy-input digest; then
2. the executor durably stores that prediction commitment before it may call
   `execute_teacher(case)`.

That prevents an adapter from waiting to see the deterministic teacher answer before producing the
model prediction.

The ledger namespace is derived from the frozen plan, not the authorization digest. Self-review
caught and removed the authorization-specific namespace because a second receipt could otherwise
create a fresh attempt. The first start record binds the exact authorization; any different receipt
for the same plan must collide with that immutable record and refuse before runner access.

The only public intermediate object contains `consumed_cases`, `declared_cases: 12` and
`metrics_available: false`. Case outcomes and prediction records live only in the immutable private
ledger. The final scorer rejects 0–11 outcomes and any extra, reordered or identity-mismatched row.

## Frozen identities

- Plan schema: `pokemon-strategic-navigation-sealed-evaluation-plan-v3`
- Plan digest: `f4429dce83b99c4c5dce05785b2222e590c6d670adc0966d8f6b86e5c88d4fec`
- Plan bytes: `11208`
- Source bundle: `585fab5b42d9b409b9d7d6659d191987ba5a31958f9ac39734f6d1e07f9833b7`
- Teacher execution: `07748caa2e1aa4a2d582c80d1d06ab1afc9b9f6725c6d0fc8224ef9b1946073e`
- Frozen model: `753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1`
- Case-order digest: `8c913e7101efdfe33c21c849d46da6076653066869077e5043bcf60928a4f2ba`
- Superseded plans retained in order: `ef9f823e…b7331b`, then `230c90aa…ef5537`

No authorization receipt exists. No runtime grant has been issued against a real catalog.

## Read first

1. `MISSION.md`
2. `AGENTS.md`
3. `AGENT_COORDINATION.md`
4. `configs/red-strategic-navigation-sealed-evaluation-v1.json`
5. `configs/red-strategic-navigation-sealed-evaluation-v1.digest.json`
6. `src/pokemon_red_completion/strategic_navigation_sealed_evaluation.py`
7. `tests/test_strategic_navigation_sealed_evaluation.py`
8. `tests/test_strategic_navigation_sealed_evaluation_plan.py`
9. `scripts/regenerate_strategic_navigation_sealed_evaluation_plan.py`
10. `docs/evidence/strategic-sealed-evaluation-plan-freeze-2026-08-13.json`
11. `docs/evidence/strategic-sealed-executor-implementation-audit-2026-08-13.json`
12. `docs/current-audit-2026-08-13.md`

## Adversarial targets

### Optional stopping and visibility

1. Make the scorer calculate a p-value, win/loss count, accuracy or safety result with fewer than
   twelve outcomes.
2. Extract a case result through the progress callback or any public return before final scoring.
3. Halt after a favorable prefix, resume, and obtain a non-protocol-failure result.
4. Crash after all case outcomes but before final publication and see whether restart avoids the
   halt marker.
5. Call the completed executor again and see whether it reruns a case rather than verifying and
   returning the immutable final.
6. Issue a second syntactically valid owner authorization for the same plan and verify that it cannot
   create a fresh ledger or invoke the runner.

### Ordering, consumption and immutable evidence

1. Claim case two before case one, create a gap, create two open cases or append after an open case.
2. Crash before claim and verify that no case is consumed; crash at every boundary after claim and
   verify that exactly the current case is consumed.
3. Reopen a failed, interrupted or unavailable case, including with a new process and the same
   authorization.
4. Store an outcome without a claim, a prediction without a claim, or a success without a committed
   prediction.
5. Alter a cached final or private ledger record and see whether the executor recomputes and rejects
   it.

### Prediction-before-teacher and identity binding

1. Let `execute_teacher` run before the prediction record is durably visible.
2. Return a prediction or teacher result for the wrong case, digest, ordinal or candidate count.
3. Return an out-of-range choice, an indexed tie, a successful teacher result without its manifest
   digest, or partial evidence from a failed case.
4. Forge a runtime grant directly, or reuse a grant across a different plan, authorization, source,
   teacher or catalog.
5. Pass dirty/unpublished source, a mismatched commit, model bytes, source bundle, teacher execution
   or case-catalog digest and verify refusal occurs before a start or claim record.

### Final scoring

1. Admit either safety case to the primary pairs or omit any of the ten challenges.
2. Let a primary teacher failure erase an unfavorable pair without producing protocol failure.
3. Let a safety execution failure pass, or let safety change the primary statistic.
4. Change the exact two-sided McNemar arithmetic, six-disagreement floor, model-better direction or
   p < 0.05 threshold.
5. Let a passing result grant live authority rather than merely leave a later gate unblocked.

When mutation testing the generated plan, exclude
`test_sealed_plan_is_canonical_digest_bound_and_reproducible` as a probe oracle. A whole-file digest
assertion kills every mutation trivially and is not evidence that the semantic test can distinguish
the change. Report semantic and digest-oracle results separately. Apply the same principle to
immutable-record digests: distinguish “tampering was detected” from “the intended rule has a direct
test.”

## Local result before handoff

- Ruff: passed
- mypy: passed across 165 source files
- pytest: 2,832 passed, three integration tests deselected, one expected failure
- targeted sealed plan/executor tests: 19 passed
- private access: 0/12

No executor mutation score is claimed in the implementation receipt. The tests are adversarial,
but an independent mutation pass is the point of this handoff.

## Power correction retained

Your corrected estimate is now the documented one. At an 85% chance that the baseline actually
errs on a challenge, the conclusive-result range is roughly 42–68% across the stated model-strength
assumptions. The earlier 58–84% estimate is explicitly superseded. A null must be published and
described as underpowered evidence, not proof of no learning.

## Decision after audit

If the core survives, report that it is approved for the next implementation gate only. The next
gate is the cartridge-facing runner and exact case catalog, qualified on non-test fixtures and then
bound to a clean published commit. Only after that adapter is independently audited should Peter be
asked for explicit one-shot owner authorization. Do not convert a clean ROM-free audit into private
test access.
