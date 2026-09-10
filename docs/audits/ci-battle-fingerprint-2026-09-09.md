# CI maintenance: stale battle-module fingerprint

Runs [34303441242](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/runs/34303441242)
and [34302286548](https://github.com/PeteAndrews1289/pokemon-red-completion-agent/actions/runs/34302286548)
failed the same independent operational-contract golden test. The recorded expected
battle fingerprint was534dcd3e; the actual fingerprint wase5cb7194.

The source diff at8d9dcc06 was reviewed: battle_runtime refreshes the final
post-pulse observation before diagnosing a PP-gate timeout, along with formatting.
The operational contract intentionally fingerprints the entire module. Its golden
test still expected the older bytes. The failure reproduced locally, so this is
not a Linux-versus-Mac discrepancy or a new model-training failure.

Update only the independently recorded expected digest and explain the reviewed
change. Do not remove the assertion, allow either digest, regenerate historical
receipts, disable CI or rerun consumed gameplay. The neighboring drift-rejection
tests remain in place. This is maintenance for the next model79/Lance learning
step; no new learner authority, model row, save change or stage progress is claimed.

The earlier local broad diagnostic stopped before this test. Its previous report
correctly was not a full-suite pass, but failing to inspect the hosted result before
the next push allowed the same notification to repeat. Next time inspect the actual
failed job first, then reproduce that exact test before expanding test coverage.

Verification: all52 tests in the affected operational-contract module passed in
108.38 seconds after the correction. Lint, documentation, product-focus,
public-artifact and registry-freshness checks also passed. These are targeted
results, not a claimed full-suite pass. No executable-source digest changed.
