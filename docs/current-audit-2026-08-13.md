# Current Audit — 2026-08-13

## Outcome

Claude's independent review found two real pre-test design defects, then its second pass found one
power defect in the proposed repair. All three were caught before any sealed scenario was opened.
The model-capacity and public test-capability defects are repaired, and Claude has approved the
amended endpoint. The ROM-free executor/scorer core, strict path-free catalog boundary and
prediction-first cartridge adapter are now implemented. Claude's adapter audit killed 18/18
semantic mutations and approved live qualification, then found one final authority defect: bare
receipt digests did not say whether the underlying verdict was favorable. Schema v7 now parses and
enforces typed verdicts. Exact-commit CI, live non-test relocation qualification, a final
authorization-level audit, a custodian-supplied path-free catalog and owner authorization remain
hard stops.

The v2 collection is unchanged: 24 authenticated train choices, 12 development-validation choices,
36 unique candidate-order-invariant contexts, no partition overlap and no failed or interrupted
choice promoted as an imitation label. Test remains **0/12 opened**.

The original eight-hidden-unit MLP is now a preserved, superseded development candidate. Its roughly
753 fitted parameters were inappropriate for 24 training examples, and seven validation-compared
trials made its 7/12 validation result weak evidence. It has not been deleted or retroactively
relabelled.

The replacement is a shared linear candidate scorer with **five fitted coefficients**. Model family,
feature subset and regularization are selected using training only: leave one of the 24 training
decisions out, fit on the other 23, and repeat. The best leave-one-out score was 17/24 from a
24-feature alternative. A one-standard-error simplicity rule admitted models at or above 61.6% and
selected the five-feature relative-route scorer at 16/24 rather than the larger alternative.
Validation was not accepted by the selection API.

Only after that choice was fixed was development validation evaluated. The linear scorer reached
**10/12 (83.3%)** versus cheapest route at **4/12 (33.3%)**, with six paired wins, zero losses and
exact two-sided p = 0.03125. This is substantially better development evidence, not a final
generalization result. The validation set has been inspected repeatedly and cannot become a sealed
estimate again.

## Claude finding 1: capacity and selection

The repair removes the high-capacity-only trial grid from the active fit path. The six training-only
feature families now cover one cost-rank coefficient, five relative-route coefficients, seven
candidate-tag coefficients, two combinations, and all 24 training-active columns. Five L2 values are
compared inside leave-one-out training evaluation. The final scorer uses:

- route-cost relative rank;
- route-step relative rank;
- map-transition relative rank;
- field-action relative rank; and
- movement-mode-change relative rank.

There is no shared intercept because it would cancel across candidates. Disabled columns are
serialized with exactly zero weight, feature order is authenticated, candidate permutation still
permutes probabilities, and the loader dispatches between the preserved MLP format and the new
linear format without weakening digest checks. A second adversarial pass killed 13/13 mutations
covering partition boundaries, true leave-one-out construction, the simplicity rule, serialized
weights, exact-p arithmetic and declared-versus-eligible test semantics.

Frozen linear model canonical digest:
`753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1`.
An independent refit after all source restoration reproduced both the private model and public
development receipt byte for byte.

## Claude finding 2: sealed-test capability

The committed v2 generator deliberately created six cost-baseline challenge hypotheses in
validation and **zero in test**. A perfect scorer needs at least six teacher-versus-baseline
disagreements for a two-sided paired exact p below 0.05. The current test specification guarantees
none, so spending it now could produce an evaluation that is incapable of answering its own
question.

A new ROM-free audit inspected only committed scenario metadata. It accessed no private capture,
episode, live route cost or model prediction. Ten of the twelve public test frontiers are
structurally eligible for a local non-teacher alternative, but eligibility is only a design option;
it is not a measured baseline disagreement. The original sealed design therefore remains blocked.

A first replacement one-shot plan was frozen without modifying the historical v2 registry. It gives
the twelve source test frontiers new evaluation-case identities and places all ten eligible cases at
the declared non-teacher region. It binds the exact five-parameter model, source bundle, development
receipt and source scenario registry. It also declares ties incorrect, consumes failed or interrupted
opened cases, forbids omissions and reruns, and requires every result to be published. Plan digest:
`ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b`.

This first revision repaired prospective capability; it did not manufacture measured disagreements.
Its digest is preserved as the superseded parent of the amended plan below.

## Claude finding 3: primary-endpoint power

