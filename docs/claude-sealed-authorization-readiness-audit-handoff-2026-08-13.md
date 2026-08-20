# External audit handoff: typed receipts and live-qualification boundary

## Audit boundary

Review the published source, the path-free live-qualification evidence and non-test fixtures only.
Do **not** locate, inventory, open, hash, preflight, materialize or score an actual sealed-test
capture. Do not create the test catalog or owner authorization. The test remains 0/12 and the only
acceptable catalog source is a custodian-supplied canonical path-free manifest.

The prospective plan is schema v7, 13,262 bytes, SHA-256
`d5ade0bf749b24f5d266f568daa7da96b715b166bd05c41c473f6d91722f582a`. Its executable source
bundle is `bf98872814159e85024104befad2689a88fe589b289958d9091eb3464c8df0dd`; deterministic teacher
execution is `4e74cb4249c2dadc7e051644d2f0771937ab5b44a6521cce78ee8401432001e2`.
Bind any verdict to the full published commit under review, not merely the abbreviated commit in a
conversation.

Claude's preceding audit attacked schema v6 with eighteen one-at-a-time semantic mutations and
killed all eighteen without using the whole-plan checksum as the oracle. It approved only live
qualification. It explicitly withheld authorization because bare evidence digests did not encode
whether a receipt said “approved” or “do not proceed.” Schema v7 is the prospective repair to audit.

## What changed

- Canonical external-audit and non-test qualification receipt parsers now require exact schemas,
  scopes and key sets. Both bind the evaluation, plan, executable source bundle, full source commit
  and evidence digest.
- External-audit verdicts are allowlisted. Only `approved_for_authorization` can satisfy owner
  authorization; `approved_for_live_qualification` and `changes_required` are valid records but
  cannot authorize.
- Non-test qualification verdicts are allowlisted. Only `passed` with exactly zero sealed cases
  opened can authorize; a canonical `failed` receipt remains publishable but is non-authorizing.
- Owner-authorization construction, authorization parsing and runtime preflight all require the
  loader-issued typed receipt objects and recheck their bindings and verdicts. Raw digest strings
  cannot stand in for the receipts.
- The live qualifier accepts one explicitly named train/validation capture and never enumerates
  storage. The canonical registry refuses test-partition lookup before any input path is read.
- Qualification and sealed execution share `_open_strategic_cartridge_context`: authenticate the
  source origin and exact frontier, relocate without a label, require zero objective delta,
  authenticate the declared region, and plan all candidates.
- The rehearsal challenge must be a non-teacher objective in a different region that is already
  authenticated by a completed objective. It closes without running the teacher, proves the state
  bytes and ROM-adjacent artifacts did not change, and emits path-free evidence.

## Adversarial targets

1. Replace either receipt schema, scope, verdict, evaluation, plan digest, source bundle, full
   commit, evidence digest or production-path declaration. Every mismatch must fail before a start
   record or private test access.
2. Feed a valid `changes_required`, `approved_for_live_qualification` or `failed` receipt through
   authorization construction, authorization parsing and runtime preflight. None may authorize.
3. Hand-write a canonical authorization around unfavorable receipt digests. The parser must still
   reject it after parsing the typed receipts.
4. Try direct construction, `dataclasses.replace`, type substitution and stale typed receipts. A
   favorable verdict from an earlier source or plan must not carry forward.
5. Mutate the non-test qualifier to enumerate storage, accept a test scenario, accept a challenge
   outside the scenario frontier, relocate to an unauthenticated region, plan before relocation,
   tolerate objective drift, accept a missing candidate, run the teacher, change the capture, or
   create a ROM-adjacent artifact.
6. Replace the shared cartridge-opening call with a mock-only qualification path. Live evidence
   must traverse the same authentication, relocation and planning function used after a sealed
   case claim.
7. Attack the command boundary with dirty or unpublished source, a source bundle different from
   the plan, relative input paths, an invalid ROM, an existing output, and path-bearing failures.
8. Confirm tests contain no literal test-scenario identity paired with an answer or teacher choice,
   and that no result, including a failed or inconclusive result, can be selectively withheld.

## Required verdict

Issue `approved_for_authorization` only after the exact published commit is green and the supplied
path-free live evidence proves a passed non-test qualification with zero sealed cases opened. If
anything is weaker, issue `changes_required`. Even a favorable receipt does not create the catalog,
provide owner sign-off, open a case or claim the model passed. The owner must separately bind the
custodian manifest and explicitly accept the one-shot, publish-regardless-of-outcome run.
