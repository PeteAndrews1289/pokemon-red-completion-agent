# Focused supplement adapter audit — 2026-09-04

Reviewed source: `850f02f008e10c065e7b0522367fff31e5dc8353` (PR 214).
This is Codex's summary and adjudication, not verbatim reviewer output.

## Verdict and scope

Proceed with the existing concrete five-root production integration sequence. No blocking
defect was established in the adapter's claimed maintenance scope. This is not live-readiness,
learned-authority, model-quality or transfer approval. The eighteen-example option model already
exists; this work connects it to bounded independent development behavior.

Claude completed a read-only source review through its CLI at High, covering the new reader,
development selection/admission/execution, production runtime, adapter tests, checkpoint receipt,
and relevant supplement/journal helpers. Its underlying model was not explicitly pinned; do not
attribute this review to a particular Claude model version. It did not execute tests.

Antigravity used explicit `gemini-3.8-flash-high` and High effort. It reviewed a compact design
packet, then a corrected packet with actual semantic feature and journal excerpts. It did not
inspect the repository directly, so its verdict is not independent code verification.

Codex independently read the relevant source and reran the adapter test file: **24 passed in
55.74 seconds**. An initial invocation omitted the worktree import path and failed during test
collection; the corrected invocation used `PYTHONPATH=src:scripts`. No implementation changed.
Hosted PR CI remained in progress at the audit check; this report does not claim a hosted pass.

## Claude findings and adjudication

1. **Binding and partition defenses hold — accept within reviewed scope.** The reader checks
   canonical commitments plus row semantics, the explicit supplement type permits zero train
   rows without weakening the historical parser, and the model is checked against the pinned
   supplement binding. The existing semantic-corruption tests recompute outer commitments before
   testing rejection. This is useful regression coverage, not a complete mutation score.
2. **Direct selection fields need upstream validation — clarify, no new repair.** Claude noted
   that the supplement branch does not locally wrap every digest. However,
   `RedLivingDexClusteredDevelopmentSelection.__post_init__` also validates all digest formats
   (runner lines 97–109). Upstream validation remains necessary for semantic authenticity, but
   malformed digest acceptance is not an established defect.
3. **Positive execution coverage is narrow — accept.** The successful adapter test runs ordinal
   zero with simulated state and synthetic model parameters. Parsing covers all three rows,
   but this is not successful production execution of all rows or supplement-specific injected
   interruption coverage. Include those boundaries in the already-planned production rehearsal;
   do not create another unrelated test campaign.
4. **Failed setup allegedly used only an old plan — reject.** The fixture obtains shared test
   infrastructure from an older fixture, but `_admitted` explicitly discards its old plan,
   constructs a supplement via `_plan()`, and authenticates that supplement (test lines 171–243).
   The failed-setup test does exercise supplement admission and terminal recovery.

Claude also confirmed the importance of keeping the shared supplement-plan digest separate from
the complete Red private-plan digest. This distinction is already implemented and documented.

## Antigravity findings and adjudication

1. **Selected-only outcomes cannot establish baseline superiority — accept.** The journal runs
   only the selected branch. Same-menu model/control choice agreement or divergence is diagnostic;
   it does not supply an unplayed control outcome, regret estimate, or comparative gameplay
   advantage. Keep this five-root gate an integration falsifier. Do not add counterfactual labels
   or expand the current gate into an unplanned multi-arm benchmark.
2. **Test the actual checkpoint, not only synthetic parameters — accept the objective, reject
   predictions inside zero-effect preflight.** The declared preflight has zero predictions as
   well as zero gameplay. Validate model/corpus bindings there, then score the real checkpoint
   only at the existing committed development-decision boundary. Preserve finite-score checks
   and record ties/margins as diagnostics; ties alone do not prove a malfunction.
3. **Separate harness interruptions from policy outcomes — accept reporting requirement, defer
   schema expansion absent a demonstrated gap.** Existing records already retain execution
   status/exception type, observation provenance, censor reasons, and preinput versus postrelease
   terminal states. Production interruption tests must verify those records remain informative.
   Do not create a new discriminator merely because the compact packet omitted existing fields.

After receiving actual feature excerpts, Antigravity retracted three initial recommendations:
that eighteen samples imply representational impossibility, that mechanical legality masking is
automatically leakage, and that preflight/synthetic tests should be deleted. None is adopted.
Its initial title-specific examples and arbitrary statistical thresholds are not project evidence.

## Shortest responsible next session

1. Finish the concrete five-root command using the existing reader and journals; authenticate the
   real model record/corpus and selected context, state, profile and source joins.
2. Rehearse the production resolver with supplement selections, including success and interrupted
   recovery. Reuse shared tests; explicitly exercise the new admission-to-runtime boundary.
3. Run the declared zero-effect preflight. Do not repeat the completed census or freeze.
4. Execute only admitted bounded model-selected choices, retain factual outcomes and setup
   censors, and report menu-choice comparison separately from measured selected-arm results.
5. Reorient on gameplay evidence. No development fitting, consumed-root retry, teacher replacement,
   full replay, sealed Red execution or Crystal execution follows from this audit.

Stop on broken bindings, duplicate controller execution, inaccessible real runtime, ambiguous
terminal evidence or another diagnostic-only scope expansion. No learning counters advance here.