Claude's second audit approved the five-parameter model selection, one-standard-error arithmetic and
conservative scoring policy. Its session total reached 58 independent mutation probes with zero
survivors. It then found that using all twelve cases for the primary paired test was needlessly
asymmetric: the two non-challenge cases are designed around a baseline-favorable origin, so they can
add model losses much more readily than model wins.

The correction was made while private access was still 0/12. The primary endpoint is now the ten
cases preregistered as cost-baseline challenges. It retains the six-measured-disagreement capability
floor, two-sided exact McNemar test, p < 0.05 threshold and an explicit requirement that model wins
exceed losses. Model and baseline accuracy over all twelve cases remains mandatory. The other two
cases are a separate safety endpoint: any model-wrong/baseline-correct result is reported and blocks
live authority, but does not enter or alter the primary statistic.

The case identities and source scenarios did not change. Six challenge cases are multiway and four
are binary. Each candidate list is the complete graph-legal frontier, so adding a third option to an
existing binary case would be fabricated. Replacing cases after observing stronger development
performance on multiway choices would change objective coverage to favor a known pattern; that was
rejected. Candidate-count results will be published rather than optimized away.

Amended plan digest:
`230c90aa7120cd6badef8e933ccf014639889781fa1e32ecb4a486a6a2ef5537`.
The amendment explicitly binds the superseded digest and records zero private inputs opened.
Claude independently reran nineteen one-at-a-time mutations of the endpoint semantics after
regenerating the plan. The fixed canonical digest test was deliberately excluded as a probe oracle,
so these were semantic checks rather than checksum-only failures. All nineteen were killed.

Claude also corrected its earlier power calculation. Allowing a challenge hypothesis to be wrong
as well as right changes the realistic estimate materially: when the baseline actually errs on 85%
of challenges, the chance of a conclusive result is roughly 42–68% across the stated model-strength
range, not 58–84%. The amendment still improves power substantially, but a null result will be
underpowered evidence rather than proof that the model learned nothing.

## Finding 4: optional stopping is now an executable rule

At the executor-core checkpoint, the plan was schema v3 with digest
`f4429dce83b99c4c5dce05785b2222e590c6d670adc0966d8f6b86e5c88d4fec`. Its amendment chain preserves
both prior plan digests. The new source module provides a strict public loader, owner-authorization
format, preflight grant, immutable private ledger, one-shot executor and final-only scorer.

The ordering rules are mechanical:

- preflight must authenticate clean published source, exact commit, model, teacher execution and
  case catalog before the first durable claim;
- a case is claimed before its private input may be opened;
- model and baseline predictions are durably committed before the deterministic teacher acts;
- the twelve cases run only in the frozen order, and a claimed case can never be reopened;
- a crash consumes the current case as interrupted, records a protocol failure and resumes at the
  next case on restart; and
- the progress callback exposes only `consumed_cases` and `metrics_available: false`. The scorer
  refuses every sequence shorter or longer than all twelve outcomes.

Self-review found and repaired one important first-draft loophole before publication. The private
namespace originally included the authorization digest, which meant a second owner receipt could
create a fresh ledger for the same plan. The namespace is now plan-global. A second authorization
therefore collides with the existing start record and is refused before the runner can open a case.
Canonical plan and authorization objects are also issued only by their strict loader/parser paths.

After all twelve outcomes exist, the primary McNemar statistic uses only the ten challenge cases.
Both safety cases must execute successfully and contain no model-wrong/baseline-correct result.
Candidate-count accuracy and all-case accuracy are descriptive, and no result can directly grant
live authority. A failed primary teacher execution is a protocol failure rather than an omission
that can improve the paired result.

The ROM-free tests exercise preflight mismatches, authorization binding, fixed order, claim-before-
access, prediction-before-teacher ordering, incomplete-score refusal, challenge/safety separation,
unfavorable failed cases, cached-final verification, hard crash/restart consumption, runner
identity mismatch, a pre-claim crash, and a second-authorization rerun attempt. That historical
local gate was 2,832 passed, three integration tests deselected, one expected failure, Ruff clean
and mypy clean across 165 source files.

## Finding 5: challenge origin was not the source snapshot origin

The adapter audit found a concrete execution gap before any sealed input was opened. Ten challenge
cases deliberately move the evaluation question beside a tempting non-teacher objective. Their
source scenarios authenticate a different origin. The first factory draft loaded that source and
immediately required it to already be at the challenge origin—an impossible assumption disguised by
ROM-free interface tests.

