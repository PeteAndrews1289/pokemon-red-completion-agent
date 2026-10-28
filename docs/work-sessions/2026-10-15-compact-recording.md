# Compact recording and the next frozen candidate

The next candidate is **qualified and prepared, not launched**. The existing
journal API now supports an explicit, prospective compact representation. Its allocated
file space falls **49.6 percent** in the complete sampled journal, and a complete
isolation report falls **90.3 percent** under lossless gzip. No data fields were
sampled or dropped. The completed save and all failed runs remain untouched.

[Evidence](../evidence/red-compact-recording-2026-10-15.json) ·
[Current handoff](../../HANDOFF.md) · [Earlier cleanup](2026-10-15-run-retirement.md).

## What changed

Only four runtime files change: private_artifacts, the fresh and continuation
launchers, and the frozen wrapper. Goal/battle models, configuration, mechanics,
support, helpers and shared environment stay unchanged. No strategy or guard is
relaxed. The accepted Tower escape correction is retained.

An opt-in new journal stores native action, trace and diagnostic records as the
original canonical manifest line followed by the original canonical payload,
in one private immutable file. Native intent publication still synchronizes before
controller input; interrupted inputs retain failed traces and partial publication
remains visible. Non-native claims, outcomes, models and labels keep their format.
The current reader discovers the declaration and supports both representations,
including metadata-only inspection without reading payload bytes. Existing journals
are not converted; old frozen readers need the qualified/current reader for new logs.

The frozen wrapper optionally saves full ISOLATED-IO JSON as .json.gz. Decompression
recovers the exact original JSON bytes. Ordinals are shared across compressed and
plain reports, preserving every inspection rather than overwriting earlier results.

## Measured verification

| Check | Result |
| --- | --- |
| Complete closed journal | 4,958 records reopen with identical payload and manifest bytes/hashes. Includes all 1,742 intents, 1,742 traces, 1,473 diagnostics and the execution claim. |
| File allocation | 40,951,808 to 20,652,032 bytes; 9,917 to 4,961 files and 4,958 to one child directory. |
| Measured new raw layout copies | 46,329,856 to 23,363,584 bytes of volume use; not a per-record transaction timing benchmark. |
| Complete actual isolation report | 23,617,500 to 2,285,033 bytes; all 44,222 read and 61,812 write entries preserved byte-for-byte. |
| Normal native copies | Both choose the same 20 steps, two model decisions/18 support steps, 1,742 actions/117,420 frames, two heals, zero debits and the exact same terminal state. |
| Interrupted native copies | Both retain the intended action before input, one executed frame, the original injected error and the same failed trace/terminal; buttons released and workers exited. |
| Existing training reader | Reauthenticates compact action/trace records without changing admission or fitting. |
| Focused checks | 548 pass, plus lint and whitespace. Not full suite or hosted CI. |
| Isolated fresh import | 301 project modules from the pinned candidate; zero player writes/inputs. Gameplay is rejected by the staging plan. |

All 3,484 live action/trace payloads match across the normal copies. Diagnostic
differences are retained, not hidden: measured evaluation time, the existing
budget.seconds readiness feature and the new source provenance hashes. These
timings can differ with performance; this pilot still selected identical bindings.
It is not a promise that every future stochastic trajectory will be identical.

Two broader sequence-replay tests fail identically on the untouched accepted
baseline. They are documented pre-existing failures, not fixed or waived by this
storage change. No test was weakened. The frozen package remains immutable after
qualification; acceptance is recorded externally.

## Durability review and replacement

Final review found a real failure-path defect in the first fully checked candidate:
if its directory sync failed after rename, publication could report success and
permit input. The exact negative test fails against retained v2. V3 only adjudicates
a genuine competing-file error; sync failures propagate before input. Both domain
and operating-system exception variants pass against frozen v3. Normal and
interrupted copied play, all 4,958-record re-encoding and isolated fresh imports were
repeated on v3. The earlier physical-layout measurement is reused transparently:
the representation and measured allocations are identical; only error handling
changed. V2 was never launched, and its prior acceptance is explicitly withdrawn.

## Capacity and candidate

T7 Developer had 21.90 GiB free at preflight. The reference-based forecast is
18.18 GiB, with the unchanged 3 GiB low-storage stop leaving 0.73 GiB additional
headroom. It uses the completed reference's 1,588,167 actions and 1,442 goals,
twice the diagnostic rate from 62 historical receipts, measured metadata overhead
and 1 GiB for full reports.
Those receipts are not independent evaluations or ancestry-deduplicated progress.
Longer loops can still reach the storage stop; a full 16-hour fit is not guaranteed.
Check live capacity again before dispatch. No volume or quota changed.
This session deletes nothing and reclaims no existing data. Retained frozen model
copies and qualification outputs consume space; the benefit is reduced future
logging growth, not another cleanup claim.

Private packet red-compact-recording-20261015-v1 holds the package, source deltas,
all copied results, re-encoding catalog, full gzip report, CAPACITY-v3.json and acceptance.
Manifest68cc18a8876a31d197918d99acad3f4db27b0d69924cfe080fe5b9cbd999a7cb;
settingsfb2ed64dba4b9c66346e5290165cf7c6e03e9c67d4b648b63b0096926e96a767;
acceptancee5640dce61896dd675f7c27836e4e6face686cdf5f16f120a11ef7b7955d59aa.
The successor-launch-staging-v3 plan rejects gameplay and has no actual PID/clock.
The unused v1 and withdrawn v2 remain retained. Only v3 is qualified.

## Closeout and next session

This finishes the requested preparation inside the two-hour allowance. Six related
copied loads cost 5,229 actions, 352,263 frames, six heals and zero debits. No copied progress
was imported. Actual inputs, loads, TRAIN/fits/new weights/registrations are zero.
The main game and same monitor remain stopped/paused; fresh final gates stay 0/5.

Next: recheck pins and capacity, authorize a distinct fresh 16-hour dashboard run,
reuse the existing launch-once supervisor/three-GiB guard and retarget the same
monitor. Review every two hours without changing the actor; retain any real blocker,
complete proof, human pause, time boundary or low-storage stop. No save edits,
runtime LLM, refit, extra deletion, title advance or publication. For preparation
and monitoring, 6.1 Sol High at normal speed/Fast off is sufficient as a task judgment.