Plan schema v5 freezes the repair. A claimed case now authenticates its original source region and
exact completed-objective frontier, performs a deterministic relocation without recording a
strategic decision, rejects any change to that frontier, authenticates the declared challenge
region, and only then constructs candidate routes and an unlabeled model input. The teacher
trajectory records the declared challenge origin. Candidate ordering is derived from the exact
capture, scenario registry, source bundle, source commit and teacher execution rather than accepting
an arbitrary nonce.

The schema-v5 checkpoint was 12,505 bytes with SHA-256
`2f7ec30b096655d23626a7a98107df770fe7e9a26943240a45f5887e72a5cba6`. Its amendment chain retains
schema-v4 digest `63b3855463fcf8834ee8ae7635df1726b78fcde52257b0c7c5a3ecb26de131d7`.
Focused catalog, executor, adapter and relocation verification is 101 passed; synthetic objective
drift closes the emulator before candidate planning. This historical checkpoint was not live
cartridge qualification and is superseded by schema v6 below.

One authority bootstrap remains explicit. The final owner receipt must bind the exact catalog
digest, while building that catalog requires hashing the private test captures. The next step must
therefore use narrowly scoped inventory-only owner permission or a custodian-supplied canonical
path-free manifest. It must not silently inspect captures under an authorization that cannot yet be
constructed.

## Finding 6: descriptive readiness gates were not runtime authority

The next self-audit found two fail-open seams while test access was still 0/12. First, the plan said
that external audit and non-test qualification were required, but an authorization and runtime
grant did not bind the exact evidence. Second, loader-issued frozen dataclasses carried a private
constructor token as a normal field, so `dataclasses.replace` could copy that token while changing
an authenticated value.

Plan schema v6 freezes the repair. Owner authorization now names the exact SHA-256 of both the
external-audit receipt and the non-test adapter-qualification receipt. Runtime preflight must be
given the same two digests and refuses either mismatch before publishing its start record. Those
identities persist in the immutable start ledger and final public result. Validation tokens are now
required `InitVar` inputs and runtime grants retain a private issued-token check, so direct
construction and ordinary dataclass cloning both fail.

The private opener was hardened at the same boundary: its root must be absolute, and every path
component from the filesystem anchor through the case directory is opened descriptor-relative with
symlink following disabled. An executor runner must expose a cleanup boundary before the start
record can exist, preventing a prepared emulator session from becoming uncloseable after a failed
prediction commitment.

The schema-v6 plan was 12,914 bytes with SHA-256
`9df65487806d80b7d37e074c6f1ecf0ddf615e9853f7615e5681975e461ff440`; source bundle
`6dcf2e9237e5a5f1c52b87869cbb5eed5def8c8130520b6295ef0e0e48a422db`; teacher execution
`7866f7627af0b56fa78553fb29c8d8d21bd33b278907bbf04dac546d9d27a0cd`. Its fifth pre-access
amendment preserves schema-v5 digest
`2f7ec30b096655d23626a7a98107df770fe7e9a26943240a45f5887e72a5cba6`. The focused public gate is
124 passed. The full repository gate is 2,872 passed, three integration tests deselected, one
expected failure, Ruff clean and mypy clean across 168 source files. Receipt binding authenticates
exact bytes plus the owner's acknowledgement; an independent reviewer should still decide whether
typed receipt parsers are warranted before authorization. No audit or live-qualification verdict
is being claimed here.

## Finding 7: a receipt digest did not encode its verdict

Claude's final schema-v6 pass verified the optional-stopping boundary, found no answer-bearing test
fixture and killed 18/18 one-at-a-time mutations without relying on the whole-plan digest. It
approved the exact adapter design for the next gate—live qualification on non-test cartridge
states—but correctly refused authorization. Owner authorization bound two receipt digests, while
no parser established whether either receipt was favorable. A correctly bound audit saying
`changes_required` could therefore satisfy the same digest-shaped slot as an approval.

Schema v7 makes the evidence semantic. Canonical external-audit receipts allow three explicit
verdicts: `approved_for_live_qualification`, `approved_for_authorization` and `changes_required`.
Only the authorization verdict passes the owner gate. Canonical non-test receipts allow `passed`
or `failed`; only `passed` with exactly zero sealed test cases opened can authorize. Both formats
bind the evaluation, plan digest, executable source bundle, full source commit and evidence digest.
The authorization builder, authorization parser and runtime preflight require the parser-issued
typed objects and recheck those bindings and verdicts. A canonical negative receipt is retained as
evidence but cannot be mistaken for permission.

The same amendment adds a live qualification command that cannot search capture storage. It accepts
one explicit train/validation state and envelope; the canonical registry refuses a test partition
before reading either path. Its challenged non-teacher objective must relocate to a different
region already authenticated by a completed objective, matching the sealed case-construction rule.
Qualification calls the same production function as sealed execution: authenticate source origin
and exact frontier, relocate without a label, prove zero objective delta, authenticate the declared
region and plan all candidates. It then closes without a teacher action and verifies the capture
and ROM-adjacent artifacts are unchanged.

The v7 plan is 13,262 bytes with SHA-256
`d5ade0bf749b24f5d266f568daa7da96b715b166bd05c41c473f6d91722f582a`; source bundle
`bf98872814159e85024104befad2689a88fe589b289958d9091eb3464c8df0dd`; teacher execution
`4e74cb4249c2dadc7e051644d2f0771937ab5b44a6521cce78ee8401432001e2`. It preserves the v6 digest
as the sixth amendment and records zero private inputs opened. This is readiness engineering, not
a live qualification result or authorization. The final local gate is 2,887 passed, three
integration tests deselected and one expected failure; 93 focused boundary tests, generated
identity checks, Ruff and mypy across 168 source files are also clean.

## Stop line and next work

Do not open, preflight, materialize or score a private test capture yet. The safe order is:

1. publish schema v7 as one exact commit and require green exact-commit CI;
2. live-qualify the shared relocation path on one explicit non-test cartridge state, run no
   teacher, open zero test cases and preserve the path-free evidence plus typed receipt outside the
   repository;
3. independently audit that exact commit and live evidence, producing a typed
   `approved_for_authorization` receipt only if the whole gate is clean;
4. obtain a custodian-supplied canonical path-free manifest for the test catalog, then obtain owner
   authorization bound to the final plan, source, model, teacher, both favorable receipts and
   catalog; and
5. only then measure baseline disagreements and execute the one-shot comparison, publishing every
   result whether favorable, unfavorable, failed or inconclusive.

A 12-case test can establish a very large paired effect but will still have a wide uncertainty
interval. A later, larger cross-context evaluation is required for a precise performance estimate.

## Evidence

- [Counted collection audit](evidence/strategic-counted-collection-audit-2026-08-13.json)
- [Superseded MLP development receipt](evidence/strategic-navigation-model-development-2026-08-13.json)
- [Linear model development receipt](evidence/strategic-navigation-linear-development-2026-08-13.json)
- [Linear byte-reproduction audit](evidence/strategic-navigation-linear-reproduction-audit-2026-08-13.json)
- [Sealed-test design audit](evidence/strategic-sealed-test-design-audit-2026-08-13.json)
- [Replacement sealed-plan freeze](evidence/strategic-sealed-evaluation-plan-freeze-2026-08-13.json)
- [Original targeted mutation audit](evidence/strategic-navigation-model-mutation-audit-2026-08-13.json)
- [Linear and sealed-design mutation audit](evidence/strategic-linear-and-sealed-design-mutation-audit-2026-08-13.json)
- [Sealed endpoint-amendment mutation audit](evidence/strategic-sealed-endpoint-amendment-mutation-audit-2026-08-13.json)
- [Sealed executor/scorer implementation audit](evidence/strategic-sealed-executor-implementation-audit-2026-08-13.json)
- [Superseded schema-v5 sealed-plan freeze](evidence/strategic-sealed-evaluation-plan-v5-freeze-2026-08-13.json)
- [Superseded schema-v6 sealed-plan freeze](evidence/strategic-sealed-evaluation-plan-v6-freeze-2026-08-13.json)
- [Current schema-v7 sealed-plan freeze](evidence/strategic-sealed-evaluation-plan-v7-freeze-2026-08-13.json)
- [ROM-free sealed-adapter qualification](evidence/strategic-sealed-adapter-rom-free-qualification-2026-08-13.json)
- [Linear pre-test audit handoff](claude-linear-pre-test-audit-handoff-2026-08-13.md)
- [Sealed endpoint-amendment audit handoff](claude-sealed-endpoint-amendment-handoff-2026-08-13.md)
- [Sealed executor/scorer audit handoff](claude-sealed-executor-audit-handoff-2026-08-13.md)
- [Sealed adapter audit handoff](claude-sealed-adapter-audit-handoff-2026-08-13.md)
- [Typed-receipt and live-qualification audit handoff](claude-sealed-authorization-readiness-audit-handoff-2026-08-13.md)
